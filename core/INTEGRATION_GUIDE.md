# Core Module - Integration Guide

## Overview

The Core module serves as the central data foundation for the Sunu Dash platform, integrating with multiple modules to provide comprehensive insurance management capabilities. This guide explains how the Core module interacts with other system components.

## Module Integration Architecture

```
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   Dashboard     │    │    Importer     │    │ File Handling   │
│     Module      │    │     Module      │    │     Module      │
│                 │    │                 │    │                 │
│ • Statistics    │◄───┤ • DataMapper    │◄───┤ • File Upload   │
│ • Analytics     │    │ • Import        │    │ • Session Mgmt  │
│ • Reporting     │    │ • Validation    │    │ • Audit Trail   │
└─────────────────┘    └─────────────────┘    └─────────────────┘
         │                       │                       │
         │                       │                       │
         └───────────────────────┼───────────────────────┘
                                 │
                                 ▼
                        ┌─────────────────┐
                        │   Core Module   │
                        │                 │
                        │ • Client        │
                        │ • Policy        │
                        │ • Insured       │
                        │ • Claim         │
                        │ • Partner       │
                        │ • Act           │
                        └─────────────────┘
                                 │
                                 ▼
                        ┌─────────────────┐    ┌─────────────────┐
                        │   Users Module  │    │  Countries      │
                        │                 │    │    Module       │
                        │ • Permissions   │    │                 │
                        │ • Access Control│    │ • Geographic    │
                        │ • Country Based │    │ • Organization  │
                        └─────────────────┘    └─────────────────┘
```

## Integration Points

### 1. Dashboard Module Integration

#### Statistics Services
The Dashboard module consumes Core data to generate comprehensive statistics and analytics.

**Core Models Used**:
- `Client`: Client statistics and portfolio analysis
- `Policy`: Policy performance metrics
- `Insured`: Coverage statistics
- `Claim`: Claims processing analytics
- `Partner`: Provider performance metrics
- `Act`: Medical procedure analysis

**Integration Examples**:

```python
# dashboard/services/client_statistics.py
from core.models import Client, Claim, Invoice, InsuredEmployer, Policy, Insured, Partner, Act, ActCategory

class ClientStatisticsService:
    def get_client_portfolio_stats(self, client_id):
        """Get comprehensive portfolio statistics for a client."""
        client = Client.objects.get(id=client_id)
        
        return {
            'total_policies': client.policies.count(),
            'total_insured': client.client_insureds.count(),
            'total_claims': Claim.objects.filter(
                policy__client=client
            ).count(),
            'total_claimed': Invoice.objects.filter(
                insured__insured_clients__employer=client
            ).aggregate(total=Sum('claimed_amount')),
            'total_reimbursed': Invoice.objects.filter(
                insured__insured_clients__employer=client
            ).aggregate(total=Sum('reimbursed_amount'))
        }
```

**Data Flow**:
1. Dashboard services query Core models
2. Statistics are calculated and aggregated
3. Results are formatted for dashboard display
4. Real-time updates based on Core data changes

### 2. Importer Module Integration

#### DataMapper Service
The Importer module's DataMapper service is the primary interface for bulk data import into Core models.

**Integration Points**:

```python
# importer/services/data_mapper.py
from core.models import (
    Client, Policy, Insured, Invoice, Partner, InsuredEmployer,
    PaymentMethod, Operator, Claim, Act, ActFamily, ActCategory
)

class DataMapper:
    def __init__(self, df_stat, import_session):
        self.df_stat = df_stat
        self.import_session = import_session
        self.country = import_session.country
        self.file = import_session.stat_file
        self.user = import_session.user

    def map_data(self):
        """Map Excel/CSV data to Core models."""
        for index, row in self.df_stat.iterrows():
            # Create or get base entities
            client = self.get_or_create_client(row["employer_name"])
            policy = self.get_or_create_policy(row["policy_number"], client)
            partner = self.get_or_create_partner(row["partner_name"], row["partner_country"])
            
            # Create insured and relationships
            insured = self.get_or_create_primary_insured(row["beneficiary_name"], row["status"], row["date"])
            insured_employer = self.get_or_create_insured_employer(
                insured, client, policy, row["status"], 
                self.insured_dict, row["main_insured_name"], row["date"]
            )
            
            # Create billing and claims
            invoice = self.get_or_create_invoice(
                row["invoice_number"], row["claimed_amount"], 
                row["reimbursed_amount"], partner, insured
            )
            
            claim = self.get_or_create_claim(
                row["claim_id"], row["status"], row["claim_date"],
                row["settlement_date"], invoice, act, operator, 
                insured, partner, policy
            )
```

