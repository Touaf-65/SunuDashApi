from django.db import models
from countries.models import Country
from file_handling.models import File, ImportSession


class Client(models.Model):
    id = models.AutoField(primary_key=True)
    contact = models.CharField(max_length=255, null=True, blank=True)
    creation_date = models.DateTimeField(auto_now_add=True)
    modification_date = models.DateTimeField(auto_now=True)
    name = models.CharField(max_length=255)
    country = models.ForeignKey(Country, on_delete=models.CASCADE, related_name='clients')
    prime = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    file = models.ForeignKey(File, on_delete=models.SET_NULL, null=True, blank=True, related_name='clients')
    import_session = models.ForeignKey(ImportSession, on_delete=models.SET_NULL, null=True, blank=True, related_name='imported_clients')

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


class Policy(models.Model):
    id = models.AutoField(primary_key=True)
    creation_date = models.DateTimeField(auto_now_add=True)
    policy_number = models.CharField(max_length=255)
    client = models.ForeignKey(Client, on_delete=models.CASCADE, related_name='policies')
    file = models.ForeignKey(File, on_delete=models.SET_NULL, null=True, blank=True, related_name='policies')
    import_session = models.ForeignKey(ImportSession, on_delete=models.SET_NULL, null=True, blank=True, related_name='imported_policies')

    def __str__(self):
        return self.policy_number


class Insured(models.Model):
    id = models.AutoField(primary_key=True)
    name = models.CharField(max_length=255)
    birth_date = models.DateField(null=True, blank=True)
    creation_date = models.DateTimeField(auto_now_add=True)
    modification_date = models.DateTimeField(auto_now=True)
    card_number = models.CharField(max_length=255, null=True, blank=True)
    phone_number = models.CharField(max_length=20, null=True, blank=True)
    email = models.EmailField(max_length=255, null=True, blank=True)
    consumption_limit = models.FloatField(null=True, blank=True)
    is_primary_insured = models.BooleanField(default=False)
    is_child = models.BooleanField(default=False)
    is_spouse = models.BooleanField(default=False)
    primary_insured = models.ForeignKey('self', null=True, blank=True, on_delete=models.SET_NULL, related_name='dependents')
    file = models.ForeignKey(File, on_delete=models.SET_NULL, null=True, blank=True, related_name='insureds')
    import_session = models.ForeignKey(ImportSession, on_delete=models.SET_NULL, null=True, blank=True, related_name='imported_insureds')

    def __str__(self):
        return f'{self.name}'

    def get_primary_for_employer(self, employer):
        try:
            link = self.insured_employers.get(employer=employer)
            return link.primary_insured_ref
        except InsuredEmployer.DoesNotExist:
            return None


class InsuredEmployer(models.Model):
    insured = models.ForeignKey('Insured', on_delete=models.CASCADE, related_name='insured_clients')
    employer = models.ForeignKey('Client', on_delete=models.CASCADE, related_name='client_insureds')
    policy = models.ForeignKey('Policy', on_delete=models.CASCADE, related_name='insured_employers')
    file = models.ForeignKey(File, on_delete=models.SET_NULL, null=True, blank=True, related_name='insured_employers')
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

    start_date = models.DateField(null=True, blank=True)
    end_date = models.DateField(null=True, blank=True)

    class Meta:
        unique_together = ('insured', 'employer', 'policy')

    def __str__(self):
        return f"{self.insured.name} chez {self.employer.name} ({self.get_role_display()})"

    def clean(self):
        from django.core.exceptions import ValidationError
        if self.role != 'primary' and not self.primary_insured_ref:
            raise ValidationError("Un assuré dépendant doit avoir un assuré principal référencé.")
        if self.role == 'primary' and self.primary_insured_ref:
            raise ValidationError("Un assuré principal ne peut pas référencer un autre assuré principal.")


