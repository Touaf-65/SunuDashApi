"""
Modèle métier des sinistres (lot I3, décisions des 08 et 09/10/2026, voir JOURNAL_DES_CHANGEMENTS.md § 9).

- Tout est cloisonné par pays : les référentiels (employeurs, polices, assurés, partenaires, opérateurs, factures,
  paiements) sont uniques **dans un pays** grâce à une clé normalisée (`*_key`), jamais par un nom brut.
- Un sinistre (en-tête) porte ses **lignes d'actes**, qui portent les montants ; les totaux du sinistre sont recopiés
  sur l'en-tête pour les tableaux de bord.
- Le rôle d'un assuré (principal / conjoint / enfant) est porté **uniquement** par son adhésion à une police
  (InsuredEmployer) : une même personne peut être enfant sur une police et principale sur une autre.
- La « famille d'acte » des fichiers est un libellé de garantie, gardé sur la ligne ; l'acte est rattaché à sa
  catégorie principale, et ses variantes d'écriture passent par la table d'alias (ActAlias).
"""
from django.conf import settings
from django.db import models
from django.db.models import Q

from countries.models import Country
from file_handling.models import File, ImportSession


class Client(models.Model):
    """Employeur : groupe d'assurés tel qu'il figure dans les fichiers (« CEET », « CEET / RETRAITES »)."""
    id = models.AutoField(primary_key=True)
    contact = models.CharField(max_length=255, null=True, blank=True)
    creation_date = models.DateTimeField(blank=True, null=True)
    modification_date = models.DateTimeField(blank=True, null=True)
    name = models.CharField(max_length=255)
    name_key = models.CharField(max_length=255, default='', db_index=True)
    country = models.ForeignKey(Country, on_delete=models.CASCADE, related_name='clients')
    # Prime : encore portée par l'employeur (import des primes) ; passera sur la police (décision L)
    prime = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    file = models.ForeignKey(File, on_delete=models.SET_NULL, null=True, blank=True, related_name='clients')
    import_session = models.ForeignKey(ImportSession, on_delete=models.SET_NULL, null=True, blank=True, related_name='imported_clients')

    class Meta:
        constraints = [models.UniqueConstraint(fields=['country', 'name_key'], name='client_unique_per_country')]

    def __str__(self):
        return self.name

    def update_prime(self, new_prime):
        ClientPrimeHistory.objects.create(client=self, prime=self.prime)
        self.prime = new_prime
        self.save()


class ClientPrimeHistory(models.Model):
    client = models.ForeignKey(Client, on_delete=models.CASCADE, related_name='prime_history')
    prime = models.DecimalField(max_digits=10, decimal_places=2)  # valeur historisée du champ prime
    date = models.DateTimeField(auto_now_add=True)  # date de modification du champ prime

    def __str__(self):
        return f"{self.client.name} - {self.date}"


class Subscriber(models.Model):
    """Souscripteur d'une police : une entreprise, ou un particulier qui assure sa famille."""
    class Kind(models.TextChoices):
        COMPANY = 'COMPANY', 'Entreprise'
        INDIVIDUAL = 'INDIVIDUAL', 'Particulier'

    country = models.ForeignKey(Country, on_delete=models.CASCADE, related_name='subscribers')
    kind = models.CharField(max_length=12, choices=Kind.choices)
    name = models.CharField(max_length=255)
    name_key = models.CharField(max_length=255, db_index=True)
    # Particulier : la personne assurée qui a souscrit
    insured = models.ForeignKey('Insured', on_delete=models.SET_NULL, null=True, blank=True, related_name='subscriptions')
    creation_date = models.DateTimeField(auto_now_add=True)
    import_session = models.ForeignKey(ImportSession, on_delete=models.SET_NULL, null=True, blank=True, related_name='imported_subscribers')

    class Meta:
        constraints = [models.UniqueConstraint(fields=['country', 'kind', 'name_key'], name='subscriber_unique_per_country')]

    def __str__(self):
        return self.name


class RateSource(models.TextChoices):
    OBSERVED = 'OBSERVED', "Observé à l'import"
    MANUAL = 'MANUAL', "Saisi par l'admin territorial"


