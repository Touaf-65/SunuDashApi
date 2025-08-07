# Users Module - Permissions System Guide

## Overview

The Users module implements a hierarchical permission system that controls access to different API endpoints based on user roles and country assignments. This guide explains how permissions work and how to use them effectively.

## Permission Classes

### 1. IsSuperUser
**File**: `users/permissions.py`

```python
class IsSuperUser(BasePermission):
    def has_permission(self, request, view):
        return request.user.is_authenticated and request.user.is_superuser_role()
```

**Usage**: Restricts access to superusers only
**Applied to**: Global admin management endpoints

### 2. IsGlobalAdmin
**File**: `users/permissions.py`

```python
class IsGlobalAdmin(BasePermission):
    def has_permission(self, request, view):
        return request.user.is_authenticated and request.user.is_admin_global()
```

**Usage**: Restricts access to global administrators
**Applied to**: Territorial admin management endpoints

### 3. IsTerritorialAdmin
**File**: `users/permissions.py`

```python
class IsTerritorialAdmin(BasePermission):
    def has_permission(self, request, view):
        return request.user.is_authenticated and request.user.is_admin_territorial()
```

**Usage**: Restricts access to territorial administrators
**Applied to**: Simple user management endpoints

### 4. IsTerritorialAdminAndAssignedCountry
**File**: `users/permissions.py`

```python
class IsTerritorialAdminAndAssignedCountry(BasePermission):
    def has_permission(self, request, view):
        user = request.user
        return (
            user.is_authenticated and 
            user.role == user.Roles.ADMIN_TERRITORIAL and 
            user.country is not None
        )
```

**Usage**: Ensures territorial admin has an assigned country
**Applied to**: User management within specific countries

### 5. HasAccessCountry
**File**: `users/permissions.py`

```python
class HasAccessCountry(BasePermission):
    def has_permission(self, request, view):
        user = request.user
        if not user.is_authenticated:
            return False
        if user.is_superuser_role() or user.is_admin_global():
            return True
        return user.country is not None
```

**Usage**: Allows access to country-specific data
**Applied to**: Dashboard and data access endpoints

## Role Hierarchy

```
SUPERUSER
├── Can manage all users
├── Can create/update/delete global admins
├── Can access all system data
└── Can toggle any user's active status

ADMIN_GLOBAL
├── Can manage territorial admins
├── Can assign countries to territorial admins
├── Can create/update/delete territorial admins
└── Can toggle territorial admin status

ADMIN_TERRITORIAL
├── Can manage simple users in assigned country
├── Can create/update/delete simple users
├── Can import users from Excel
└── Can toggle simple user status

CHEF_DEPT_TECH
├── Can access country-specific data
└── No user management permissions

RESP_OPERATEUR
├── Can access country-specific data
└── No user management permissions
```

## Permission Matrix

| Endpoint | SUPERUSER | ADMIN_GLOBAL | ADMIN_TERRITORIAL | CHEF_DEPT_TECH | RESP_OPERATEUR |
|----------|-----------|--------------|-------------------|----------------|----------------|
| Create Superuser | ✅ | ❌ | ❌ | ❌ | ❌ |
| Login | ✅ | ✅ | ✅ | ✅ | ✅ |
| Password Reset | ✅ | ✅ | ✅ | ✅ | ✅ |
| Create Global Admin | ✅ | ❌ | ❌ | ❌ | ❌ |
| List Global Admins | ✅ | ❌ | ❌ | ❌ | ❌ |
| Update Global Admin | ✅ | ❌ | ❌ | ❌ | ❌ |
| Delete Global Admin | ✅ | ❌ | ❌ | ❌ | ❌ |
| Create Territorial Admin | ✅ | ✅ | ❌ | ❌ | ❌ |
| List Territorial Admins | ✅ | ✅ | ❌ | ❌ | ❌ |
| Update Territorial Admin | ✅ | ✅ | ❌ | ❌ | ❌ |
| Delete Territorial Admin | ✅ | ✅ | ❌ | ❌ | ❌ |
| Assign Country | ✅ | ✅ | ❌ | ❌ | ❌ |
| Create Simple User | ✅ | ✅ | ✅* | ❌ | ❌ |
| List Simple Users | ✅ | ✅ | ✅* | ❌ | ❌ |
| Update Simple User | ✅ | ✅ | ✅* | ❌ | ❌ |
| Delete Simple User | ✅ | ✅ | ✅* | ❌ | ❌ |
| Toggle User Status | ✅** | ✅*** | ✅**** | ❌ | ❌ |

*Only for users in assigned country
**Can toggle any user
***Can toggle territorial admins and simple users
****Can toggle only simple users in assigned country

## Country-Based Access Control

### Territorial Admin Country Assignment

Territorial admins must have a country assigned to access user management features:

```python
# Check if territorial admin has assigned country
if user.role == user.Roles.ADMIN_TERRITORIAL and user.country is None:
    # Cannot access user management
    return False
```

### Simple User Country Inheritance

When territorial admins create simple users, the users automatically inherit the admin's country:

```python
# In CreateUserByTerritorialAdmin view
user = CustomUser.objects.create_user(
    first_name=first_name,
    last_name=last_name,
    email=email,
    password=password,
    role=role,
    country=request.user.country  # Inherit from territorial admin
)
```

## Custom Permission Implementation

### Creating Custom Permissions

To create a new permission class:

```python
from rest_framework.permissions import BasePermission

class IsChefDeptTech(BasePermission):
    def has_permission(self, request, view):
        return request.user.is_authenticated and request.user.is_chef_dept_tech()

class IsResponsableOperateur(BasePermission):
    def has_permission(self, request, view):
        return request.user.is_authenticated and request.user.is_responsable_operateur()
```

