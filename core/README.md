# Core Module - Sunu Dash API

## Overview

The Core module is the heart of the Sunu Dash platform, containing all the essential business models for insurance management. It provides the data foundation for clients, policies, insured individuals, claims, and all related entities in the insurance ecosystem.

## Business Domain

The Core module manages the complete insurance lifecycle:
- **Client Management**: Employers and organizations
- **Policy Management**: Insurance contracts and coverage
- **Insured Management**: Individuals covered by policies
- **Claims Processing**: Medical claims and reimbursements
- **Partner Management**: Healthcare providers and partners
- **Act Classification**: Medical procedures and services

## Models Architecture

### Core Entities

```
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│     Client      │    │     Policy      │    │     Insured     │
│                 │    │                 │    │                 │
│ • name          │◄───┤ • policy_number │    │ • name          │
│ • contact       │    │ • client        │    │ • birth_date    │
│ • country       │    │ • creation_date │    │ • card_number   │
│ • prime         │    └─────────────────┘    │ • phone_number  │
│ • creation_date │                           │ • email         │
└─────────────────┘                           │ • is_primary    │
                                              │ • is_child      │
                                              │ • is_spouse     │
                                              └─────────────────┘
                                                       │
                                                       ▼
                                              ┌─────────────────┐
                                              │ InsuredEmployer │
                                              │                 │
                                              │ • insured       │
                                              │ • employer      │
                                              │ • policy        │
                                              │ • role          │
                                              │ • start_date    │
                                              │ • end_date      │
                                              └─────────────────┘
```

### Claims and Billing

```
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│     Claim       │    │     Invoice     │    │     Partner     │
│                 │    │                 │    │                 │
│ • id            │◄───┤ • invoice_number│    │ • name          │
│ • status        │    │ • claimed_amount│    │ • contact       │
│ • claim_date    │    │ • reimbursed    │    │ • country       │
│ • settlement    │    │ • provider      │    │ • main_resp     │
│ • invoice       │    │ • insured       │    └─────────────────┘
│ • act           │    └─────────────────┘
│ • operator      │
│ • insured       │
│ • partner       │
│ • policy        │
└─────────────────┘
```

### Medical Acts Classification

```
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│  ActCategory    │    │   ActFamily     │    │      Act        │
│                 │    │                 │    │                 │
│ • label         │◄───┤ • label         │◄───┤ • label         │
│ • creation_date │    │ • category      │    │ • family        │
│ • modification  │    │ • creation_date │    │ • creation_date │
└─────────────────┘    └─────────────────┘    └─────────────────┘
```

## Models Documentation

### 1. Client Model
**File**: `core/models.py`

```python
class Client(models.Model):
    id = models.AutoField(primary_key=True)
    contact = models.CharField(max_length=255, null=True, blank=True)
    creation_date = models.DateTimeField(blank=True, null=True)
    modification_date = models.DateTimeField(blank=True, null=True)
    name = models.CharField(max_length=255)
    country = models.ForeignKey(Country, on_delete=models.CASCADE, related_name='clients')
    prime = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    file = models.ForeignKey(File, on_delete=models.SET_NULL, null=True, blank=True, related_name='clients')
    import_session = models.ForeignKey(ImportSession, on_delete=models.SET_NULL, null=True, blank=True, related_name='imported_clients')
```

**Purpose**: Represents employers or organizations that purchase insurance policies.

**Key Features**:
- **Prime Management**: Tracks insurance premiums with historical changes
- **Country Association**: Links clients to specific countries
- **Import Tracking**: Tracks data import sessions and source files
- **Contact Information**: Stores client contact details

**Relationships**:
- `Country`: Each client belongs to a specific country
- `Policy`: One-to-many relationship with policies
- `InsuredEmployer`: Links insured individuals to employers
- `File`: Tracks source file for data import
- `ImportSession`: Tracks import session for audit trail

### 2. ClientPrimeHistory Model
**File**: `core/models.py`

```python
class ClientPrimeHistory(models.Model):
    client = models.ForeignKey(Client, on_delete=models.CASCADE, related_name='prime_history')
    prime = models.DecimalField(max_digits=10, decimal_places=2)
    date = models.DateTimeField(auto_now_add=True)
```

**Purpose**: Maintains historical record of client premium changes.