class Policy(models.Model):
    """Police : un souscripteur peut en avoir plusieurs ; une police peut couvrir plusieurs employeurs.
    Deux numéros qui ne diffèrent que par l'année sont deux polices distinctes (décision J)."""
    id = models.AutoField(primary_key=True)
    country = models.ForeignKey(Country, on_delete=models.CASCADE, related_name='policies')
    policy_number = models.CharField(max_length=255)
    number_key = models.CharField(max_length=255, db_index=True)
    subscriber = models.ForeignKey(Subscriber, on_delete=models.SET_NULL, null=True, blank=True, related_name='policies')
    employers = models.ManyToManyField(Client, blank=True, related_name='policies')
    # Taux de couverture par défaut (0,80 = 80 %) ; un plan de garanties peut le remplacer
    coverage_rate = models.DecimalField(max_digits=5, decimal_places=4, null=True, blank=True)
    coverage_rate_source = models.CharField(max_length=10, choices=RateSource.choices, blank=True, default='')
    creation_date = models.DateTimeField(auto_now_add=True)
    import_session = models.ForeignKey(ImportSession, on_delete=models.SET_NULL, null=True, blank=True, related_name='imported_policies')

    class Meta:
        constraints = [models.UniqueConstraint(fields=['country', 'number_key'], name='policy_unique_per_country')]

    def __str__(self):
        return self.policy_number

    @property
    def client(self):
        """Employeur principal (le premier enregistré), pour l'affichage. Une police peut en avoir plusieurs :
        voir `employers` (utiliser prefetch_related('employers') dans les listes)."""
        employers = sorted(self.employers.all(), key=lambda e: e.pk)
        return employers[0] if employers else None


class GuaranteePlan(models.Model):
    """Plan (collège) de garanties d'une police : colonne « Acte_Contraté_Assuré » (« SUNU IARD Cadres »)."""
    policy = models.ForeignKey(Policy, on_delete=models.CASCADE, related_name='plans')
    label = models.CharField(max_length=255)
    label_key = models.CharField(max_length=255)
    coverage_rate = models.DecimalField(max_digits=5, decimal_places=4, null=True, blank=True)
    coverage_rate_source = models.CharField(max_length=10, choices=RateSource.choices, blank=True, default='')
    import_session = models.ForeignKey(ImportSession, on_delete=models.SET_NULL, null=True, blank=True, related_name='imported_plans')

    class Meta:
        constraints = [models.UniqueConstraint(fields=['policy', 'label_key'], name='plan_unique_per_policy')]

    def __str__(self):
        return self.label


class Insured(models.Model):
    """Personne assurée (principal ou ayant droit). Son rôle est porté par ses adhésions (InsuredEmployer)."""
    id = models.AutoField(primary_key=True)
    country = models.ForeignKey(Country, on_delete=models.CASCADE, related_name='insureds')
    name = models.CharField(max_length=255)
    # Nom sans accents ni casse, mots triés : « LOGO AMEVI » = « AMEVI LOGO »
    name_key = models.CharField(max_length=255, db_index=True)
    # Autres écritures rencontrées pour cette personne (ordre des mots, colonne « Assuré principal »…)
    other_names = models.JSONField(default=list, blank=True)
    # Identifiant de l'assuré (colonne Broker_SunuId), prioritaire quand il est présent
    card_number = models.CharField(max_length=255, null=True, blank=True)
    birth_date = models.DateField(null=True, blank=True)
    phone_number = models.CharField(max_length=20, null=True, blank=True)
    email = models.EmailField(max_length=255, null=True, blank=True)
    consumption_limit = models.FloatField(null=True, blank=True)
    # Principal créé d'après la colonne « Assuré principal » de ses ayants droit, sans consommation propre
    is_deduced = models.BooleanField(default=False)
    creation_date = models.DateTimeField(auto_now_add=True)
    modification_date = models.DateTimeField(auto_now=True)
    import_session = models.ForeignKey(ImportSession, on_delete=models.SET_NULL, null=True, blank=True, related_name='imported_insureds')

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['country', 'card_number'], condition=Q(card_number__isnull=False),
                                    name='insured_card_unique_per_country'),
        ]

    def __str__(self):
        return f'{self.name}'

    def get_primary_for_employer(self, employer):
        link = self.insured_clients.filter(employer=employer).first()
        return link.primary_insured_ref if link else None


