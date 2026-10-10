"""
Session d'import : enregistrement des fichiers, choix de la feuille, rapprochement et rapport (lots I1 et I2),
puis écriture en base des sinistres importables (lot I3).

1. analyse()       : rapprochement, aucune écriture dans les tables métier ; statut ANALYSED, chiffres dans
                     `summary`, rapport Excel dans `error_file`.
2. import_claims() : après validation du rapprochement par l'utilisateur, relit les fichiers, refait le même
                     rapprochement et écrit les sinistres importables (writer_service, une seule transaction) ;
                     statut DONE, rapport complété (rejets à l'écriture, assurés à vérifier, polices et taux).

Lot I4 : les deux traitements tournent en tâche de fond (importer/tasks.py). La vue appelle queue_analyse() ou
queue_import(), qui passent la session en PROCESSING (étape ANALYSE ou IMPORT) et confient le travail à Celery ;
l'interface suit `progress` / `progress_label`. En local, CELERY_TASK_ALWAYS_EAGER=True exécute la tâche tout de
suite, dans la requête. Un traitement sans signe de vie depuis IMPORT_STALE_MINUTES est déclaré interrompu
(mark_stale) : une écriture interrompue n'a rien écrit (transaction unique).
"""
import logging
import os
from datetime import timedelta

from django.conf import settings
from django.core.files.base import ContentFile
from django.db import transaction
from django.utils import timezone

from file_handling.models import File, ImportSession
from importer.reconciliation import engine, report, sources
from importer.services.writer_service import write_claims

logger = logging.getLogger(__name__)

STALE_AFTER = timedelta(minutes=getattr(settings, 'IMPORT_STALE_MINUTES', 20))
QUEUE_UNAVAILABLE = ("Le service de traitement en arrière-plan est indisponible : relancez plus tard ou "
                     "contactez l'administrateur.")
INTERRUPTED_ANALYSE = "Le rapprochement a été interrompu (serveur redémarré ?). Relancez-le."
INTERRUPTED_IMPORT = ("L'écriture en base a été interrompue (serveur redémarré ?) : rien n'a été importé. "
                      "Vous pouvez relancer l'import.")

UNEXPECTED = ("Erreur inattendue pendant le traitement. Les fichiers sont conservés ; "
              "contactez l'administrateur si le problème persiste.")

PROGRESS_FIELDS = ['status', 'step', 'progress', 'progress_label', 'progress_at', 'started_at', 'completed_at']


def create_session(user, country, stat_upload, recap_uploads, currency=None):
    """Enregistre les fichiers et crée la session (statut PENDING). Devise : celle du pays par défaut."""
    with transaction.atomic():
        stat = File.objects.create(user=user, file=stat_upload, file_type='stat', country=country)
        recaps = [File.objects.create(user=user, file=up, file_type='recap', country=country)
                  for up in recap_uploads]
        session = ImportSession.objects.create(
            user=user, country=country, stat_file=stat, recap_file=recaps[0],
            status=ImportSession.Status.PENDING,
            currency=(currency or country.currency_code or '')[:3].upper(),
        )
        session.recap_files.set(recaps)
    return session


def stat_sheets(session):
    stat = session.stat_file
    return sources.list_sheets(stat.file.path, stat.file.name)


def _display_name(file):
    """Nom d'origine du fichier (sans le suffixe ajouté par le stockage en cas de doublon de nom)."""
    return f"{file.name}{os.path.splitext(file.file.name)[1]}" if file.name else os.path.basename(file.file.name)


# ------------------------------------------------------------------ avancement et tâche de fond
def progress(session, percent, label):
    """Avancement visible pendant le traitement (requête séparée : pas d'écrasement des autres champs)."""
    now = timezone.now()
    ImportSession.objects.filter(pk=session.pk).update(progress=percent, progress_label=label, progress_at=now)
    session.progress, session.progress_label, session.progress_at = percent, label, now


def _start(session, step, label):
    now = timezone.now()
    session.status = ImportSession.Status.PROCESSING
    session.step = step
    session.progress, session.progress_label, session.progress_at = 0, label, now
    session.started_at = now
    session.completed_at = None