**Key Features**:
- **Audit Trail**: Tracks all premium modifications
- **Timestamp**: Records exact date of changes
- **Data Integrity**: Preserves historical premium values

### 3. Policy Model
**File**: `core/models.py`

```python
class Policy(models.Model):
    id = models.AutoField(primary_key=True)
    creation_date = models.DateTimeField(auto_now_add=True)
    policy_number = models.CharField(max_length=255)
    client = models.ForeignKey(Client, on_delete=models.CASCADE, related_name='policies')
    file = models.ForeignKey(File, on_delete=models.SET_NULL, null=True, blank=True, related_name='policies')
    import_session = models.ForeignKey(ImportSession, on_delete=models.SET_NULL, null=True, blank=True, related_name='imported_policies')
```

**Purpose**: Represents insurance contracts between clients and insurance providers.

**Key Features**:
- **Unique Identification**: Policy numbers for contract tracking
- **Client Association**: Links policies to specific clients
- **Creation Tracking**: Automatic timestamp for policy creation
- **Import Audit**: Tracks data import sessions

### 4. Insured Model
**File**: `core/models.py`

```python
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
```

**Purpose**: Represents individuals covered by insurance policies.

**Key Features**:
- **Family Structure**: Supports primary insured and dependents
- **Contact Information**: Phone, email, and card number
- **Consumption Limits**: Tracks usage limits for services
- **Status Flags**: Identifies primary insured, children, and spouses
- **Self-Referential**: Links dependents to primary insured

**Relationships**:
- `Insured` (self): Primary insured for dependents
- `InsuredEmployer`: Links to employers through policies
- `Invoice`: Billing records for services
- `Claim`: Medical claims submitted

### 5. InsuredEmployer Model
**File**: `core/models.py`

```python
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
    primary_insured_ref = models.ForeignKey('Insured', null=True, blank=True, on_delete=models.SET_NULL, related_name='dependents_in_clients')
    start_date = models.DateField(null=True, blank=True)
    end_date = models.DateField(null=True, blank=True)
```

**Purpose**: Junction table linking insured individuals to employers through policies.

**Key Features**:
- **Role Management**: Defines relationship type (primary, spouse, child, other)
- **Temporal Coverage**: Start and end dates for coverage periods
- **Dependency Tracking**: Links dependents to primary insured
- **Unique Constraints**: Prevents duplicate relationships

**Validation Rules**:
- Dependents must reference a primary insured
- Primary insured cannot reference another primary insured

### 6. Invoice Model
**File**: `core/models.py`

```python
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
```

**Purpose**: Represents medical bills and reimbursement records.

**Key Features**:
- **Financial Tracking**: Claimed and reimbursed amounts
- **Provider Association**: Links to healthcare providers
- **Insured Association**: Links to covered individuals
- **Audit Trail**: Creation and modification timestamps

### 7. Partner Model
**File**: `core/models.py`

```python
class Partner(models.Model):
    id = models.AutoField(primary_key=True)
    name = models.CharField(max_length=255)
    contact = models.CharField(max_length=255, null=True, blank=True)
    modification_date = models.DateTimeField(auto_now=True)
    creation_date = models.DateTimeField(auto_now_add=True)
    main_responsible_name = models.CharField(max_length=255, null=True, blank=True)
    country = models.ForeignKey(Country, on_delete=models.CASCADE, related_name='partners')
```

**Purpose**: Represents healthcare providers and service partners.

**Key Features**:
- **Contact Management**: Stores partner contact information
- **Responsibility Tracking**: Main responsible person
- **Country Association**: Links partners to specific countries
- **Service History**: Tracks all services provided

### 8. PaymentMethod Model
**File**: `core/models.py`

```python
class PaymentMethod(models.Model):
    id = models.AutoField(primary_key=True)
    creation_date = models.DateTimeField(auto_now_add=True)
    modification_date = models.DateTimeField(auto_now=True)
    payment_number = models.CharField(max_length=255)
    emission_date = models.DateTimeField()
    provider = models.ForeignKey(Partner, on_delete=models.CASCADE, related_name='payment_methods')
```

**Purpose**: Tracks payment methods and transactions.

**Key Features**:
- **Payment Tracking**: Unique payment numbers
- **Emission Dates**: When payments were issued
- **Provider Association**: Links to service providers

### 9. ActCategory Model
**File**: `core/models.py`