class InsuredEmployer(models.Model):
    """Adhésion : un assuré sur une police, chez un employeur (vide pour un particulier), avec son rôle."""
    insured = models.ForeignKey('Insured', on_delete=models.CASCADE, related_name='insured_clients')
    policy = models.ForeignKey('Policy', on_delete=models.CASCADE, related_name='insured_employers')
    employer = models.ForeignKey('Client', on_delete=models.CASCADE, null=True, blank=True, related_name='client_insureds')
    plan = models.ForeignKey(GuaranteePlan, on_delete=models.SET_NULL, null=True, blank=True, related_name='members')
    import_session = models.ForeignKey(ImportSession, on_delete=models.SET_NULL, null=True, blank=True, related_name='imported_insured_employers')

    ROLE_CHOICES = (
        ('primary', 'Assuré principal'),
        ('spouse', 'Conjoint(e)'),
        ('child', 'Enfant'),
        ('other', 'Autre'),
    )
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default='primary')

    primary_insured_ref = models.ForeignKey(
        'Insured',
        null=True, blank=True,
        on_delete=models.SET_NULL,
        related_name='dependents_in_clients',
        help_text="Renseigner si l’assuré est conjoint ou enfant."
    )

    # Première et dernière consommation observées sur cette adhésion
    start_date = models.DateField(null=True, blank=True)
    end_date = models.DateField(null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['insured', 'policy', 'employer'], nulls_distinct=False,
                                    name='membership_unique'),
        ]

    def __str__(self):
        where = self.employer.name if self.employer_id else 'particulier'
        return f"{self.insured.name} — {self.policy} ({where}, {self.get_role_display()})"

    def clean(self):
        from django.core.exceptions import ValidationError
        if self.role != 'primary' and not self.primary_insured_ref:
            raise ValidationError("Un assuré dépendant doit avoir un assuré principal référencé.")
        if self.role == 'primary' and self.primary_insured_ref:
            raise ValidationError("Un assuré principal ne peut pas référencer un autre assuré principal.")


class Partner(models.Model):
    """Prestataire de soins."""
    id = models.AutoField(primary_key=True)
    name = models.CharField(max_length=255)
    name_key = models.CharField(max_length=255, db_index=True)
    address = models.CharField(max_length=255, null=True, blank=True)
    contact = models.CharField(max_length=255, null=True, blank=True)
    modification_date = models.DateTimeField(auto_now=True)
    creation_date = models.DateTimeField(auto_now_add=True)
    main_responsible_name = models.CharField(max_length=255, null=True, blank=True)
    country = models.ForeignKey(Country, on_delete=models.CASCADE, related_name='partners')
    import_session = models.ForeignKey(ImportSession, on_delete=models.SET_NULL, null=True, blank=True, related_name='imported_partners')

    class Meta:
        constraints = [models.UniqueConstraint(fields=['country', 'name_key'], name='partner_unique_per_country')]

    def __str__(self):
        return self.name


class Invoice(models.Model):
    """Facture (ou bordereau) d'un prestataire : simple référence, qui peut couvrir plusieurs sinistres.
    Les montants sont sur les lignes d'actes (décision G)."""
    id = models.AutoField(primary_key=True)
    country = models.ForeignKey(Country, on_delete=models.CASCADE, related_name='invoices')
    partner = models.ForeignKey(Partner, on_delete=models.CASCADE, related_name='invoices')
    invoice_number = models.CharField(max_length=255)
    number_key = models.CharField(max_length=255)
    creation_date = models.DateTimeField(auto_now_add=True)
    import_session = models.ForeignKey(ImportSession, on_delete=models.SET_NULL, null=True, blank=True, related_name='imported_invoices')

    class Meta:
        constraints = [models.UniqueConstraint(fields=['country', 'partner', 'number_key'], name='invoice_unique_per_partner')]

    def __str__(self):
        return self.invoice_number


