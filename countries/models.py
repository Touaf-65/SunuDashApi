from django.db import models


class Country(models.Model):
    name = models.CharField(max_length=100, unique=True)
    code = models.CharField(max_length=4, unique=True)
    currency_code = models.CharField(max_length=10, null=True, blank=True, default='XOF')  # ISO 4217
    currency_name = models.CharField(max_length=50, null=True, blank=True, default='F CFA')
    is_active = models.BooleanField(default=True)  # pour masquer/activer un pays

    def __str__(self):
        return f"{self.name} ({self.currency_code})"