```python
class ActCategory(models.Model):
    id = models.AutoField(primary_key=True)
    creation_date = models.DateTimeField(auto_now_add=True)
    modification_date = models.DateTimeField(auto_now=True)
    label = models.CharField(max_length=255)
```

**Purpose**: Top-level classification for medical acts and procedures.

**Key Features**:
- **Hierarchical Classification**: Top level of medical act hierarchy
- **Label Management**: Descriptive category names
- **Audit Trail**: Creation and modification tracking

### 10. ActFamily Model
**File**: `core/models.py`

```python
class ActFamily(models.Model):
    id = models.AutoField(primary_key=True)
    creation_date = models.DateTimeField(auto_now_add=True)
    modification_date = models.DateTimeField(auto_now=True)
    label = models.CharField(max_length=255)
    category = models.ForeignKey('ActCategory', on_delete=models.CASCADE, related_name='families')
```

**Purpose**: Second-level classification grouping related medical acts.

**Key Features**:
- **Category Association**: Links to parent category
- **Grouping Logic**: Groups related medical procedures
- **Hierarchical Structure**: Middle level in classification

### 11. Act Model
**File**: `core/models.py`

```python
class Act(models.Model):
    id = models.AutoField(primary_key=True)
    creation_date = models.DateTimeField(auto_now_add=True)
    modification_date = models.DateTimeField(auto_now=True)
    label = models.CharField(max_length=255)
    family = models.ForeignKey('ActFamily', on_delete=models.CASCADE, related_name='acts')
```

**Purpose**: Represents specific medical procedures and services.

**Key Features**:
- **Specific Procedures**: Individual medical acts
- **Family Association**: Links to act family
- **Service Tracking**: Used in claims and billing

### 12. Operator Model
**File**: `core/models.py`

```python
class Operator(models.Model):
    id = models.AutoField(primary_key=True)
    name = models.CharField(max_length=255)
    country = models.ForeignKey(Country, on_delete=models.CASCADE, related_name='operators')
```

**Purpose**: Represents system operators and data entry personnel.

**Key Features**:
- **Operator Tracking**: Identifies who processed claims
- **Country Association**: Links operators to specific countries
- **Audit Trail**: Tracks claim processing responsibility

### 13. Claim Model
**File**: `core/models.py`

```python
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
```

**Purpose**: Central entity representing medical claims and their processing status.

**Key Features**:
- **Status Management**: Approved, Rejected, or Canceled
- **Temporal Tracking**: Claim and settlement dates
- **Comprehensive Relations**: Links to all related entities
- **Import Tracking**: Audit trail for data imports

**Status Options**:
- `A` - Approved: Claim has been approved for payment
- `R` - Rejected: Claim has been rejected
- `C` - Canceled: Claim has been canceled

## Serializers

### Overview
The Core module provides comprehensive serializers for all models, enabling RESTful API operations with proper data validation and relationship handling.

### Key Serializers

1. **ClientSerializer**: Handles client data with country and file relationships
2. **PolicySerializer**: Manages policy data with client associations
3. **InsuredSerializer**: Handles insured data with family relationships
4. **InsuredEmployerSerializer**: Manages complex employer-insured relationships
5. **InvoiceSerializer**: Handles billing data with provider and insured links
6. **ClaimSerializer**: Comprehensive claim data with all related entities
7. **PartnerSerializer**: Manages partner data with country associations
8. **ActCategorySerializer**: Handles medical act classification
9. **ActFamilySerializer**: Manages act family relationships
10. **ActSerializer**: Handles specific medical procedures

### Serializer Features
- **Relationship Handling**: Proper foreign key and many-to-many field management
- **Validation**: Built-in Django REST Framework validation
- **Nested Serialization**: Support for nested object creation and updates
- **Import Session Tracking**: All serializers support import session tracking
- **File Association**: Links to source files for audit purposes

## Data Import System

### Integration with Importer Module
The Core module is tightly integrated with the Importer module for bulk data processing:

1. **DataMapper Service**: Maps Excel/CSV data to Core models
2. **Import Session Tracking**: All models track import sessions
3. **File Association**: Links imported data to source files
4. **Audit Trail**: Complete tracking of data import history