def _dispatch(session, task, *args):
    """Confie le traitement à Celery après la validation de la transaction en cours. Si la file est injoignable,
    la session est remise dans un état stable avec le motif."""
    def send():
        try:
            task.delay(session.pk, *args)
        except Exception:
            logger.exception("Mise en file du traitement de la session %s", session.pk)
            fresh = ImportSession.objects.filter(pk=session.pk).first()
            if fresh and fresh.status == ImportSession.Status.PROCESSING:
                is_import = fresh.step == 'IMPORT'
                fresh.status = ImportSession.Status.ANALYSED if is_import else ImportSession.Status.ERROR
                fresh.message = QUEUE_UNAVAILABLE
                fresh.step = ''
                fresh.save(update_fields=['status', 'message', 'step'])
    transaction.on_commit(send)


def queue_analyse(session, sheet=None):
    """Rapprochement en tâche de fond. Renvoie la session relue (déjà terminée si la tâche s'exécute sur place)."""
    from importer import tasks
    _start(session, 'ANALYSE', 'En attente du rapprochement…')
    session.stat_sheet = sheet or ''
    session.message = ''
    session.summary = None
    session.save()
    _dispatch(session, tasks.analyse_session, sheet)
    session.refresh_from_db()
    return session


def queue_import(session):
    """Écriture en base en tâche de fond (session ANALYSED). Renvoie la session relue."""
    from importer import tasks
    _start(session, 'IMPORT', "En attente de l'écriture en base…")
    session.save(update_fields=PROGRESS_FIELDS)
    _dispatch(session, tasks.import_session)
    session.refresh_from_db()
    return session


def mark_stale(session):
    """Traitement sans signe de vie depuis STALE_AFTER : déclaré interrompu. Renvoie True si la session a changé."""
    if session.status != ImportSession.Status.PROCESSING:
        return False
    last = session.progress_at or session.started_at or session.created_at
    if last and timezone.now() - last < STALE_AFTER:
        return False
    if session.step == 'IMPORT':
        session.status, session.message = ImportSession.Status.ANALYSED, INTERRUPTED_IMPORT
    else:
        session.status, session.message = ImportSession.Status.ERROR, INTERRUPTED_ANALYSE
        session.completed_at = timezone.now()
    session.step = ''
    session.save(update_fields=['status', 'message', 'step', 'completed_at'])
    return True


# ------------------------------------------------------------------ traitements
def _fail(session, message, summary=None):
    session.status = ImportSession.Status.ERROR
    session.step = ''
    session.message = message
    session.summary = summary
    session.completed_at = timezone.now()
    session.save(update_fields=['status', 'step', 'message', 'summary', 'completed_at'])
    return session


def _reconcile(session, sheet, start=0, end=60):
    """Lecture et rapprochement ; avancement de `start` à `end` %."""
    stat_file = session.stat_file
    recap_files = list(session.recap_files.all().order_by('pk')) or [session.recap_file]
    progress(session, start, 'Lecture du fichier statistique…')
    stat = sources.load_stat(stat_file.file.path, _display_name(stat_file), sheet)
    span = end - start
    last = [None]

    def on_file(i, n):
        pct = start + int(span * 0.2) + int(span * 0.6 * i / n)
        if pct != last[0] or i == n:
            last[0] = pct
            progress(session, pct, f'Lecture des récaps ({i} / {n})…')

    recap = sources.load_recaps([(f.file.path, _display_name(f)) for f in recap_files], on_file=on_file)
    progress(session, start + int(span * 0.85), 'Rapprochement des sinistres…')
    return engine.reconcile(stat, recap)


def _save_report(session, result, write=None):
    content = report.build_report(result, {
        'session_id': session.pk,
        'country': str(session.country),
        'user': session.uploaded_by_name,
        'sheet': session.stat_sheet,
        'currency': session.currency,
        'date': timezone.localtime().strftime('%d/%m/%Y %H:%M'),
        'dry_run': write is None,
    }, write=write)
    if session.error_file:
        session.error_file.delete(save=False)
    session.error_file.save(f"rapport_import_session_{session.pk}.xlsx", ContentFile(content), save=False)


