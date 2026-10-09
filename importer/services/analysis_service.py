"""
Session d'import : enregistrement des fichiers, choix de la feuille, rapprochement et rapport (lots I1 et I2).

Rien n'est écrit dans les tables métier (sinistres, assurés…) : la session garde seulement ses fichiers,
la feuille choisie, les chiffres du rapprochement (summary) et le rapport Excel (error_file).
L'écriture en base viendra au lot I3.
"""
import logging
import os

from django.core.files.base import ContentFile
from django.db import transaction
from django.utils import timezone

from file_handling.models import File, ImportSession
from importer.reconciliation import engine, report, sources

logger = logging.getLogger(__name__)


def create_session(user, country, stat_upload, recap_uploads):
    """Enregistre les fichiers et crée la session (statut PENDING)."""
    with transaction.atomic():
        stat = File.objects.create(user=user, file=stat_upload, file_type='stat', country=country)
        recaps = [File.objects.create(user=user, file=up, file_type='recap', country=country)
                  for up in recap_uploads]
        session = ImportSession.objects.create(
            user=user, country=country, stat_file=stat, recap_file=recaps[0],
            status=ImportSession.Status.PENDING,
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

    stat_file = session.stat_file
    recap_files = list(session.recap_files.all().order_by('pk')) or [session.recap_file]
    try:
        stat = sources.load_stat(stat_file.file.path, _display_name(stat_file), sheet)
        recap = sources.load_recaps([(f.file.path, _display_name(f)) for f in recap_files])
        result = engine.reconcile(stat, recap)
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
        return _fail(session, "Erreur inattendue pendant le rapprochement. Les fichiers sont conservés ; "
                              "contactez l'administrateur si le problème persiste.")

    content = report.build_report(result, {
        'session_id': session.pk,
        'country': str(session.country),
        'user': session.uploaded_by_name,
        'sheet': sheet,
        'date': timezone.localtime().strftime('%d/%m/%Y %H:%M'),
    })
    session.error_file.save(f"rapport_rapprochement_session_{session.pk}.xlsx", ContentFile(content), save=False)

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