class Invoice(models.Model):
    id = models.AutoField(primary_key=True)
    creation_date = models.DateTimeField(auto_now_add=True)
    modification_date = models.DateTimeField(auto_now=True)
    invoice_number = models.CharField(max_length=255)
    claimed_amount = models.FloatField()
    reimbursed_amount = models.FloatField()
    provider = models.ForeignKey('Partner', on_delete=models.CASCADE, related_name='invoices')
    insured = models.ForeignKey(Insured, on_delete=models.CASCADE, related_name='invoices')
    file = models.ForeignKey(File, on_delete=models.SET_NULL, null=True, blank=True, related_name='invoices')
    import_session = models.ForeignKey(ImportSession, on_delete=models.SET_NULL, null=True, blank=True, related_name='imported_invoices')

    def __str__(self):
        return self.invoice_number


class Partner(models.Model):
    id = models.AutoField(primary_key=True)
    name = models.CharField(max_length=255)
    contact = models.CharField(max_length=255, null=True, blank=True)
    modification_date = models.DateTimeField(auto_now=True)
    creation_date = models.DateTimeField(auto_now_add=True)
    main_responsible_name = models.CharField(max_length=255, null=True, blank=True)
    country = models.ForeignKey(Country, on_delete=models.CASCADE, related_name='partners')

    def __str__(self):
        return self.name


class PaymentMethod(models.Model):
    
    id = models.AutoField(primary_key=True)
    creation_date = models.DateTimeField(auto_now_add=True)
    modification_date = models.DateTimeField(auto_now=True)
    payment_number = models.CharField(max_length=255)
    emission_date = models.DateTimeField()
    provider = models.ForeignKey(Partner, on_delete=models.CASCADE, related_name='payment_methods')

    def __str__(self):
        return f'Method {self.payment_number} - {self.payment_method_type}'


class Act(models.Model):
    id = models.AutoField(primary_key=True)
    creation_date = models.DateTimeField(auto_now_add=True)
    modification_date = models.DateTimeField(auto_now=True)
    label = models.CharField(max_length=255)
    family = models.ForeignKey('ActFamily', on_delete=models.CASCADE, related_name='acts')

    def __str__(self):
        return self.label


class ActFamily(models.Model):
    id = models.AutoField(primary_key=True)
    creation_date = models.DateTimeField(auto_now_add=True)
    modification_date = models.DateTimeField(auto_now=True)
    label = models.CharField(max_length=255)
    category = models.ForeignKey('ActCategory', on_delete=models.CASCADE, related_name='families')

    def __str__(self):
        return self.label


class ActCategory(models.Model):
    id = models.AutoField(primary_key=True)
    creation_date = models.DateTimeField(auto_now_add=True)
    modification_date = models.DateTimeField(auto_now=True)
    label = models.CharField(max_length=255)

    def __str__(self):
        return self.label


class Operator(models.Model):
    id = models.AutoField(primary_key=True)
    name = models.CharField(max_length=255)
    country = models.ForeignKey(Country, on_delete=models.CASCADE, related_name='operators')

    def __str__(self):
        return self.name


class Claim(models.Model):
    class StatusEnum(models.TextChoices):
        APPROVED = 'A', 'Approved'
        REJECTED = 'R', 'Rejected'
        CANCELED = 'C', 'Canceled'

    id = models.CharField(primary_key=True, max_length=255)
    status = models.CharField(max_length=1, choices=StatusEnum.choices, null=True)
    claim_date = models.DateTimeField()
    settlement_date = models.DateTimeField()
    invoice = models.ForeignKey('Invoice', on_delete=models.CASCADE, related_name='claims', null=True)
    act = models.ForeignKey(Act, on_delete=models.CASCADE, related_name='claims', null=True)
    operator = models.ForeignKey(Operator, on_delete=models.CASCADE, related_name='claims', null=True)
    insured = models.ForeignKey(Insured, on_delete=models.CASCADE, related_name='claims', null=True)
    partner = models.ForeignKey(Partner, on_delete=models.CASCADE, related_name='claims', null=True)
    policy = models.ForeignKey(Policy, on_delete=models.CASCADE, related_name='claims', null=True)
    file = models.ForeignKey(File, on_delete=models.SET_NULL, null=True, blank=True, related_name='claims')
    import_session = models.ForeignKey(ImportSession, on_delete=models.SET_NULL, null=True, blank=True, related_name='imported_claims')

    def __str__(self):
        return f'Claim {self.id}'
    