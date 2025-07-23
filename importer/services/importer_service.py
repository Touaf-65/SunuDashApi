from django.db import transaction
import pandas as pd
from file_handling.models import File, ImportSession
from core.models import ( Client, Policy, Insured, InsuredEmployer, Invoice,
    Act, ActFamily, ActCategory, Operator, Claim, Partner, PaymentMethod )
from countries.models import Country
from django.contrib.auth import get_user_model
from django.db.models import Q
from .cleaning_service import CleaningService
from .comparison_service import ComparisonService
from django.utils import timezone

#from importer.tasks import async_import_data  # tâche celery


User = get_user_model()

class ImporterService:
    def __init__(self, user, country, stat_file, recap_file):
        self.user = user
        self.country = country
        self.stat_file = stat_file
        self.recap_file = recap_file
        self.import_session = None
        self.file_stat = None
        self.file_recap = None
        self.df_stat = None
        self.df_recap = None
        self.cleaned_stat = None
        self.cleaned_recap = None
        self.valid_stat = None
        self.valid_recap = None
        self.errors = []

    def create_import_session_and_files(self):
        self.import_session = ImportSession.objects.create(
            user=self.user,
            country=self.country,
            status='pending',
            started_at=timezone.now()
        )

        self.file_stat = File.objects.create(
            file=self.stat_file,
            file_type='stat',
            user=self.user,
            import_session=self.import_session
        )
        self.file_recap = File.objects.create(
            file=self.recap_file,
            file_type='recap',
            user=self.user,
            import_session=self.import_session
        )

    def open_files(self):
        self.df_stat = pd.read_excel(self.file_stat.file.path)
        self.df_recap = pd.read_excel(self.file_recap.file.path)

    def clean_data(self):
        cleaner = CleaningService()
        self.cleaned_stat = cleaner.clean_dataframe(self.df_stat)
        self.cleaned_recap = cleaner.clean_dataframe(self.df_recap)

    def compare_data(self):
        comparator = ComparisonService()
        self.valid_stat, self.valid_recap, self.errors = comparator.compare_dataframes(
            self.cleaned_stat,
            self.cleaned_recap
        )

        if self.errors:
            error_path = comparator.generate_error_report(self.errors, self.import_session.id)
            self.import_session.status = 'completed_with_errors'
            self.import_session.error_report.name = error_path
            self.import_session.save()
            return False
        return True

    def trigger_async_import(self):
        self.import_session.status = 'processing'
        self.import_session.save()
        # async_import_data.delay(
        #     self.valid_stat.to_dict(orient='records'),
        #     self.valid_recap.to_dict(orient='records'),
        #     self.import_session.id
        # )

    def run(self):
        self.create_import_session_and_files()
        self.open_files()
        self.clean_data()
        is_valid = self.compare_data()

        if not is_valid:
            return False

        self.trigger_async_import()
        return True




"""
je comprend un peu mieux maintenant merci. on va d'abord terminer la mise en place de ImporterService.
rendons le modulaire. genre une methode pour l'enregistrement des fichiers et la session d'import, une pour l'ouverture des fichiers, une autre pour la nettoyage des fichiers,
une autre pour la comparaison des fichiers, et une autre pour l'insertion des données.
et enfin la methode run qui va orchestrer toutes ces autres methodes.

n'est-ce pas une bonne approche ?

from importer.services.cleaning import CleaningService
from importer.services.comparison import ComparisonService
from file_handling.models import ImportSession, File
from django.utils import timezone
from importer.tasks import async_import_data  # tâche celery

class ImporterService:
    def __init__(self, user, country, stat_file, recap_file):
        self.user = user
        self.country = country
        self.stat_file = stat_file
        self.recap_file = recap_file
        self.import_session = None

    def run_import(self):
        # 1. Créer une ImportSession
        self.import_session = ImportSession.objects.create(
            user=self.user,
            country=self.country,
            status='pending',
            started_at=timezone.now()
        )

        # 2. Sauvegarder les fichiers liés
        file_stat = File.objects.create(
            file=self.stat_file,
            file_type='stat',
            user=self.user,
            import_session=self.import_session
        )
        file_recap = File.objects.create(
            file=self.recap_file,
            file_type='recap',
            user=self.user,
            import_session=self.import_session
        )

        # 3. Nettoyage
        cleaner = CleaningService()
        df_stat_clean, df_recap_clean = cleaner.clean_files(file_stat.file.path, file_recap.file.path)

        # 4. Comparaison / Validation
        comparator = ComparisonService()
        valid_stat_df, valid_recap_df, errors = comparator.compare_dataframes(df_stat_clean, df_recap_clean)

        if errors:
            # Générer fichier d'erreur
            error_file_path = comparator.generate_error_report(errors, self.import_session.id)
            self.import_session.status = 'completed_with_errors'
            self.import_session.error_report.name = error_file_path
            self.import_session.save()
            return False  # Stop là pour consultation

        # 5. Lancer tâche d'import asynchrone
        self.import_session.status = 'processing'
        self.import_session.save()

        async_import_data.delay(valid_stat_df.to_dict(), valid_recap_df.to_dict(), self.import_session.id)

        return True

    """