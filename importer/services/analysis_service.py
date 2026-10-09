"""
Session d'import : enregistrement des fichiers, choix de la feuille, rapprochement et rapport (lots I1 et I2),
puis écriture en base des sinistres importables (lot I3).

1. analyse()       : rapprochement, aucune écriture dans les tables métier ; statut ANALYSED, chiffres dans
                     `summary`, rapport Excel dans `error_file`.
2. import_claims() : après validation du rapprochement par l'utilisateur, relit les fichiers, refait le même
                     rapprochement et écrit les sinistres importables (writer_service, une seule transaction) ;
                     statut DONE, rapport complété (rejets à l'écriture, assurés à vérifier, polices et taux).
"""
import logging
import os

from django.core.files.base import ContentFile
from django.db import transaction
from django.utils import timezone

from file_handling.models import File, ImportSession
from importer.reconciliation import engine, report, sources
from importer.services.writer_service import write_claims

logger = logging.getLogger(__name__)

UNEXPECTED = ("Erreur inattendue pendant le traitement. Les fichiers sont conservés ; "
              "contactez l'administrateur si le problème persiste.")


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


def _fail(session, message, summary=None):
    session.status = ImportSession.Status.ERROR
    session.message = message
    session.summary = summary
    session.completed_at = timezone.now()
    session.save(update_fields=['status', 'message', 'summary', 'completed_at'])
    return session


def _reconcile(session, sheet):
    stat_file = session.stat_file
    recap_files = list(session.recap_files.all().order_by('pk')) or [session.recap_file]
    stat = sources.load_stat(stat_file.file.path, _display_name(stat_file), sheet)
    recap = sources.load_recaps([(f.file.path, _display_name(f)) for f in recap_files])
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
    session.status = ImportSession.Status.PROCESSING
    session.stat_sheet = sheet or ''
    session.started_at = timezone.now()
    session.completed_at = None
    session.message = ''
    session.summary = None
    if session.error_file:
        session.error_file.delete(save=False)
    session.save()

    try:
        result = _reconcile(session, sheet)
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

    _save_report(session, result)
    s = result.summary
    session.summary = s
    session.start_date, session.end_date = result.period[0].date(), result.period[1].date()
    session.status = ImportSession.Status.ANALYSED
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
    session.status = ImportSession.Status.PROCESSING
    session.started_at = timezone.now()
    session.save(update_fields=['status', 'started_at'])
    try:
        result = _reconcile(session, session.stat_sheet or None)
        write = write_claims(session, result)
    except Exception:
        logger.exception("Écriture en base de la session %s", session.pk)
        session.status = ImportSession.Status.ANALYSED
        session.summary = previous
        session.message = "L'écriture en base a échoué : rien n'a été importé. " + UNEXPECTED
        session.save(update_fields=['status', 'summary', 'message'])
        return False

    _save_report(session, result, write)
    w = write.summary()
    session.summary = {**result.summary, 'write': w}
    session.insured_created_count = write.created['Insured']
    session.claims_created_count = write.created['Claim']
    session.total_claimed_amount = write.claimed
    session.total_reimbursed_amount = write.reimbursed
    session.status = ImportSession.Status.DONE
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
