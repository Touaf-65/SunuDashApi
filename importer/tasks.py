from celery import shared_task
import pandas as pd
from .services.data_mapper import DataMapper
from file_handling.models import ImportSession
from django.utils import timezone
from django.core.exceptions import ValidationError
from importer.services.logging_service import ImportLoggerService
import logging
logger = logging.getLogger(__name__)

@shared_task
def async_import_data(stat_data_dict, import_session_id):
    logger = logging.getLogger(__name__)
    logger.info(f"Début du traitement de la tâche d'import pour la session {import_session_id}")
    
    import_session = ImportSession.objects.filter(id=import_session_id).first()
    
    if not import_session:
        logger.error(f"Aucune session d'import trouvée avec l'ID {import_session_id}")
        return

    # Initialisation du logger spécifique pour cette tâche
    import_logger = None
    
    try:
        import_logger = ImportLoggerService(import_session_id)
        import_logger.log_step_start("DÉBUT DE LA TÂCHE CELERY D'IMPORT")
        import_logger.log_info("Initialisation de la tâche", {
            "session_id": import_session_id,
            "nombre_enregistrements": len(stat_data_dict)
        })
        
        df_stat = pd.DataFrame(stat_data_dict)
        import_logger.log_info(f"DataFrame créé avec succès", {
            "lignes": len(df_stat),
            "colonnes": len(df_stat.columns)
        })
        
        mapper = DataMapper(df_stat=df_stat, import_session=import_session)
        import_logger.log_info("DataMapper initialisé, début du mapping")
        
        mapper.map_data()
        
        import_session.refresh_from_db()
        import_session.status = ImportSession.Status.DONE
        import_session.completed_at = timezone.now()
        import_session.save()
        
        import_logger.log_info("✅ TÂCHE CELERY TERMINÉE AVEC SUCCÈS", {
            "session_id": import_session_id,
            "statut_final": "DONE",
            "heure_fin": timezone.now().isoformat()
        })
        
    except ValidationError as ve:
        if import_logger:
            import_logger.log_error("Erreur de validation dans la tâche Celery", exception=ve)
        
        import_session.status = ImportSession.Status.ERROR
        import_session.error_report = f"Erreur de validation : {str(ve)}"
        import_session.completed_at = timezone.now()
        import_session.save()
        
    except Exception as e:
        if import_logger:
            import_logger.log_critical("Erreur critique dans la tâche Celery", exception=e)
        
        import_session.status = ImportSession.Status.ERROR
        import_session.error_report = f"Erreur inattendue : {str(e)}"
        import_session.completed_at = timezone.now()
        import_session.save()
        raise e
        
    finally:
        if import_logger:
            import_logger.close()