class Payment(models.Model):
    """Règlement (chèque ou virement) à un prestataire ; un règlement couvre souvent plusieurs sinistres."""
    id = models.AutoField(primary_key=True)
    country = models.ForeignKey(Country, on_delete=models.CASCADE, related_name='payments')
    partner = models.ForeignKey(Partner, on_delete=models.CASCADE, related_name='payments')
    reference = models.CharField(max_length=255)
    reference_key = models.CharField(max_length=255)
    payment_date = models.DateField(null=True, blank=True)
    creation_date = models.DateTimeField(auto_now_add=True)
    import_session = models.ForeignKey(ImportSession, on_delete=models.SET_NULL, null=True, blank=True, related_name='imported_payments')

    class Meta:
        constraints = [models.UniqueConstraint(fields=['country', 'partner', 'reference_key'], name='payment_unique_per_partner')]

    def __str__(self):
        return self.reference


class ActCategory(models.Model):
    id = models.AutoField(primary_key=True)
    creation_date = models.DateTimeField(auto_now_add=True)
    modification_date = models.DateTimeField(auto_now=True)
    label = models.CharField(max_length=255)
    label_key = models.CharField(max_length=255, unique=True)

    def __str__(self):
        return self.label


class Act(models.Model):
    """Acte du référentiel commun, rattaché à sa catégorie principale (la ligne garde sa propre catégorie)."""
    id = models.AutoField(primary_key=True)
    creation_date = models.DateTimeField(auto_now_add=True)
    modification_date = models.DateTimeField(auto_now=True)
    label = models.CharField(max_length=255)
    label_key = models.CharField(max_length=255, unique=True)
    category = models.ForeignKey(ActCategory, on_delete=models.PROTECT, related_name='acts')

    def __str__(self):
        return self.label


class ActAlias(models.Model):
    """Variante d'écriture d'un acte -> libellé de l'acte du référentiel
    (« VITAMINES OU FORTIFIANTS » -> « Vitamines / Fortifiants »)."""
    alias_key = models.CharField(max_length=255, unique=True)
    alias_label = models.CharField(max_length=255)
    act_label = models.CharField(max_length=255)

    class Meta:
        verbose_name_plural = 'act aliases'

    def __str__(self):
        return f"{self.alias_label} -> {self.act_label}"


class Operator(models.Model):
    """Gestionnaire qui a saisi le sinistre (colonne « Modifié par »)."""
    id = models.AutoField(primary_key=True)
    name = models.CharField(max_length=255)
    name_key = models.CharField(max_length=255)
    country = models.ForeignKey(Country, on_delete=models.CASCADE, related_name='operators')

    class Meta:
        constraints = [models.UniqueConstraint(fields=['country', 'name_key'], name='operator_unique_per_country')]

    def __str__(self):
        return self.name


class ClaimStatus(models.TextChoices):
    SETTLED = 'S', 'Réglé'
    CANCELLED = 'C', 'Annulé'


class Claim(models.Model):
    """Sinistre (en-tête). Numéro unique dans un pays ; totaux = somme des lignes d'actes, dans `currency`."""
    StatusEnum = ClaimStatus

    id = models.BigAutoField(primary_key=True)
    country = models.ForeignKey(Country, on_delete=models.CASCADE, related_name='claims')
    number = models.CharField(max_length=255)
    status = models.CharField(max_length=1, choices=ClaimStatus.choices, default=ClaimStatus.SETTLED)
    # Date et heure (minuit) plutôt que date seule : les tableaux de bord travaillent en datetime
    claim_date = models.DateTimeField(null=True, blank=True)    # date du sinistre (des soins)
    settlement_date = models.DateTimeField()                    # date de règlement (la plus récente des lignes)
    insured = models.ForeignKey(Insured, on_delete=models.PROTECT, related_name='claims')
    policy = models.ForeignKey(Policy, on_delete=models.PROTECT, related_name='claims')
    employer = models.ForeignKey(Client, on_delete=models.PROTECT, null=True, blank=True, related_name='claims')
    membership = models.ForeignKey(InsuredEmployer, on_delete=models.PROTECT, related_name='claims')
    partner = models.ForeignKey(Partner, on_delete=models.PROTECT, related_name='claims')
    operator = models.ForeignKey(Operator, on_delete=models.SET_NULL, null=True, blank=True, related_name='claims')
    payment = models.ForeignKey(Payment, on_delete=models.SET_NULL, null=True, blank=True, related_name='claims')
    currency = models.CharField(max_length=3)
    # Totaux recopiés des lignes (qui portent les montants exacts) ; en flottant comme les anciens montants de
    # facture, sur lesquels les calculs des tableaux de bord sont écrits
    claimed_amount = models.FloatField(default=0)
    reimbursed_amount = models.FloatField(default=0)
    lines_count = models.PositiveIntegerField(default=0)
    note = models.TextField(blank=True, default='')
    creation_date = models.DateTimeField(auto_now_add=True)
    import_session = models.ForeignKey(ImportSession, on_delete=models.SET_NULL, null=True, blank=True, related_name='imported_claims')

    class Meta:
        constraints = [models.UniqueConstraint(fields=['country', 'number'], name='claim_unique_per_country')]
        indexes = [models.Index(fields=['country', 'settlement_date'], name='claim_country_settled_idx')]

    def __str__(self):
        return f'Claim {self.number}'


