from django.db import transaction
from django.forms import ValidationError
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

from importer.tasks import async_import_data 


User = get_user_model()

class ImporterService:
    def __init__(self, user, country, stat_file, recap_file):
        self.user = user
        self.country = country
        self.stat_file = stat_file
        self.recap_file = recap_file
        self.import_session = None
        self.df_stat = None
        self.df_recap = None
        self.cleaned_stat = None
        self.valid_data = None
        self.invalid_data = None
        self.errors = []
        self.common_range = None

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
    
    def get_common_range(self):
        comparator = ComparisonService()
        self.common_range = comparator.get_common_date(self.df_stat, self.df_recap)
        
        if not self.common_range:
            self.import_session.status = ImportSession.status.error
            self.import_session.save()
            raise ValidationError("Aucune période commune entre les fichiers stat et recap. Import annulé.")

        self.import_session.start_date = self.common_range[0]
        self.import_session.end_date = self.common_range[1]
        self.import_session.save()

    def compare_data(self):
        comparator = ComparisonService()
        compared_df = comparator.compare_dataframes(
            self.cleaned_stat,
            self.cleaned_recap,
            self.common_range
        )

        self.invalid_data, self.valid_data = comparator.extract_non_conformity(compared_df)

        if self.invalid_data.empty:
            self.import_session.status = 'completed'
            self.import_session.save()
            return True
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
        async_import_data.delay(
            self.valid_data.to_dict(orient='records'),
            self.import_session.id
        )


    def run(self):
        self.create_import_session_and_files()
        self.open_files()
        self.clean_data()
        self.get_common_range()
        is_valid = self.compare_data()

        if not is_valid:
            return False

        self.trigger_async_import()
        return True