### Import Workflow
1. **File Upload**: Excel/CSV files uploaded through file_handling module
2. **Data Mapping**: DataMapper service processes and validates data
3. **Model Creation**: Core models created with proper relationships
4. **Session Tracking**: Import sessions recorded for audit purposes
5. **Error Handling**: Comprehensive error logging and reporting

## Business Logic

### Client Management
- **Prime Tracking**: Historical premium changes with audit trail
- **Country Association**: Geographic organization of clients
- **Policy Management**: Multiple policies per client support

### Insured Management
- **Family Structure**: Primary insured and dependent relationships
- **Employment Links**: Multiple employer relationships through policies
- **Coverage Periods**: Temporal tracking of insurance coverage

### Claims Processing
- **Status Workflow**: Approved → Rejected → Canceled
- **Financial Tracking**: Claimed vs reimbursed amounts
- **Provider Integration**: Healthcare provider relationships
- **Medical Act Classification**: Hierarchical procedure classification

### Medical Act Classification
- **Three-Level Hierarchy**: Category → Family → Act
- **Flexible Classification**: Supports various medical procedure types
- **Standardization**: Consistent classification across the system

## Data Relationships

### Primary Relationships
- **Client → Policy**: One-to-many (one client can have multiple policies)
- **Policy → InsuredEmployer**: One-to-many (one policy can cover multiple insured)
- **Insured → InsuredEmployer**: One-to-many (one insured can work for multiple employers)
- **Insured → Claim**: One-to-many (one insured can have multiple claims)
- **Partner → Invoice**: One-to-many (one partner can issue multiple invoices)
- **Invoice → Claim**: One-to-many (one invoice can generate multiple claims)

### Complex Relationships
- **Insured Self-Reference**: Primary insured and dependent relationships
- **InsuredEmployer Junction**: Complex many-to-many with role and temporal data
- **Act Classification**: Three-level hierarchical classification system

## Audit and Tracking

### Import Session Tracking
All models include import session tracking for:
- **Data Lineage**: Track data source and import history
- **Error Investigation**: Identify problematic import sessions
- **Data Quality**: Monitor import success rates
- **Compliance**: Maintain audit trails for regulatory requirements

### File Association
All models link to source files for:
- **Data Provenance**: Track original data sources
- **Reimport Capability**: Support for data reimport
- **Version Control**: Track data file versions
- **Backup and Recovery**: File-based data recovery

### Timestamp Tracking
- **Creation Dates**: Automatic timestamp for new records
- **Modification Dates**: Track when records were last updated
- **Temporal Queries**: Support for time-based data analysis

## Performance Considerations

### Database Optimization
- **Indexed Fields**: Primary keys and foreign keys are indexed
- **Selective Queries**: Efficient relationship queries
- **Bulk Operations**: Support for bulk create and update operations

### Memory Management
- **Lazy Loading**: Relationships loaded on demand
- **Query Optimization**: Efficient database queries
- **Caching Support**: Compatible with Django caching

## Security and Validation

### Data Validation
- **Model Validation**: Comprehensive field validation
- **Business Rules**: Enforced through model constraints
- **Relationship Integrity**: Foreign key constraints maintained

### Access Control
- **Permission-Based**: Access controlled through user permissions
- **Country-Based**: Data access restricted by country
- **Audit Logging**: All changes tracked for security

## Integration Points

### Dashboard Module
- **Statistics Services**: Core models provide data for dashboard statistics
- **Real-time Updates**: Live data for dashboard displays
- **Filtering Support**: Country and date-based filtering

### File Handling Module
- **Import Integration**: Seamless file import processing
- **Export Support**: Data export capabilities
- **File Management**: Source file tracking and management

### Users Module
- **Permission Integration**: User-based access control
- **Country Association**: User-country data access restrictions
- **Audit Trail**: User action tracking

## Future Enhancements

### Planned Features
- **API Endpoints**: RESTful API for all Core models
- **Advanced Filtering**: Complex query and filtering capabilities
- **Data Analytics**: Advanced statistical analysis features
- **Real-time Updates**: WebSocket support for live updates
- **Mobile Support**: Mobile-optimized API endpoints

### Scalability Improvements
- **Database Partitioning**: Support for large datasets
- **Caching Layer**: Redis-based caching for performance
- **Async Processing**: Background task processing
- **Microservices**: Modular service architecture

---

**Module Version**: 1.0  
**Last Updated**: December 2024  
**Documentation Status**: Complete ✅
