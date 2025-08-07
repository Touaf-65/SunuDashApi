# File Handling Module - Sunu Dash API

## Overview

The File Handling module manages file uploads, storage, and session management for the Sunu Dash platform. It provides comprehensive file management capabilities including upload, download, preview, and deletion operations with proper access control and audit trails.

## Business Domain

The File Handling module serves as the foundation for data import operations:
- **File Management**: Upload, storage, and retrieval of Excel/CSV files
- **Session Management**: Import session tracking and status management
- **Access Control**: Country-based and user-based file access restrictions
- **Audit Trail**: Complete tracking of file operations and import sessions

## Models Architecture

### Core Entities

```
┌─────────────────┐    ┌─────────────────┐
│      File       │    │ ImportSession   │
│                 │    │                 │
│ • file          │◄───┤ • stat_file     │
│ • name          │    │ • recap_file    │
│ • file_type     │    │ • status        │
│ • uploaded_at   │    │ • created_at    │
│ • size          │    │ • started_at    │
│ • country       │    │ • completed_at  │
│ • user          │    │ • error_file    │
└─────────────────┘    │ • message       │
                       │ • country       │
                       │ • user          │
                       └─────────────────┘
```

## Models Documentation

### 1. File Model
**File**: `file_handling/models.py`

```python
class File(models.Model):
    FILE_TYPE_CHOICES = [
        ('stat', 'Fichier Statistique'),
        ('recap', 'Fichier Récap'),
    ]

    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    uploaded_by_name = models.CharField(max_length=255, blank=True)
    uploaded_by_email = models.EmailField(blank=True, null=True)
    file = models.FileField(upload_to='uploads/')
    name = models.CharField(max_length=255)
    file_type = models.CharField(max_length=5, choices=FILE_TYPE_CHOICES)
    uploaded_at = models.DateTimeField(auto_now_add=True)
    size = models.CharField(max_length=20, editable=False)
    country = models.ForeignKey(Country, on_delete=models.CASCADE, null=True, blank=True)
```

**Purpose**: Represents uploaded files with metadata and access control.

**Key Features**:
- **File Type Classification**: Distinguishes between statistical and recap files
- **Automatic Metadata**: File size, upload timestamp, and user information
- **Country Association**: Links files to specific countries for access control
- **User Attribution**: Tracks who uploaded the file
- **Size Formatting**: Human-readable file size display

**File Types**:
- `stat`: Statistical files containing detailed claim data
- `recap`: Recap files containing summary information

**Automatic Behaviors**:
- **Name Generation**: Automatically extracts filename from uploaded file
- **Country Assignment**: Inherits country from user if not specified
- **User Information**: Automatically populates uploader details
- **Size Calculation**: Formats file size in human-readable format

### 2. ImportSession Model
**File**: `file_handling/models.py`

```python
class ImportSession(models.Model):
    class Status(models.TextChoices):
        PENDING = 'PENDING', 'Pending'
        PROCESSING = 'PROCESSING', 'Processing'
        DONE = 'DONE', 'Done'
        ERROR = 'ERROR', 'Error'
        DONE_WITH_ERRORS = 'DONE_WITH_ERRORS', 'Done with Errors'

    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    uploaded_by_name = models.CharField(max_length=255, blank=True)
    uploaded_by_email = models.EmailField(blank=True, null=True)
    country = models.ForeignKey(Country, on_delete=models.CASCADE)
    stat_file = models.ForeignKey(File, on_delete=models.CASCADE, related_name='stat_sessions')
    recap_file = models.ForeignKey(File, on_delete=models.CASCADE, related_name='recap_sessions')
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    created_at = models.DateTimeField(auto_now_add=True)
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    error_file = models.FileField(upload_to='error_reports/', null=True, blank=True)
    message = models.TextField(null=True, blank=True)
    insured_created_count = models.IntegerField(default=0)
    claims_created_count = models.IntegerField(default=0)
    total_claimed_amount = models.DecimalField(max_digits=18, decimal_places=2, default=0)
    total_reimbursed_amount = models.DecimalField(max_digits=18, decimal_places=2, default=0)
    start_date = models.DateField(null=True, blank=True)
    end_date = models.DateField(null=True, blank=True)
    log_file_path = models.CharField(max_length=500, blank=True, null=True)
```

**Purpose**: Manages import sessions that link statistical and recap files together.

