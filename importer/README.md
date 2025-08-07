# Importer Module - Sunu Dash API

## Overview

The Importer module is the core data processing engine of the Sunu Dash platform, responsible for importing, validating, cleaning, and mapping Excel/CSV data into the Core module's business models. It provides comprehensive data import capabilities with robust error handling, validation, and audit trails.

## Business Domain

The Importer module handles the complete data import lifecycle:
- **File Validation**: Validates Excel/CSV files against expected schemas
- **Data Cleaning**: Cleans and standardizes imported data
- **Data Mapping**: Maps cleaned data to Core module models
- **Error Handling**: Comprehensive error tracking and reporting
- **Audit Trail**: Complete logging of import operations
- **Async Processing**: Background processing for large datasets

## Architecture Overview

### Service-Oriented Architecture

```
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   File Upload   │    │  ImporterService│    │   DataMapper    │
│     (Views)     │───▶│                 │───▶│                 │
│                 │    │ • Validation    │    │ • Model Creation│
│ • File Upload   │    │ • Cleaning      │    │ • Relationships │
│ • Session Mgmt  │    │ • Comparison    │    │ • Error Handling│
└─────────────────┘    └─────────────────┘    └─────────────────┘
                                │                       │
                                ▼                       ▼
                       ┌─────────────────┐    ┌─────────────────┐
                       │ CleaningService │    │ LoggingService  │
                       │                 │    │                 │
                       │ • Data Cleaning │    │ • Audit Trail   │
                       │ • Formatting    │    │ • Error Logging │
                       │ • Validation    │    │ • Progress Track│
                       └─────────────────┘    └─────────────────┘
                                │
                                ▼
                       ┌─────────────────┐
                       │ComparisonService│
                       │                 │
                       │ • Date Range    │
                       │ • Data Matching │
                       │ • Validation    │
                       └─────────────────┘
```

## Core Components

### 1. ImporterService
**File**: `importer/services/importer_service.py`

The main orchestrator service that coordinates the entire import process.

```python
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
        self.valid_stats = None
        self.errors = []
        self.common_range = None
```

**Key Responsibilities**:
- **Session Management**: Creates and manages import sessions
- **File Processing**: Coordinates file reading and validation
- **Data Cleaning**: Orchestrates data cleaning operations
- **Data Comparison**: Manages data comparison and validation
- **Async Processing**: Triggers background import operations

**Workflow**:
1. **Session Creation**: Creates import session and file records
2. **File Opening**: Reads and validates uploaded files
3. **Data Cleaning**: Cleans and standardizes data
4. **Data Comparison**: Compares stat and recap data
5. **Async Import**: Triggers background data mapping

### 2. DataMapper Service
**File**: `importer/services/data_mapper.py`

Responsible for mapping cleaned data to Core module models.

```python
class DataMapper:
    def __init__(self, df_stat, import_session):
        self.df_stat = df_stat
        self.import_session = import_session
        self.country = import_session.country
        self.file = import_session.stat_file
        self.user = import_session.user
        self.logger_service = ImportLoggerService(import_session.id)
        self.logs = []
        self.orphan_claims = []
        self.errors = []
```

**Key Responsibilities**:
- **Model Creation**: Creates Core module models from data
- **Relationship Management**: Establishes relationships between models
- **Error Handling**: Tracks and logs mapping errors
- **Audit Logging**: Comprehensive logging of mapping operations
- **Data Validation**: Validates data during mapping process

**Mapping Process**:
1. **Base Objects**: Creates categories, families, acts, partners
2. **Business Objects**: Creates clients, policies, insured individuals
3. **Relationships**: Establishes employment and family relationships
4. **Financial Data**: Creates invoices and payment methods
5. **Claims**: Creates claims with all associated data

### 3. CleaningService
**File**: `importer/services/cleaning_service.py`

Handles data cleaning and standardization.

```python
class CleaningService:
    def clean_stat_dataframe(self, df):
        """Cleans statistical data dataframe."""
        
    def clean_recap_dataframe(self, df):
        """Cleans recap data dataframe."""
```

**Key Responsibilities**:
- **Data Standardization**: Standardizes data formats and values
- **Missing Data Handling**: Handles missing or invalid data
- **Format Conversion**: Converts data to required formats
- **Validation**: Validates data quality and consistency
- **Error Reporting**: Reports cleaning errors and issues

