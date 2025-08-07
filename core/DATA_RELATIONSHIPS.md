# Core Module - Data Relationships Guide

## Overview

This guide provides a comprehensive understanding of the relationships between Core module models, their business logic, and how data flows through the insurance management system.

## Entity Relationship Diagram

```
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│     Country     │    │     Client      │    │     Policy      │
│                 │    │                 │    │                 │
│ • id            │◄───┤ • country       │◄───┤ • client        │
│ • name          │    │ • name          │    │ • policy_number │
│ • code          │    │ • contact       │    │ • creation_date │
└─────────────────┘    │ • prime         │    └─────────────────┘
                       │ • creation_date │             │
                       └─────────────────┘             │
                                │                      │
                                ▼                      ▼
                       ┌─────────────────┐    ┌─────────────────┐
                       │     Insured     │    │ InsuredEmployer │
                       │                 │    │                 │
                       │ • name          │◄───┤ • insured       │
                       │ • birth_date    │    │ • employer      │
                       │ • card_number   │    │ • policy        │
                       │ • phone_number  │    │ • role          │
                       │ • email         │    │ • start_date    │
                       │ • is_primary    │    │ • end_date      │
                       │ • is_child      │    └─────────────────┘
                       │ • is_spouse     │
                       │ • primary_insured│
                       └─────────────────┘
                                │
                                ▼
                       ┌─────────────────┐    ┌─────────────────┐
                       │     Invoice     │    │     Partner     │
                       │                 │    │                 │
                       │ • invoice_number│◄───┤ • name          │
                       │ • claimed_amount│    │ • contact       │
                       │ • reimbursed    │    │ • country       │
                       │ • provider      │    │ • main_resp     │
                       │ • insured       │    └─────────────────┘
                       └─────────────────┘
                                │
                                ▼
                       ┌─────────────────┐
                       │     Claim       │
                       │                 │
                       │ • id            │
                       │ • status        │
                       │ • claim_date    │
                       │ • settlement    │
                       │ • invoice       │
                       │ • act           │
                       │ • operator      │
                       │ • insured       │
                       │ • partner       │
                       │ • policy        │
                       └─────────────────┘
```

## Detailed Relationship Analysis

### 1. Geographic Hierarchy

#### Country → Client/Partner/Operator
```python
# Country is the top-level geographic entity
class Country(models.Model):
    name = models.CharField(max_length=255)
    code = models.CharField(max_length=3)

# All business entities are associated with countries
class Client(models.Model):
    country = models.ForeignKey(Country, on_delete=models.CASCADE, related_name='clients')

class Partner(models.Model):
    country = models.ForeignKey(Country, on_delete=models.CASCADE, related_name='partners')

class Operator(models.Model):
    country = models.ForeignKey(Country, on_delete=models.CASCADE, related_name='operators')
```

**Business Logic**:
- All business operations are country-specific
- Data access is restricted by user's country assignment
- Statistics and reporting are organized by country
- Import sessions are country-specific

### 2. Client-Policy Relationship

#### Client → Policy (One-to-Many)
```python
class Client(models.Model):
    name = models.CharField(max_length=255)
    # ... other fields

class Policy(models.Model):
    policy_number = models.CharField(max_length=255)
    client = models.ForeignKey(Client, on_delete=models.CASCADE, related_name='policies')
```

**Business Logic**:
- One client can have multiple insurance policies
- Each policy has a unique policy number
- Policies inherit client's country association
- Policy creation is tracked with timestamps

**Example Queries**:
```python
# Get all policies for a client
client.policies.all()

# Get client for a policy
policy.client

# Get policies by country
Policy.objects.filter(client__country=country)
```

### 3. Insured Family Structure

#### Insured Self-Reference (Primary-Dependent)
```python
class Insured(models.Model):
    name = models.CharField(max_length=255)
    is_primary_insured = models.BooleanField(default=False)
    is_child = models.BooleanField(default=False)
    is_spouse = models.BooleanField(default=False)
    primary_insured = models.ForeignKey('self', null=True, blank=True, on_delete=models.SET_NULL, related_name='dependents')
```

**Business Logic**:
- Primary insured can have multiple dependents (spouse, children)
- Dependents reference their primary insured
- Family structure affects coverage and billing
- Consumption limits may vary by family role

**Example Queries**:
```python
# Get primary insured for a dependent
dependent.primary_insured

# Get all dependents for a primary insured
primary_insured.dependents.all()

# Get family members
insured.dependents.filter(is_spouse=True)  # Spouse
insured.dependents.filter(is_child=True)   # Children
```

### 4. Complex Employment Relationship

