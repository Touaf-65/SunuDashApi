import os
from django.db import models
from django.contrib.auth import get_user_model
from countries.models import Country

User = get_user_model()

class File(models.Model):
    FILE_TYPE_CHOICES = [
        ('stat', 'Fichier Statistique'),
        ('recap', 'Fichier Récap'),
    ]

    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    uploaded_by_name = models.CharField(max_length=255, blank=True)
    uploaded_by_email = models.EmailField(blank=True, null=True)


    file = models.FileField(upload_to='uploads/')
    file_name = models.CharField(max_length=255)
    file_type = models.CharField(max_length=5, choices=FILE_TYPE_CHOICES)
    uploaded_at = models.DateTimeField(auto_now_add=True)
    size = models.CharField(max_length=20, editable=False)
    country = models.ForeignKey(Country, on_delete=models.CASCADE, null=True, blank=True)

    def save(self, *args, **kwargs):
        if not self.file_name:
            filename = os.path.splitext(self.file.name)[0]
            self.file_name = filename
        
        if not self.country and self.user and hasattr(self.user, 'country'):
            self.country = self.user.country
        
        if self.user:
            if not self.uploaded_by_name:
                full_name = f"{self.user.first_name} {self.user.last_name}".strip()
                self.uploaded_by_name = full_name or self.user.email
            if not self.uploaded_by_email:
                self.uploaded_by_email = self.user.email
        
        self.size = self.format_size(self.file.size)
        
        super().save(*args, **kwargs)

    def format_size(self, size):
        for unit in ['', 'K', 'M', 'G', 'T', 'P', 'E', 'Z']:
            if size < 1024:
                return f"{size:.2f} {unit}o"
            size /= 1024
        return f"{size:.2f} Yo"

    def __str__(self):
        return self.file.name




class ImportSession(models.Model):
    """
    Represents a session that links a statistical and a recap file together,
    tracks the processing status, and stores the final result or error report.
    """
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('processing', 'Processing'),
        ('done', 'Done'),
        ('error', 'Error'),
        ('done_with_errors', 'Done with Errors'),
    ]

    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    uploaded_by_name = models.CharField(max_length=255, blank=True)
    uploaded_by_email = models.EmailField(blank=True, null=True)

    country = models.ForeignKey(Country, on_delete=models.CASCADE)
    stat_file = models.ForeignKey(File, on_delete=models.CASCADE, related_name='stat_sessions')
    recap_file = models.ForeignKey(File, on_delete=models.CASCADE, related_name='recap_sessions')
    
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    created_at = models.DateTimeField(auto_now_add=True)
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    
    error_file = models.FileField(upload_to='error_reports/', null=True, blank=True)
    message = models.TextField(null=True, blank=True)

    insured_created_count = models.IntegerField(default=0)
    claims_created_count = models.IntegerField(default=0)
    total_claimed_amount = models.DecimalField(max_digits=18, decimal_places=2, default=0)
    total_reimbursed_amount = models.DecimalField(max_digits=18, decimal_places=2, default=0)


    def __str__(self):
        return f"ImportSession {self.pk} ({self.country.name}) - {self.status}"
    def save(self, *args, **kwargs):
        if not self.country and self.user and hasattr(self.user, 'country'):
            self.country = self.user.country
        if self.user:
            if not self.uploaded_by_name:
                full_name = f"{self.user.first_name} {self.user.last_name}".strip()
                self.uploaded_by_name = full_name or self.user.email
            if not self.uploaded_by_email:
                self.uploaded_by_email = self.user.email
        