### 4. ComparisonService
**File**: `importer/services/comparison_service.py`

Compares and validates data between stat and recap files.

```python
class ComparisonService:
    def get_common_date(self, df_stat, df_recap):
        """Finds common date range between files."""
        
    def compare_data(self, df_stat, df_recap):
        """Compares data between stat and recap files."""
```

**Key Responsibilities**:
- **Date Range Analysis**: Finds common date ranges between files
- **Data Consistency**: Validates data consistency between files
- **Matching Validation**: Ensures data matches between sources
- **Error Detection**: Detects discrepancies and errors
- **Validation Reporting**: Reports comparison results

### 5. LoggingService
**File**: `importer/services/logging_service.py`

Provides comprehensive logging and audit trail capabilities.

```python
class ImportLoggerService:
    def __init__(self, session_id):
        self.session_id = session_id
        self.log_file_path = self._create_log_file()
        
    def log_step_start(self, step_name, step_number=None):
        """Logs the start of a processing step."""
        
    def log_step_end(self, step_name, success, details=None):
        """Logs the end of a processing step."""
```

**Key Responsibilities**:
- **Step Logging**: Logs start and end of processing steps
- **Error Logging**: Logs errors and exceptions
- **Progress Tracking**: Tracks import progress
- **Audit Trail**: Maintains complete audit trail
- **File Management**: Manages log file creation and storage

## API Endpoints

### File Upload and Import

#### 1. Upload and Import Files
- **URL**: `POST /importer/upload-and-import/`
- **Permissions**: IsAuthenticated, IsTerritorialAdmin, IsTerritorialAdminAndAssignedCountry | IsChefDeptTech
- **Description**: Uploads stat and recap files and initiates import process
- **Payload**: Multipart form data
  - `stat_file`: Statistical Excel/CSV file
  - `recap_file`: Recap Excel/CSV file
- **Response**:
```json
{
    "detail": "Import lancé avec succès.",
    "session_id": 123
}
```

**Expected Headers**:
- **Stat File**: 22 required columns including employer name, beneficiary name, policy number, etc.
- **Recap File**: 13 required columns including settlement ID, beneficiary, employer, etc.

**Validation Process**:
1. **File Format**: Validates Excel/CSV format
2. **Header Validation**: Checks for required columns
3. **Data Validation**: Validates data quality and format
4. **Country Validation**: Ensures user has country assignment

## Data Processing Workflow

### 1. File Upload and Validation
```
File Upload → Header Validation → Format Validation → Session Creation
```

**Steps**:
1. **File Upload**: Files uploaded via multipart form
2. **Header Validation**: Check for required columns
3. **Format Validation**: Validate file format and structure
4. **Session Creation**: Create import session and file records

### 2. Data Cleaning and Standardization
```
File Reading → Data Cleaning → Format Conversion → Validation
```

**Steps**:
1. **File Reading**: Read Excel/CSV files into dataframes
2. **Data Cleaning**: Clean and standardize data
3. **Format Conversion**: Convert dates and other formats
4. **Validation**: Validate cleaned data quality

### 3. Data Comparison and Validation
```
Date Range Analysis → Data Comparison → Consistency Check → Validation
```

**Steps**:
1. **Date Range Analysis**: Find common date ranges
2. **Data Comparison**: Compare stat and recap data
3. **Consistency Check**: Validate data consistency
4. **Validation**: Final validation before import

### 4. Data Mapping and Import
```
Model Creation → Relationship Establishment → Database Insertion → Audit Logging
```

**Steps**:
1. **Model Creation**: Create Core module models
2. **Relationship Establishment**: Establish model relationships
3. **Database Insertion**: Insert data into database
4. **Audit Logging**: Log all operations and results

## Data Mapping Strategy

### Core Model Creation Order

1. **Base Classification Models**:
   - `ActCategory` → `ActFamily` → `Act`
   - `Partner` (Healthcare providers)
   - `Operator` (System operators)

2. **Business Entity Models**:
   - `Client` (Employers)
   - `Policy` (Insurance contracts)
   - `Insured` (Covered individuals)

3. **Relationship Models**:
   - `InsuredEmployer` (Employment relationships)
   - `Invoice` (Billing records)
   - `PaymentMethod` (Payment tracking)

