# File Handling Module - Integration Guide

## Overview

The File Handling module integrates with multiple modules to provide comprehensive file management capabilities. This guide explains how the module interacts with other system components and provides integration patterns for developers.

## Module Integration Architecture

```
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   Users Module  │    │ File Handling   │    │  Importer       │
│                 │    │     Module      │    │    Module       │
│ • Permissions   │◄───┤                 │◄───┤                 │
│ • Access Control│    │ • File Upload   │    │ • File Processing│
│ • Country Based │    │ • Session Mgmt  │    │ • Data Mapping  │
└─────────────────┘    │ • Audit Trail   │    │ • Import Logic  │
                       └─────────────────┘    └─────────────────┘
                                │                       │
                                ▼                       ▼
                       ┌─────────────────┐    ┌─────────────────┐
                       │   Core Module   │    │   Dashboard     │
                       │                 │    │     Module      │
                       │ • File Assoc    │    │                 │
                       │ • Import Track  │    │ • File Stats    │
                       │ • Data Lineage  │    │ • Session Stats │
                       └─────────────────┘    └─────────────────┘
```

## Integration Points

### 1. Users Module Integration

#### Permission-Based Access Control
The File Handling module uses the Users module's permission system for access control.

**Integration Features**:
```python
# Permission classes used
from users.permissions import (
    IsTerritorialAdmin, 
    IsTerritorialAdminAndAssignedCountry, 
    IsChefDeptTech
)

# Access control implementation
class FileListView(APIView):
    permission_classes = [
        IsAuthenticated, 
        IsTerritorialAdminAndAssignedCountry | IsChefDeptTech
    ]
    
    def get(self, request):
        # Filter files by user's country
        files = File.objects.filter(country=request.user.country)
```

**Access Control Features**:
- **Country-Based Filtering**: Users can only access files from their assigned country
- **Role-Based Permissions**: Different access levels based on user roles
- **Ownership Control**: Users can only delete their own files (with admin exceptions)
- **Audit Trail**: Track user actions on files

#### User Information Integration
```python
# Automatic user information population
def save(self, *args, **kwargs):
    if self.user:
        if not self.uploaded_by_name:
            full_name = f"{self.user.first_name} {self.user.last_name}".strip()
            self.uploaded_by_name = full_name or self.user.email
        if not self.uploaded_by_email:
            self.uploaded_by_email = self.user.email
```

### 2. Importer Module Integration

#### File Processing Coordination
The File Handling module provides the foundation for the Importer module's file processing capabilities.

**Integration Points**:
```python
# File model used by importer
class ImportSession(models.Model):
    stat_file = models.ForeignKey(File, on_delete=models.CASCADE, related_name='stat_sessions')
    recap_file = models.ForeignKey(File, on_delete=models.CASCADE, related_name='recap_sessions')
```

**Processing Workflow**:
1. **File Upload**: Files uploaded through File Handling module
2. **Session Creation**: Import sessions created with file references
3. **Processing**: Importer module processes files using session information
4. **Status Updates**: Import session status updated during processing
5. **Error Handling**: Error files and logs managed by File Handling module

#### Session Management
```python
# Import session tracking
class ImportSession(models.Model):
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    error_file = models.FileField(upload_to='error_reports/', null=True, blank=True)
    log_file_path = models.CharField(max_length=500, blank=True, null=True)
```

### 3. Core Module Integration

#### File Association
All Core module models can link to source files for data lineage.

**Integration Features**:
```python
# Core models include file references
class Client(models.Model):
    file = models.ForeignKey(File, on_delete=models.SET_NULL, null=True, blank=True, related_name='clients')
    import_session = models.ForeignKey(ImportSession, on_delete=models.SET_NULL, null=True, blank=True, related_name='imported_clients')

class Policy(models.Model):
    file = models.ForeignKey(File, on_delete=models.SET_NULL, null=True, blank=True, related_name='policies')
    import_session = models.ForeignKey(ImportSession, on_delete=models.SET_NULL, null=True, blank=True, related_name='imported_policies')
```