def analyse(session, sheet=None):
    """Rapprochement de la session sur la feuille `sheet` (None : CSV ou première feuille).
    Ne lève pas d'exception : le résultat est dans session.status / message / summary / error_file."""
    _start(session, 'ANALYSE', 'Rapprochement en cours…')
    session.stat_sheet = sheet or ''
    session.message = ''
    session.summary = None
    if session.error_file:
        session.error_file.delete(save=False)
    session.save()

    try:
        result = _reconcile(session, sheet, 0, 80)
    except engine.NoCommonPeriod as exc:
        iso = lambda d: d.date().isoformat()
        return _fail(session, str(exc), {
            'stat': {'start': iso(exc.stat_range[0]), 'end': iso(exc.stat_range[1])},
            'recap': {'start': iso(exc.recap_range[0]), 'end': iso(exc.recap_range[1])},
            'period': None,
        })
    except (sources.SourceError, engine.NoUsableData) as exc:
        return _fail(session, str(exc))
    except Exception:
        logger.exception("Rapprochement de la session %s", session.pk)
        return _fail(session, UNEXPECTED)

    progress(session, 85, 'Rédaction du rapport…')
    _save_report(session, result)
    s = result.summary
    session.summary = s
    session.start_date, session.end_date = result.period[0].date(), result.period[1].date()
    session.status = ImportSession.Status.ANALYSED
    session.step = ''
    session.progress, session.progress_label = 100, 'Rapprochement terminé'
    session.completed_at = timezone.now()
    session.message = (
        f"Période commune du {engine.fmt_date(result.period[0])} au {engine.fmt_date(result.period[1])} : "
        f"{s['importable']['claims']} sinistre(s) importable(s), {s['claims']['non_conform']} non conforme(s). "
        "Rien n'a encore été écrit en base."
    )
    session.save()
    return session


def import_claims(session):
    """Écrit en base les sinistres importables d'une session ANALYSED. Renvoie True si l'écriture a eu lieu.
    En cas d'échec, rien n'est écrit (transaction annulée) et la session reste ANALYSED, avec le motif."""
    previous = session.summary
    _start(session, 'IMPORT', 'Écriture en base…')
    session.save(update_fields=PROGRESS_FIELDS)
    try:
        result = _reconcile(session, session.stat_sheet or None, 0, 50)
        # Une seule transaction : l'avancement n'est pas visible pendant l'écriture elle-même
        progress(session, 55, 'Écriture des sinistres en base (environ une minute)…')
        write = write_claims(session, result)
    except Exception:
        logger.exception("Écriture en base de la session %s", session.pk)
        session.status = ImportSession.Status.ANALYSED
        session.step = ''
        session.summary = previous
        session.message = "L'écriture en base a échoué : rien n'a été importé. " + UNEXPECTED
        session.save(update_fields=['status', 'step', 'summary', 'message'])
        return False

    progress(session, 90, 'Rédaction du rapport…')
    _save_report(session, result, write)
    w = write.summary()
    session.summary = {**result.summary, 'write': w}
    session.insured_created_count = write.created['Insured']
    session.claims_created_count = write.created['Claim']
    session.total_claimed_amount = write.claimed
    session.total_reimbursed_amount = write.reimbursed
    session.status = ImportSession.Status.DONE
    session.step = ''
    session.progress, session.progress_label = 100, 'Import terminé'
    session.completed_at = timezone.now()
    parts = [f"{write.created['Claim']} sinistre(s) importé(s) ({write.created['ClaimLine']} ligne(s) d'actes)"]
    if write.skipped_identical:
        parts.append(f"{len(write.skipped_identical)} déjà en base à l'identique, ignoré(s)")
    if write.rejected:
        parts.append(f"{len(write.rejected)} rejeté(s) à l'écriture (voir le rapport)")
    if write.insured_notes:
        parts.append(f"{len(write.insured_notes)} point(s) sur les assurés à vérifier")
    session.message = ' ; '.join(parts) + '.'
    session.save()
    return True