#### InsuredEmployer Junction Table
```python
class InsuredEmployer(models.Model):
    insured = models.ForeignKey('Insured', on_delete=models.CASCADE, related_name='insured_clients')
    employer = models.ForeignKey('Client', on_delete=models.CASCADE, related_name='client_insureds')
    policy = models.ForeignKey('Policy', on_delete=models.CASCADE, related_name='insured_employers')
    
    ROLE_CHOICES = (
        ('primary', 'Assuré principal'),
        ('spouse', 'Conjoint(e)'),
        ('child', 'Enfant'),
        ('other', 'Autre'),
    )
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default='primary')
    primary_insured_ref = models.ForeignKey('Insured', null=True, blank=True, on_delete=models.SET_NULL, related_name='dependents_in_clients')
    start_date = models.DateField(null=True, blank=True)
    end_date = models.DateField(null=True, blank=True)
```

**Business Logic**:
- Links insured individuals to employers through specific policies
- Tracks employment periods with start/end dates
- Manages family roles within employment context
- Supports multiple employers per insured
- Enforces business rules for dependent relationships

**Validation Rules**:
```python
def clean(self):
    if self.role != 'primary' and not self.primary_insured_ref:
        raise ValidationError("Un assuré dépendant doit avoir un assuré principal référencé.")
    if self.role == 'primary' and self.primary_insured_ref:
        raise ValidationError("Un assuré principal ne peut pas référencer un autre assuré principal.")
```

**Example Queries**:
```python
# Get all employers for an insured
insured.insured_clients.all()

# Get all insured for an employer
employer.client_insureds.all()

# Get active employment relationships
InsuredEmployer.objects.filter(
    start_date__lte=today,
    end_date__gte=today
)

# Get primary insured for a dependent
dependent.primary_insured_ref
```

### 5. Billing and Claims Flow

#### Invoice → Claim Relationship
```python
class Invoice(models.Model):
    invoice_number = models.CharField(max_length=255)
    claimed_amount = models.FloatField()
    reimbursed_amount = models.FloatField()
    provider = models.ForeignKey('Partner', on_delete=models.CASCADE, related_name='invoices')
    insured = models.ForeignKey(Insured, on_delete=models.CASCADE, related_name='invoices')

class Claim(models.Model):
    id = models.CharField(primary_key=True, max_length=255)
    status = models.CharField(max_length=1, choices=StatusEnum.choices, null=True)
    claim_date = models.DateTimeField()
    settlement_date = models.DateTimeField()
    invoice = models.ForeignKey('Invoice', on_delete=models.CASCADE, related_name='claims', null=True)
    # ... other fields
```

**Business Logic**:
- One invoice can generate multiple claims
- Claims track processing status (Approved/Rejected/Canceled)
- Financial amounts are tracked at invoice level
- Claims link to medical acts and operators

**Example Queries**:
```python
# Get all claims for an invoice
invoice.claims.all()

# Get invoice for a claim
claim.invoice

# Get claims by status
Claim.objects.filter(status='A')  # Approved
Claim.objects.filter(status='R')  # Rejected
Claim.objects.filter(status='C')  # Canceled

# Get total claimed amount for an insured
insured.invoices.aggregate(total=Sum('claimed_amount'))
```

### 6. Medical Act Classification

#### Three-Level Hierarchy
```python
class ActCategory(models.Model):
    label = models.CharField(max_length=255)

class ActFamily(models.Model):
    label = models.CharField(max_length=255)
    category = models.ForeignKey('ActCategory', on_delete=models.CASCADE, related_name='families')

class Act(models.Model):
    label = models.CharField(max_length=255)
    family = models.ForeignKey('ActFamily', on_delete=models.CASCADE, related_name='acts')
```

**Business Logic**:
- Hierarchical classification of medical procedures
- Supports standardized medical coding
- Enables statistical analysis by procedure type
- Facilitates billing and reimbursement processing

**Example Queries**:
```python
# Get all families in a category
category.families.all()

# Get all acts in a family
family.acts.all()

# Get complete hierarchy for an act
act.family.category

# Get all acts in a category
Act.objects.filter(family__category=category)
```

### 7. Partner and Provider Relationships

#### Partner → Invoice → Claim
```python
class Partner(models.Model):
    name = models.CharField(max_length=255)
    country = models.ForeignKey(Country, on_delete=models.CASCADE, related_name='partners')

class Invoice(models.Model):
    provider = models.ForeignKey('Partner', on_delete=models.CASCADE, related_name='invoices')

class Claim(models.Model):
    partner = models.ForeignKey(Partner, on_delete=models.CASCADE, related_name='claims', null=True)
```