**Data Lineage Features**:
- **Source Tracking**: Track which file imported each record
- **Import History**: Complete import session history
- **Audit Trail**: Full audit trail for data imports
- **Reimport Support**: Support for data reimport and updates

#### Import Session Tracking
```python
# All Core models track import sessions
class Claim(models.Model):
    file = models.ForeignKey(File, on_delete=models.SET_NULL, null=True, blank=True, related_name='claims')
    import_session = models.ForeignKey(ImportSession, on_delete=models.SET_NULL, null=True, blank=True, related_name='imported_claims')
```

### 4. Dashboard Module Integration

#### File Statistics
The Dashboard module can consume file and session statistics for reporting.

**Integration Examples**:
```python
# File statistics for dashboard
def get_file_statistics(country):
    return {
        'total_files': File.objects.filter(country=country).count(),
        'stat_files': File.objects.filter(country=country, file_type='stat').count(),
        'recap_files': File.objects.filter(country=country, file_type='recap').count(),
        'recent_uploads': File.objects.filter(
            country=country, 
            uploaded_at__gte=timezone.now() - timedelta(days=7)
        ).count()
    }

# Import session statistics
def get_import_session_statistics(country):
    return {
        'total_sessions': ImportSession.objects.filter(country=country).count(),
        'successful_imports': ImportSession.objects.filter(
            country=country, 
            status=ImportSession.Status.DONE
        ).count(),
        'failed_imports': ImportSession.objects.filter(
            country=country, 
            status=ImportSession.Status.ERROR
        ).count()
    }
```

## Data Flow Patterns

### 1. File Upload Flow

```
User Upload → Permission Check → File Validation → Storage → Session Creation → Processing
```

**Detailed Flow**:
1. **User Upload**: User uploads files through API
2. **Permission Check**: Validate user permissions and country access
3. **File Validation**: Validate file format and content
4. **Storage**: Store file in configured directory
5. **Session Creation**: Create import session with file references
6. **Processing**: Trigger file processing by importer module

### 2. File Access Flow

```
User Request → Permission Validation → Country Filter → File Retrieval → Response
```

**Detailed Flow**:
1. **User Request**: User requests file access
2. **Permission Validation**: Check user permissions and role
3. **Country Filter**: Filter files by user's country
4. **File Retrieval**: Retrieve file with appropriate access level
5. **Response**: Return file data or download

### 3. Import Session Flow

```
Session Creation → File Association → Processing → Status Updates → Completion
```

**Detailed Flow**:
1. **Session Creation**: Create import session with metadata
2. **File Association**: Link files to import session
3. **Processing**: Process files through importer module
4. **Status Updates**: Update session status during processing
5. **Completion**: Mark session as complete with results

## API Integration Patterns

### 1. File Upload Integration

```python
# Example file upload integration
def upload_files(request):
    stat_file = request.FILES.get('stat_file')
    recap_file = request.FILES.get('recap_file')
    
    # Create files
    stat_file_obj = File.objects.create(
        user=request.user,
        file=stat_file,
        file_type='stat',
        country=request.user.country
    )
    
    recap_file_obj = File.objects.create(
        user=request.user,
        file=recap_file,
        file_type='recap',
        country=request.user.country
    )
    
    # Create import session
    import_session = ImportSession.objects.create(
        user=request.user,
        country=request.user.country,
        stat_file=stat_file_obj,
        recap_file=recap_file_obj
    )
    
    return import_session
```

### 2. File Access Integration

```python
# Example file access integration
def get_user_files(request):
    # Filter by user's country
    files = File.objects.filter(country=request.user.country)
    
    # Apply role-based filtering
    if not request.user.is_admin_territorial:
        files = files.filter(user=request.user)
    
    return files
```

### 3. Session Management Integration

```python
# Example session management integration
def get_import_sessions(request):
    sessions = ImportSession.objects.filter(country=request.user.country)
    
    # Include file information
    sessions = sessions.select_related('stat_file', 'recap_file')
    
    return sessions
```