### Using Multiple Permissions

You can combine multiple permission classes:

```python
class CreateUserByTerritorialAdmin(APIView):
    permission_classes = [
        IsAuthenticated, 
        IsTerritorialAdmin, 
        IsTerritorialAdminAndAssignedCountry
    ]
```

### Conditional Permissions

For more complex permission logic, you can override `has_permission`:

```python
class CustomPermission(BasePermission):
    def has_permission(self, request, view):
        user = request.user
        
        # Superusers can do anything
        if user.is_superuser_role():
            return True
            
        # Global admins can manage their own data
        if user.is_admin_global():
            return True
            
        # Territorial admins can only access their country's data
        if user.is_admin_territorial():
            return user.country is not None
            
        return False
```

## Testing Permissions

### Unit Tests for Permissions

```python
from django.test import TestCase
from rest_framework.test import APIClient
from users.models import CustomUser
from users.permissions import IsSuperUser, IsGlobalAdmin

class PermissionTestCase(TestCase):
    def setUp(self):
        self.client = APIClient()
        
    def test_superuser_permission(self):
        # Create superuser
        superuser = CustomUser.objects.create_superuser(
            first_name="Admin",
            last_name="Test",
            email="admin@test.com",
            password="testpass123"
        )
        
        # Test permission
        permission = IsSuperUser()
        self.assertTrue(permission.has_permission(None, None))
        
    def test_global_admin_permission(self):
        # Create global admin
        admin = CustomUser.objects.create_user(
            first_name="Global",
            last_name="Admin",
            email="global@test.com",
            password="testpass123",
            role=CustomUser.Roles.ADMIN_GLOBAL
        )
        
        # Test permission
        permission = IsGlobalAdmin()
        self.assertTrue(permission.has_permission(None, None))
```

### Integration Tests

```python
from django.test import TestCase
from django.urls import reverse
from rest_framework.test import APIClient
from users.models import CustomUser

class UserAPIPermissionTestCase(TestCase):
    def setUp(self):
        self.client = APIClient()
        
    def test_global_admin_cannot_create_superuser(self):
        # Create global admin
        admin = CustomUser.objects.create_user(
            first_name="Global",
            last_name="Admin",
            email="global@test.com",
            password="testpass123",
            role=CustomUser.Roles.ADMIN_GLOBAL
        )
        
        self.client.force_authenticate(user=admin)
        
        # Try to create superuser
        url = reverse('create_superuser')
        data = {
            "first_name": "Test",
            "last_name": "Superuser",
            "email": "test@example.com"
        }
        
        response = self.client.post(url, data)
        self.assertEqual(response.status_code, 403)
        
    def test_territorial_admin_needs_country_assignment(self):
        # Create territorial admin without country
        admin = CustomUser.objects.create_user(
            first_name="Territorial",
            last_name="Admin",
            email="territorial@test.com",
            password="testpass123",
            role=CustomUser.Roles.ADMIN_TERRITORIAL
        )
        
        self.client.force_authenticate(user=admin)
        
        # Try to create user
        url = reverse('create_user_by_territorial_admin')
        data = {
            "first_name": "Test",
            "last_name": "User",
            "email": "test@example.com",
            "role": "CHEF_DEPT_TECH"
        }
        
        response = self.client.post(url, data)
        self.assertEqual(response.status_code, 403)
```

## Security Best Practices

### 1. Always Validate Permissions

```python
# Good: Check permissions in views
def post(self, request):
    if not request.user.is_admin_global():
        return Response({'error': 'Permission denied'}, status=403)
    
    # Process request
```

### 2. Use Permission Classes

```python
# Better: Use permission classes
class CreateGlobalAdminView(APIView):
    permission_classes = [IsAuthenticated, IsSuperUser]
    
    def post(self, request):
        # Permission already checked
        # Process request
```

### 3. Validate Country Access

```python
# Ensure users can only access their assigned country
def get_users_in_country(self, request):
    user = request.user
    
    if user.is_superuser_role() or user.is_admin_global():
        # Can see all users
        return CustomUser.objects.all()
    elif user.is_admin_territorial():
        # Can only see users in assigned country
        return CustomUser.objects.filter(country=user.country)
    else:
        # No access
        return CustomUser.objects.none()
```

### 4. Audit Trail

```python
# Log permission checks for security auditing
import logging

logger = logging.getLogger(__name__)

class AuditPermission(BasePermission):
    def has_permission(self, request, view):
        user = request.user
        action = f"{request.method} {view.__class__.__name__}"
        
        logger.info(f"Permission check: {user.username} ({user.role}) - {action}")
        
        # Check permission
        has_access = super().has_permission(request, view)
        
        if not has_access:
            logger.warning(f"Permission denied: {user.username} - {action}")
            
        return has_access
```

## Troubleshooting

### Common Permission Issues

1. **403 Forbidden**: Check if user has the correct role
2. **Country not assigned**: Ensure territorial admin has country assignment
3. **Token expired**: Refresh authentication token
4. **Incorrect role**: Verify user role in database

### Debugging Permissions

```python
# Add debug logging to permission classes
class DebugPermission(BasePermission):
    def has_permission(self, request, view):
        user = request.user
        print(f"Debug: User {user.username} has role {user.role}")
        print(f"Debug: User country: {user.country}")
        print(f"Debug: User is authenticated: {user.is_authenticated}")
        
        # Your permission logic here
        return True
```

### Permission Testing Checklist

- [ ] User is authenticated
- [ ] User has correct role
- [ ] User has required country assignment (if applicable)
- [ ] User is active
- [ ] Token is valid and not expired
- [ ] Endpoint permissions are correctly configured