**Import Workflow**:
1. **File Upload**: File handling module receives Excel/CSV files
2. **Session Creation**: Import session created with metadata
3. **Data Mapping**: DataMapper processes and validates data
4. **Model Creation**: Core models created with proper relationships
5. **Audit Trail**: All operations tracked with import sessions

### 3. File Handling Module Integration

#### Import Session Tracking
All Core models include import session tracking for complete audit trails.

**Integration Features**:

```python
# All Core models include these fields
class Client(models.Model):
    file = models.ForeignKey(File, on_delete=models.SET_NULL, null=True, blank=True, related_name='clients')
    import_session = models.ForeignKey(ImportSession, on_delete=models.SET_NULL, null=True, blank=True, related_name='imported_clients')

class Policy(models.Model):
    file = models.ForeignKey(File, on_delete=models.SET_NULL, null=True, blank=True, related_name='policies')
    import_session = models.ForeignKey(ImportSession, on_delete=models.SET_NULL, null=True, blank=True, related_name='imported_policies')

# ... similar for all other models
```

**Audit Capabilities**:
- **Data Lineage**: Track data source and import history
- **Error Investigation**: Identify problematic import sessions
- **Reimport Support**: Support for data reimport and updates
- **Compliance**: Maintain audit trails for regulatory requirements

### 4. Users Module Integration

#### Permission-Based Access Control
Core data access is controlled through the Users module's permission system.

**Integration Points**:

```python
# Core models respect user permissions and country access
class CoreDataAccessMixin:
    def get_queryset(self):
        """Filter data based on user permissions and country."""
        user = self.request.user
        
        if user.is_superuser_role() or user.is_admin_global():
            # Superusers and global admins see all data
            return super().get_queryset()
        elif user.is_admin_territorial():
            # Territorial admins see only their country's data
            return super().get_queryset().filter(
                country=user.country
            )
        else:
            # Other users have restricted access
            return super().get_queryset().none()
```

**Access Control Features**:
- **Country-Based Filtering**: Data access restricted by user's country
- **Role-Based Permissions**: Different access levels based on user role
- **Audit Logging**: Track all data access and modifications
- **Security Compliance**: Ensure data privacy and security

### 5. Countries Module Integration

#### Geographic Organization
All Core entities are organized by geographic regions through the Countries module.

**Integration Examples**:

```python
# Core models link to countries
class Client(models.Model):
    country = models.ForeignKey(Country, on_delete=models.CASCADE, related_name='clients')

class Partner(models.Model):
    country = models.ForeignKey(Country, on_delete=models.CASCADE, related_name='partners')

class Operator(models.Model):
    country = models.ForeignKey(Country, on_delete=models.CASCADE, related_name='operators')
```

**Geographic Features**:
- **Country-Specific Data**: All business operations are country-specific
- **Regional Reporting**: Statistics and analytics by geographic region
- **Compliance**: Support for country-specific regulations
- **Localization**: Support for country-specific business rules

## Data Flow Patterns

### 1. Data Import Flow

```
File Upload → Import Session → DataMapper → Core Models → Dashboard Statistics
```

**Detailed Flow**:
1. **File Upload**: User uploads Excel/CSV file through file handling module
2. **Session Creation**: Import session created with metadata (user, country, file)
3. **Data Processing**: DataMapper processes and validates data
4. **Model Creation**: Core models created with proper relationships and audit trails
5. **Statistics Update**: Dashboard statistics automatically updated with new data
6. **Notification**: Users notified of import completion and results

### 2. Data Access Flow

```
User Request → Permission Check → Country Filter → Core Data → Formatted Response
```

**Detailed Flow**:
1. **User Request**: User requests data through API or dashboard
2. **Permission Validation**: Users module validates user permissions
3. **Country Filtering**: Data filtered based on user's country assignment
4. **Data Retrieval**: Core models queried with appropriate filters
5. **Response Formatting**: Data formatted for display or API response

### 3. Statistics Generation Flow

```
Core Data → Statistics Service → Aggregated Results → Dashboard Display
```

**Detailed Flow**:
1. **Data Query**: Statistics services query Core models
2. **Calculation**: Complex aggregations and calculations performed
3. **Caching**: Results cached for performance optimization
4. **Display**: Formatted results displayed in dashboard

## API Integration

### 1. Serializer Integration
Core models provide comprehensive serializers for API integration:

