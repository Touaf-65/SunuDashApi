"""
Tâches Celery de l'import des sinistres (lot I4) : rapprochement et écriture en base d'une session, lancés par
analysis_service.queue_analyse() / queue_import(). En local, CELERY_TASK_ALWAYS_EAGER=True les exécute sur place.
"""
import logging

from celery import shared_task

from file_handling.models import ImportSession

logger = logging.getLogger(__name__)


def _session(session_id, step):
    """Session encore en attente de cette étape (supprimée ou déjà traitée entre-temps : None)."""
    session = ImportSession.objects.select_related('country', 'stat_file', 'recap_file').filter(pk=session_id).first()
    if session is None or session.status != ImportSession.Status.PROCESSING or session.step != step:
        logger.info("Session %s : plus rien à faire pour l'étape %s", session_id, step)
        return None
    return session


@shared_task(name='importer.analyse_session')
def analyse_session(session_id, sheet=None):
    from importer.services import analysis_service
    session = _session(session_id, 'ANALYSE')
    if session is not None:
        analysis_service.analyse(session, sheet)


@shared_task(name='importer.import_session')
def import_session(session_id):
    from importer.services import analysis_service
    session = _session(session_id, 'IMPORT')
    if session is not None:
        analysis_service.import_claims(session)