4. **Transaction Models**:
   - `Claim` (Medical claims)

### Relationship Mapping

```python
# Example mapping relationships
def get_or_create_insured_employer(self, insured, employer, policy, status, insured_dict, main_insured_name, date):
    """Creates or retrieves insured-employer relationship."""
    
def get_or_create_primary_insured(self, name, statut, date):
    """Creates or retrieves primary insured individual."""
    
def get_or_create_dependent_insured(self, name, statut, principal_name, insured_dict, date):
    """Creates or retrieves dependent insured individual."""
```

## Error Handling and Validation

### Validation Levels

1. **File Level Validation**:
   - File format validation
   - Header validation
   - File size validation

2. **Data Level Validation**:
   - Data type validation
   - Required field validation
   - Format validation

3. **Business Logic Validation**:
   - Relationship validation
   - Business rule validation
   - Consistency validation

### Error Categories

1. **File Errors**:
   - Invalid file format
   - Missing required columns
   - File corruption

2. **Data Errors**:
   - Invalid data types
   - Missing required data
   - Format errors

3. **Business Logic Errors**:
   - Invalid relationships
   - Business rule violations
   - Data inconsistencies

### Error Handling Strategy

```python
# Comprehensive error handling
try:
    # Processing logic
    pass
except ValidationError as ve:
    self.logger_service.log_error(f"Validation error: {str(ve)}")
    self.errors.append(str(ve))
except Exception as e:
    self.logger_service.log_error(f"Unexpected error: {str(e)}")
    self.errors.append(str(e))
```

## Performance Optimization

### Async Processing
- **Background Tasks**: Large imports processed asynchronously
- **Progress Tracking**: Real-time progress updates
- **Resource Management**: Efficient memory and CPU usage

### Database Optimization
- **Bulk Operations**: Efficient bulk create and update operations
- **Transaction Management**: Proper transaction handling
- **Index Optimization**: Optimized database queries

### Memory Management
- **Streaming Processing**: Process large files in chunks
- **Garbage Collection**: Proper memory cleanup
- **Resource Monitoring**: Monitor memory usage during processing

## Security and Access Control

### Permission System
- **Authentication Required**: All operations require authentication
- **Country-Based Access**: Users can only import data for their country
- **Role-Based Permissions**: Different access levels based on user roles

### Data Validation
- **Input Validation**: Comprehensive input validation
- **SQL Injection Prevention**: Parameterized queries
- **File Upload Security**: Secure file upload handling

### Audit Trail
- **Operation Logging**: All operations logged with timestamps
- **User Attribution**: All actions attributed to specific users
- **Error Tracking**: Complete error tracking and reporting

## Monitoring and Maintenance

### Performance Monitoring
- **Import Performance**: Monitor import speeds and success rates
- **Error Tracking**: Track and analyze import errors
- **Resource Usage**: Monitor memory and CPU usage

### Data Quality
- **Validation Reports**: Regular validation of imported data
- **Error Analysis**: Analyze and categorize import errors
- **Quality Metrics**: Track data quality metrics

### Maintenance Tasks
- **Log Management**: Regular log file cleanup
- **Error Analysis**: Analyze and fix common errors
- **Performance Optimization**: Optimize import performance

## Integration Points

### File Handling Module
- **File Upload**: Receives files from file handling module
- **Session Management**: Uses import sessions for coordination
- **Error Reports**: Generates error reports for file handling

### Core Module
- **Model Creation**: Creates all Core module models
- **Data Population**: Populates Core module with imported data
- **Relationship Management**: Establishes model relationships

### Users Module
- **Permission Integration**: Uses user permissions for access control
- **Country Association**: Links imports to user countries
- **Audit Trail**: Tracks user actions on imports

## Future Enhancements

### Planned Features
- **Advanced Validation**: Enhanced data validation capabilities
- **Real-Time Processing**: Real-time data processing and updates
- **Advanced Error Handling**: More sophisticated error handling
- **Performance Optimization**: Enhanced performance optimization

### Scalability Improvements
- **Distributed Processing**: Support for distributed processing
- **Cloud Integration**: Integration with cloud processing services
- **Advanced Caching**: Enhanced caching for performance
- **Microservices**: Modular service architecture

---

**Module Version**: 1.0  
**Last Updated**: December 2024  
**Documentation Status**: Complete ✅