## Error Handling Integration

### 1. Permission Errors
```python
# Handle permission errors
try:
    file = File.objects.get(pk=file_id)
    if file.country != request.user.country:
        return Response({"detail": "Access denied"}, status=403)
except File.DoesNotExist:
    return Response({"detail": "File not found"}, status=404)
```

### 2. File Processing Errors
```python
# Handle file processing errors
try:
    df = open_excel_csv(file.file)
    return Response({"preview": df.head(10).to_dict()})
except Exception as e:
    return Response({"detail": f"Error reading file: {str(e)}"}, status=400)
```

### 3. Session Errors
```python
# Handle session errors
try:
    session = ImportSession.objects.get(pk=session_id)
    if session.country != request.user.country:
        return Response({"detail": "Access denied"}, status=403)
except ImportSession.DoesNotExist:
    return Response({"detail": "Session not found"}, status=404)
```

## Security Integration

### 1. Access Control Integration
```python
# Comprehensive access control
class FileAccessMixin:
    def get_queryset(self):
        user = self.request.user
        
        if user.is_superuser_role() or user.is_admin_global():
            return File.objects.all()
        elif user.is_admin_territorial():
            return File.objects.filter(country=user.country)
        else:
            return File.objects.filter(user=user, country=user.country)
```

### 2. File Security
```python
# File security measures
def secure_file_download(request, file_id):
    file = get_object_or_404(File, pk=file_id)
    
    # Check permissions
    if file.country != request.user.country:
        return Response({"detail": "Access denied"}, status=403)
    
    # Check ownership (except for admins)
    if file.user != request.user and not request.user.is_admin_territorial:
        return Response({"detail": "Access denied"}, status=403)
    
    return FileResponse(open(file.file.path, 'rb'), as_attachment=True)
```

## Performance Integration

### 1. Database Optimization
```python
# Optimized queries
def get_files_with_metadata(country):
    return File.objects.filter(country=country).select_related('user', 'country')

def get_sessions_with_files(country):
    return ImportSession.objects.filter(country=country).select_related(
        'stat_file', 'recap_file', 'user', 'country'
    )
```

### 2. Caching Integration
```python
# Caching for file metadata
from django.core.cache import cache

def get_file_statistics(country):
    cache_key = f"file_stats_{country.id}"
    stats = cache.get(cache_key)
    
    if not stats:
        stats = {
            'total_files': File.objects.filter(country=country).count(),
            'recent_uploads': File.objects.filter(
                country=country,
                uploaded_at__gte=timezone.now() - timedelta(days=7)
            ).count()
        }
        cache.set(cache_key, stats, 300)  # Cache for 5 minutes
    
    return stats
```

## Monitoring Integration

### 1. File Operation Monitoring
```python
# Monitor file operations
import logging

logger = logging.getLogger(__name__)

def log_file_operation(user, operation, file_id, success=True):
    logger.info(f"File operation: {operation} by {user.username} on file {file_id}, success: {success}")
```

### 2. Performance Monitoring
```python
# Monitor file processing performance
import time

def monitor_file_processing(func):
    def wrapper(*args, **kwargs):
        start_time = time.time()
        result = func(*args, **kwargs)
        end_time = time.time()
        
        logger.info(f"File processing took {end_time - start_time:.2f} seconds")
        return result
    return wrapper
```

## Future Integration Enhancements

### 1. Real-Time Updates
- **WebSocket Integration**: Real-time file upload progress
- **Event Streaming**: Stream file processing events
- **Live Status Updates**: Real-time import session status

### 2. Advanced Analytics
- **File Usage Analytics**: Track file access patterns
- **Processing Analytics**: Monitor processing performance
- **Error Analytics**: Analyze and categorize errors

### 3. External Integrations
- **Cloud Storage**: Integration with cloud storage providers
- **File Processing Services**: Integration with external processing services
- **Notification Services**: Integration with notification systems

---

**Integration Guide Version**: 1.0  
**Last Updated**: December 2024  
**Status**: Complete ✅