**Business Logic**:
- Partners are healthcare providers
- Partners issue invoices for services
- Claims are processed against partner invoices
- Partner performance can be analyzed

**Example Queries**:
```python
# Get all invoices from a partner
partner.invoices.all()

# Get all claims for a partner
partner.claims.all()

# Get total reimbursed amount for a partner
partner.invoices.aggregate(total=Sum('reimbursed_amount'))
```

## Data Flow Patterns

### 1. Client Onboarding Flow
```
Country → Client → Policy → InsuredEmployer → Insured
```

### 2. Claims Processing Flow
```
Insured → Invoice → Claim → Act → Operator
```

### 3. Billing Flow
```
Partner → Invoice → Claim → Policy → Client
```

### 4. Family Management Flow
```
Primary Insured → Dependents → InsuredEmployer → Policy
```

## Complex Query Examples

### 1. Get Complete Family Coverage
```python
def get_family_coverage(primary_insured):
    """Get all family members and their coverage details."""
    family_members = InsuredEmployer.objects.filter(
        insured__primary_insured=primary_insured
    ).select_related(
        'insured', 'employer', 'policy'
    )
    
    return {
        'primary': primary_insured,
        'dependents': family_members,
        'total_coverage': family_members.count()
    }
```

### 2. Get Claims Statistics by Partner
```python
def get_partner_statistics(partner, start_date, end_date):
    """Get comprehensive statistics for a partner."""
    claims = Claim.objects.filter(
        partner=partner,
        claim_date__range=[start_date, end_date]
    )
    
    return {
        'total_claims': claims.count(),
        'approved_claims': claims.filter(status='A').count(),
        'rejected_claims': claims.filter(status='R').count(),
        'total_claimed': claims.aggregate(total=Sum('invoice__claimed_amount')),
        'total_reimbursed': claims.aggregate(total=Sum('invoice__reimbursed_amount'))
    }
```

### 3. Get Client Portfolio
```python
def get_client_portfolio(client):
    """Get complete portfolio for a client."""
    policies = client.policies.prefetch_related(
        'insured_employers__insured',
        'insured_employers__insured__invoices',
        'insured_employers__insured__claims'
    )
    
    return {
        'client': client,
        'policies': policies,
        'total_insured': sum(policy.insured_employers.count() for policy in policies),
        'total_claims': sum(
            claim.count() for policy in policies 
            for ie in policy.insured_employers.all() 
            for claim in ie.insured.claims.all()
        )
    }
```

## Performance Optimization

### 1. Select Related for Foreign Keys
```python
# Efficient query with related data
clients = Client.objects.select_related('country').all()
policies = Policy.objects.select_related('client', 'client__country').all()
```

### 2. Prefetch Related for Reverse Foreign Keys
```python
# Efficient query for reverse relationships
clients = Client.objects.prefetch_related('policies', 'client_insureds').all()
insured = Insured.objects.prefetch_related('dependents', 'invoices', 'claims').all()
```

### 3. Bulk Operations
```python
# Efficient bulk creation
Client.objects.bulk_create([
    Client(name="Client 1", country=country1),
    Client(name="Client 2", country=country2),
])

# Efficient bulk update
Client.objects.bulk_update(clients, ['prime', 'modification_date'])
```

## Data Integrity Constraints

### 1. Unique Constraints
```python
class InsuredEmployer(models.Model):
    class Meta:
        unique_together = ('insured', 'employer', 'policy')
```

### 2. Business Rule Validation
```python
def clean(self):
    # Validate dependent relationships
    if self.role != 'primary' and not self.primary_insured_ref:
        raise ValidationError("Dependents must reference primary insured")
```

### 3. Cascade Deletion Rules
```python
# Client deletion cascades to policies
client = models.ForeignKey(Client, on_delete=models.CASCADE)

# File deletion sets to NULL (preserves data)
file = models.ForeignKey(File, on_delete=models.SET_NULL, null=True, blank=True)
```

## Audit Trail

### 1. Import Session Tracking
All models track import sessions for data lineage:
```python
import_session = models.ForeignKey(ImportSession, on_delete=models.SET_NULL, null=True, blank=True)
```

### 2. File Association
All models link to source files:
```python
file = models.ForeignKey(File, on_delete=models.SET_NULL, null=True, blank=True)
```

### 3. Timestamp Tracking
```python
creation_date = models.DateTimeField(auto_now_add=True)
modification_date = models.DateTimeField(auto_now=True)
```

---

**Documentation Version**: 1.0  
**Last Updated**: December 2024  
**Status**: Complete ✅