class ClaimLine(models.Model):
    """Ligne d'acte d'un sinistre, telle que dans le fichier statistique (une ligne = un acte).
    Les lignes strictement identiques sont gardées : actes répétés légitimes."""
    claim = models.ForeignKey(Claim, on_delete=models.CASCADE, related_name='lines')
    line_number = models.PositiveIntegerField()
    category = models.ForeignKey(ActCategory, on_delete=models.PROTECT, related_name='claim_lines')
    act = models.ForeignKey(Act, on_delete=models.PROTECT, null=True, blank=True, related_name='claim_lines')
    # Libellé de garantie (colonne « Famille Acte »), gardé tel quel
    guarantee_label = models.CharField(max_length=500, blank=True, default='')
    invoice = models.ForeignKey(Invoice, on_delete=models.SET_NULL, null=True, blank=True, related_name='claim_lines')
    status = models.CharField(max_length=1, choices=ClaimStatus.choices, default=ClaimStatus.SETTLED)
    settlement_date = models.DateField()
    currency = models.CharField(max_length=3)
    claimed_amount = models.DecimalField(max_digits=16, decimal_places=2)
    reimbursed_amount = models.DecimalField(max_digits=16, decimal_places=2)
    operator = models.ForeignKey(Operator, on_delete=models.SET_NULL, null=True, blank=True, related_name='claim_lines')
    note = models.TextField(blank=True, default='')

    class Meta:
        constraints = [models.UniqueConstraint(fields=['claim', 'line_number'], name='claim_line_unique')]
        ordering = ['claim_id', 'line_number']

    def __str__(self):
        return f'{self.claim.number} #{self.line_number}'


class FamilyChange(models.Model):
    """Correction d'une famille faite par l'admin territorial ou le chef de département technique (lot F1) :
    trace de qui a changé quoi, affichée sur la fiche des familles concernées."""
    class Action(models.TextChoices):
        ATTACH = 'ATTACH', 'Rattachement à un autre principal'
        ROLE = 'ROLE', 'Changement de rôle'
        MERGE = 'MERGE', 'Fusion de deux fiches'
        RENAME = 'RENAME', 'Nom retenu'

    country = models.ForeignKey(Country, on_delete=models.CASCADE, related_name='family_changes')
    policy = models.ForeignKey(Policy, on_delete=models.SET_NULL, null=True, blank=True, related_name='family_changes')
    # Assurés principaux des familles touchées (avant et après), pour retrouver l'historique d'une famille
    principals = models.JSONField(default=list, blank=True)
    insured = models.ForeignKey(Insured, on_delete=models.SET_NULL, null=True, blank=True, related_name='family_changes')
    action = models.CharField(max_length=10, choices=Action.choices)
    summary = models.TextField()
    details = models.JSONField(default=dict, blank=True)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
                             related_name='family_changes')
    user_name = models.CharField(max_length=255, blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at', '-id']

    def __str__(self):
        return f'{self.get_action_display()} — {self.summary}'