```python
# core/serializers.py
class ClientSerializer(serializers.ModelSerializer):
    country = serializers.PrimaryKeyRelatedField(queryset=Country.objects.all())
    file = serializers.PrimaryKeyRelatedField(queryset=File.objects.all(), allow_null=True, required=False)
    import_session = serializers.PrimaryKeyRelatedField(queryset=ImportSession.objects.all(), allow_null=True, required=False)

    class Meta:
        model = Client
        fields = '__all__'
```

### 2. Nested Serialization
Support for nested object creation and updates:

```python
class InsuredEmployerSerializer(serializers.ModelSerializer):
    insured = serializers.PrimaryKeyRelatedField(queryset=Insured.objects.all())
    employer = serializers.PrimaryKeyRelatedField(queryset=Client.objects.all())
    policy = serializers.PrimaryKeyRelatedField(queryset=Policy.objects.all())
    primary_insured_ref = serializers.PrimaryKeyRelatedField(queryset=Insured.objects.all(), allow_null=True, required=False)

    class Meta:
        model = InsuredEmployer
        fields = '__all__'
```

## Performance Optimization

### 1. Database Optimization
- **Indexed Relationships**: All foreign keys are indexed for performance
- **Selective Loading**: Use `select_related` and `prefetch_related` for efficient queries
- **Bulk Operations**: Support for bulk create and update operations

### 2. Caching Strategy
- **Query Caching**: Cache frequently accessed data
- **Statistics Caching**: Cache calculated statistics
- **Session Caching**: Cache user session data

### 3. Background Processing
- **Async Imports**: Large data imports processed asynchronously
- **Statistics Calculation**: Complex calculations run in background
- **Email Notifications**: Import notifications sent asynchronously

## Error Handling and Validation

### 1. Data Validation
```python
# Core models include comprehensive validation
class InsuredEmployer(models.Model):
    def clean(self):
        from django.core.exceptions import ValidationError
        if self.role != 'primary' and not self.primary_insured_ref:
            raise ValidationError("Un assuré dépendant doit avoir un assuré principal référencé.")
```

### 2. Import Error Handling
```python
# DataMapper includes comprehensive error handling
class DataMapper:
    def map_data(self):
        try:
            # Data mapping logic
            pass
        except Exception as e:
            self.logger_service.log_error(f"Mapping error: {str(e)}")
            self.errors.append(str(e))
```

### 3. Rollback Capabilities
- **Transaction Management**: All imports wrapped in database transactions
- **Partial Rollback**: Support for partial import rollback
- **Error Recovery**: Ability to retry failed imports

## Security Considerations

### 1. Data Access Control
- **Permission-Based**: All data access controlled by user permissions
- **Country Isolation**: Data isolated by country boundaries
- **Audit Logging**: All data access and modifications logged

### 2. Data Integrity
- **Validation Rules**: Comprehensive validation at model level
- **Constraint Enforcement**: Database constraints ensure data integrity
- **Business Rules**: Business logic enforced through model methods

### 3. Audit Trail
- **Import Tracking**: All imports tracked with sessions and files
- **Modification History**: All changes tracked with timestamps
- **User Attribution**: All changes attributed to specific users

## Monitoring and Maintenance

### 1. Performance Monitoring
- **Query Performance**: Monitor database query performance
- **Import Performance**: Track import processing times
- **Memory Usage**: Monitor memory usage during large imports

### 2. Data Quality
- **Validation Reports**: Regular validation of data quality
- **Duplicate Detection**: Identify and handle duplicate records
- **Consistency Checks**: Ensure data consistency across models

### 3. Maintenance Tasks
- **Data Cleanup**: Regular cleanup of orphaned records
- **Index Maintenance**: Regular database index maintenance
- **Archive Management**: Archive old data for performance

## Future Integration Enhancements

### 1. Real-Time Updates
- **WebSocket Integration**: Real-time data updates
- **Event Streaming**: Stream data changes to other modules
- **Live Statistics**: Real-time statistics updates

### 2. Advanced Analytics
- **Machine Learning**: Integration with ML models for predictions
- **Advanced Reporting**: Complex analytical reporting
- **Data Visualization**: Enhanced data visualization capabilities

### 3. External Integrations
- **Third-Party APIs**: Integration with external insurance systems
- **Data Exports**: Export data to external systems
- **Webhook Support**: Webhook notifications for data changes

---

**Integration Guide Version**: 1.0  
**Last Updated**: December 2024  
**Status**: Complete ✅