**Key Features**:
- **Status Tracking**: Complete workflow status management
- **File Association**: Links statistical and recap files
- **Progress Monitoring**: Tracks import progress and timing
- **Error Handling**: Stores error reports and messages
- **Statistics Tracking**: Records import results and statistics
- **Log Management**: Links to detailed log files

**Status Workflow**:
1. **PENDING**: Session created, waiting for processing
2. **PROCESSING**: Import operation in progress
3. **DONE**: Import completed successfully
4. **ERROR**: Import failed with errors
5. **DONE_WITH_ERRORS**: Import completed but with some errors

## API Endpoints

### File Management

#### 1. List Files
- **URL**: `GET /file_handling/files/`
- **Permissions**: IsAuthenticated, IsTerritorialAdminAndAssignedCountry | IsChefDeptTech
- **Description**: Retrieves all files for the user's country
- **Response**: List of files with metadata

#### 2. Delete File
- **URL**: `DELETE /file_handling/files/<int:pk>/delete/`
- **Permissions**: IsAuthenticated, IsTerritorialAdminAndAssignedCountry | IsChefDeptTech
- **Description**: Deletes a file and optionally removes associated claims
- **Payload**:
```json
{
    "delete_claims": true  // Optional: delete associated claims
}
```
- **Response**: Confirmation message with deletion details

#### 3. Download File
- **URL**: `GET /file_handling/files/<int:pk>/download/`
- **Permissions**: IsAuthenticated, IsTerritorialAdminAndAssignedCountry | IsChefDeptTech
- **Description**: Downloads the file as an attachment
- **Response**: File download

#### 4. Preview File
- **URL**: `GET /file_handling/files/<int:pk>/preview/`
- **Permissions**: IsAuthenticated, IsTerritorialAdminAndAssignedCountry | IsChefDeptTech
- **Description**: Returns a preview of the file content (first 10 rows)
- **Response**:
```json
{
    "preview": [
        {"column1": "value1", "column2": "value2"},
        // ... up to 10 rows
    ],
    "metadata": {
        "total_rows": 1000,
        "total_columns": 15,
        "preview_row_count": 10
    }
}
```

### Import Session Management

#### 5. List Import Sessions
- **URL**: `GET /file_handling/import-sessions/`
- **Permissions**: IsAuthenticated, IsTerritorialAdminAndAssignedCountry | IsChefDeptTech
- **Description**: Retrieves all import sessions for the user's country
- **Response**: List of import sessions with status and statistics

#### 6. Download Session Files
- **URL**: `GET /file_handling/import-sessions/<int:pk>/download/?type=error|log`
- **Permissions**: IsAuthenticated, IsTerritorialAdminAndAssignedCountry | IsChefDeptTech
- **Description**: Downloads error reports or log files for import sessions
- **Query Parameters**:
  - `type=error`: Downloads error report file
  - `type=log`: Downloads log file
- **Response**: File download

## Serializers

### FileSerializer
**File**: `file_handling/serializers.py`

```python
class FileSerializer(serializers.ModelSerializer):
    class Meta:
        model = File
        fields = ['id', 'file', 'uploaded_at', 'name', 'file_type', 'size', 'country', 'user']
```

**Features**:
- **Complete File Metadata**: All file information including size and type
- **User Information**: Uploader details and country association
- **Read-Only Fields**: Proper field protection for sensitive data

### ImportSessionSerializer
**File**: `file_handling/serializers.py`

```python
class ImportSessionSerializer(serializers.ModelSerializer):
    class Meta:
        model = ImportSession
        fields = ['id', 'status', 'started_at', 'finished_at', 'country', 'stat_file', 'recap_file']
```

**Features**:
- **Status Information**: Current import session status
- **Timing Data**: Start and completion timestamps
- **File References**: Links to associated files
- **Country Association**: Geographic organization

## Access Control

### Permission System
The module implements comprehensive access control:

1. **Authentication Required**: All endpoints require user authentication
2. **Country-Based Access**: Users can only access files from their assigned country
3. **Role-Based Permissions**: Different access levels based on user roles
4. **Ownership Control**: Users can only delete their own files (with admin exceptions)

### Permission Classes
- **IsAuthenticated**: Ensures user is logged in
- **IsTerritorialAdminAndAssignedCountry**: Territorial admins with country assignment
- **IsChefDeptTech**: Technical department heads

### Access Rules
```python
# File access is restricted by country
files = File.objects.filter(country=request.user.country)

# Users can only delete their own files (except admins)
if request.user != file.user and not getattr(request.user, 'is_admin_territorial', False):
    return Response({"detail": "Permission denied"}, status=403)
```

