from django.db import models
from django.db.models.functions import Lower, Trim


class Country(models.Model):
    name = models.CharField(max_length=100, unique=True)
    code = models.CharField(max_length=4, unique=True)
    currency_code = models.CharField(max_length=10, null=True, blank=True, default='XOF')  # ISO 4217
    currency_name = models.CharField(max_length=50, null=True, blank=True, default='F CFA')
    is_active = models.BooleanField(default=True)  # pour masquer/activer un pays

    class Meta:
        # Unicité sans tenir compte de la casse ni des espaces de début/fin, garantie
        # par la base elle-même (« togo » ou « Togo  » ne peuvent pas coexister avec
        # « TOGO », même hors de l'API : admin Django, scripts, SQL direct).
        # unique=True ci-dessus est sensible à la casse et aux espaces.
        constraints = [
            models.UniqueConstraint(
                Lower(Trim('name')), name='country_name_unique_ci',
                violation_error_message="Un pays avec ce nom existe déjà.",
            ),
            models.UniqueConstraint(
                Lower(Trim('code')), name='country_code_unique_ci',
                violation_error_message="Un pays avec ce code existe déjà.",
            ),
        ]

    def __str__(self):
        return f"{self.name} ({self.currency_code})"


class CountryDeactivationRequest(models.Model):
    """
    Demande de désactivation d'un pays par un ADMIN_GLOBAL, avec motif obligatoire.

    La désactivation n'est appliquée qu'au quorum de validations des ADMIN_GLOBAL
    (le demandeur compte comme une validation) : 2 s'il y a au plus 3 ADMIN_GLOBAL
    actifs à la création de la demande, 3 au-delà. Le SUPERUSER peut trancher à tout
    moment (valider = désactiver, refuser = clore). Une demande expire après 7 jours.
    """
    class Status(models.TextChoices):
        PENDING = 'PENDING', 'En attente'
        APPROVED = 'APPROVED', 'Validée (pays désactivé)'
        REJECTED = 'REJECTED', 'Refusée'
        EXPIRED = 'EXPIRED', 'Expirée'
        CANCELLED = 'CANCELLED', 'Annulée'

    country = models.ForeignKey(Country, on_delete=models.CASCADE, related_name='deactivation_requests')
    requested_by = models.ForeignKey('users.CustomUser', on_delete=models.SET_NULL, null=True,
                                     related_name='country_deactivation_requests')
    reason = models.TextField()
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.PENDING)
    # Figés à la création : nombre d'ADMIN_GLOBAL actifs et quorum correspondant
    eligible_voters = models.PositiveSmallIntegerField()
    required_approvals = models.PositiveSmallIntegerField()
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    decided_at = models.DateTimeField(null=True, blank=True)
    decided_by = models.ForeignKey('users.CustomUser', on_delete=models.SET_NULL, null=True, blank=True,
                                   related_name='+')

    class Meta:
        ordering = ['-created_at']
        constraints = [
            # Une seule demande en attente par pays
            models.UniqueConstraint(fields=['country'], condition=models.Q(status='PENDING'),
                                    name='one_pending_deactivation_per_country'),
        ]

    def __str__(self):
        return f"Désactivation {self.country.name} ({self.get_status_display()})"


class CountryDeactivationVote(models.Model):
    """Validation ou refus d'une demande de désactivation par un ADMIN_GLOBAL."""
    class Decision(models.TextChoices):
        APPROVE = 'APPROVE', 'Validation'
        REJECT = 'REJECT', 'Refus'

    request = models.ForeignKey(CountryDeactivationRequest, on_delete=models.CASCADE, related_name='votes')
    admin = models.ForeignKey('users.CustomUser', on_delete=models.CASCADE, related_name='+')
    decision = models.CharField(max_length=7, choices=Decision.choices)
    comment = models.TextField(blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['created_at']
        constraints = [
            models.UniqueConstraint(fields=['request', 'admin'], name='one_vote_per_admin_per_request'),
        ]
