from celery import shared_task
import pandas as pd
from .services.data_mapper import DataMapper
from file_handling.models import ImportSession
from django.utils import timezone
from django.core.exceptions import ValidationError

@shared_task
def async_import_data(stat_data_dict, import_session_id):
    import_session = ImportSession.objects.filter(id=import_session_id).first()
    
    if not import_session:
        return

    try:
        df_stat = pd.DataFrame(stat_data_dict)

        mapper = DataMapper(df_stat=df_stat, import_session=import_session)
        mapper.map_data()  

        import_session.status = ImportSession.Status.COMPLETED
        import_session.completed_at = timezone.now()
        import_session.save()

    except ValidationError as ve:
        import_session.status = ImportSession.Status.FAILED
        import_session.error_report = f"Erreur de validation : {str(ve)}"
        import_session.completed_at = timezone.now()
        import_session.save()

    except Exception as e:
        import_session.status = ImportSession.Status.FAILED
        import_session.error_report = f"Erreur inattendue : {str(e)}"
        import_session.completed_at = timezone.now()
        import_session.save()
        raise e  