## File Operations

### File Upload Process
1. **Validation**: File type and format validation
2. **Storage**: Files stored in configured upload directory
3. **Metadata Extraction**: File size, name, and type extraction
4. **User Association**: Link file to uploading user
5. **Country Assignment**: Associate file with user's country

### File Preview Process
1. **Permission Check**: Verify user has access to file
2. **File Reading**: Read file using appropriate method (Excel/CSV)
3. **Data Extraction**: Extract first 10 rows for preview
4. **Metadata Calculation**: Calculate total rows and columns
5. **Response Formatting**: Return structured preview data

### File Deletion Process
1. **Permission Validation**: Check user permissions
2. **Claim Association Check**: Determine if claims are associated
3. **Data Cleanup**: Remove or update associated data
4. **File Removal**: Delete physical file from storage
5. **Database Cleanup**: Remove file record from database

## Integration Points

### Core Module Integration
- **File Association**: All Core models can link to source files
- **Import Session Tracking**: Complete audit trail for data imports
- **Data Lineage**: Track data source and import history

### Importer Module Integration
- **File Processing**: Files are processed by the importer module
- **Session Management**: Import sessions coordinate file processing
- **Error Handling**: Error reports and logs are managed
- **Status Updates**: Real-time status updates during processing

### Users Module Integration
- **Permission System**: Uses user permissions for access control
- **Country Association**: Links files to user countries
- **Audit Trail**: Tracks user actions on files

## Error Handling

### File Validation Errors
- **Format Validation**: Ensures files are in expected format
- **Size Limits**: Validates file size constraints
- **Type Validation**: Ensures correct file type (stat/recap)

### Access Control Errors
- **Permission Denied**: When user lacks required permissions
- **Country Mismatch**: When file country doesn't match user country
- **Ownership Issues**: When user tries to access others' files

### Processing Errors
- **File Read Errors**: When files cannot be read or parsed
- **Storage Errors**: When files cannot be saved or retrieved
- **Database Errors**: When file metadata cannot be saved

## Performance Considerations

### File Storage
- **Efficient Storage**: Files stored in organized directory structure
- **Size Optimization**: File size formatting for display
- **Cleanup Processes**: Automatic cleanup of orphaned files

### Database Optimization
- **Indexed Queries**: Efficient queries for file retrieval
- **Selective Loading**: Load only necessary file metadata
- **Bulk Operations**: Support for bulk file operations

### Memory Management
- **Streaming Downloads**: Efficient file download handling
- **Preview Generation**: Memory-efficient file preview
- **Error Handling**: Proper resource cleanup on errors

## Security Features

### File Security
- **Access Control**: Country and user-based access restrictions
- **Permission Validation**: Comprehensive permission checking
- **Audit Logging**: Complete tracking of file operations

### Data Protection
- **User Isolation**: Users can only access their country's files
- **File Validation**: Comprehensive file format and content validation
- **Error Handling**: Secure error messages without data exposure

### Audit Trail
- **Operation Logging**: All file operations are logged
- **User Attribution**: All actions attributed to specific users
- **Timestamp Tracking**: Complete timing information for all operations

## Monitoring and Maintenance

### File Management
- **Storage Monitoring**: Track disk usage and file counts
- **Access Patterns**: Monitor file access and usage patterns
- **Error Tracking**: Track and analyze file operation errors

### Performance Monitoring
- **Upload Performance**: Monitor file upload speeds and success rates
- **Download Performance**: Track download performance and user experience
- **Processing Times**: Monitor file processing and preview generation times

### Maintenance Tasks
- **Orphaned File Cleanup**: Remove files without associated records
- **Storage Optimization**: Optimize file storage and organization
- **Log Rotation**: Manage log files and prevent storage bloat

## Future Enhancements

### Planned Features
- **File Versioning**: Support for file version control
- **Advanced Preview**: Enhanced file preview capabilities
- **Batch Operations**: Support for bulk file operations
- **File Compression**: Automatic file compression for storage optimization

### Scalability Improvements
- **Cloud Storage**: Integration with cloud storage providers
- **CDN Integration**: Content delivery network for file downloads
- **Async Processing**: Background file processing for large files
- **Caching Layer**: File metadata caching for performance

---

**Module Version**: 1.0  
**Last Updated**: December 2024  
**Documentation Status**: Complete ✅
