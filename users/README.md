# Users Module - Sunu Dash API

## Overview

The Users module provides comprehensive user management functionality for the Sunu Dash platform. It handles authentication, user creation, role management, and country assignments with a hierarchical permission system.

## User Roles Hierarchy

1. **SUPERUSER** - Full system access
2. **ADMIN_GLOBAL** - Global administrator with country management capabilities
3. **ADMIN_TERRITORIAL** - Territorial administrator assigned to specific countries
4. **CHEF_DEPT_TECH** - Technical department head
5. **RESP_OPERATEUR** - Data entry manager

## Models

### CustomUser
```python
class CustomUser(AbstractUser, PermissionsMixin):
    email = models.EmailField(unique=True)
    country = models.ForeignKey(Country, on_delete=models.SET_NULL, null=True, blank=True)
    role = models.CharField(max_length=32, choices=Roles.choices, default=Roles.RESP_OPERATEUR)
```

### PasswordResetToken
```python
class PasswordResetToken(models.Model):
    user = models.ForeignKey(CustomUser, on_delete=models.CASCADE)
    token = models.UUIDField(default=uuid.uuid4, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)
```

## API Endpoints

### Authentication & User Management

#### 1. Create Superuser
- **URL**: `POST /users/create_superuser/`
- **Permissions**: None (only if no superuser exists)
- **Payload**:
```json
{
    "first_name": "John",
    "last_name": "Doe",
    "email": "admin@example.com"
}
```
- **Response**: 201 Created with user credentials

#### 2. User Login
- **URL**: `POST /users/login/`
- **Permissions**: None
- **Payload**:
```json
{
    "login": "username_or_email",
    "password": "password"
}
```
- **Response**: 200 OK with JWT tokens and user info

#### 3. Get User by Login
- **URL**: `GET /users/getConnectedUser/<str:login>/`
- **Permissions**: None
- **Response**: 200 OK with user details

#### 4. Verify Password
- **URL**: `POST /users/verify_password/`
- **Permissions**: IsAuthenticated
- **Payload**:
```json
{
    "password": "current_password"
}
```
- **Response**: 200 OK with boolean result

### Password Reset

#### 5. Request Password Reset
- **URL**: `POST /users/password_reset/`
- **Permissions**: None
- **Payload**:
```json
{
    "email": "user@example.com"
}
```
- **Response**: 200 OK with confirmation message

#### 6. Confirm Password Reset
- **URL**: `POST /users/password_reset_confirm/`
- **Permissions**: None
- **Payload**:
```json
{
    "token": "uuid-token",
    "new_password": "new_password",
    "confirm_password": "new_password"
}
```
- **Response**: 200 OK with success message

### Global Administrators Management

#### 7. Create Global Admin
- **URL**: `POST /users/global_admins/create/`
- **Permissions**: IsSuperUser
- **Payload**:
```json
{
    "first_name": "Admin",
    "last_name": "Global",
    "email": "global.admin@example.com"
}
```
- **Response**: 201 Created with admin details

#### 8. Import Global Admins from Excel
- **URL**: `POST /users/global_admins/import_create/`
- **Permissions**: IsSuperUser
- **Payload**: Multipart form with Excel file
- **File Format**: Excel with columns: first_name, last_name, email, role (optional)
- **Response**: 200 OK with creation summary

#### 9. List Global Admins
- **URL**: `GET /users/global_admins/list/`
- **Permissions**: IsSuperUser
- **Response**: 200 OK with list of global admins

#### 10. Get Global Admin Details
- **URL**: `GET /users/global_admins/<int:pk>/`
- **Permissions**: IsSuperUser
- **Response**: 200 OK with admin details

#### 11. Update Global Admin
- **URL**: `PUT /users/global_admins/<int:pk>/update/`
- **Permissions**: IsSuperUser
- **Payload**:
```json
{
    "first_name": "Updated",
    "last_name": "Name",
    "email": "updated@example.com"
}
```
- **Response**: 200 OK with updated admin details

#### 12. Delete Global Admin
- **URL**: `DELETE /users/global_admins/<int:pk>/delete/`
- **Permissions**: IsSuperUser
- **Response**: 204 No Content

### Territorial Administrators Management

#### 13. Create Territorial Admin
- **URL**: `POST /users/territorial_admins/create/`
- **Permissions**: IsGlobalAdmin
- **Payload**:
```json
{
    "first_name": "Territorial",
    "last_name": "Admin",
    "email": "territorial@example.com"
}
```
- **Response**: 201 Created with admin details

#### 14. Import Territorial Admins from Excel
- **URL**: `POST /users/territorial_admins/import_create/`
- **Permissions**: IsGlobalAdmin
- **Payload**: Multipart form with Excel file
- **File Format**: Excel with columns: first_name, last_name, email
- **Response**: 200 OK with creation summary

#### 15. List Territorial Admins
- **URL**: `GET /users/territorial_admins/list/`
- **Permissions**: IsGlobalAdmin
- **Response**: 200 OK with list of territorial admins

#### 16. Get Territorial Admin Details
- **URL**: `GET /users/territorial_admins/<int:pk>/`
- **Permissions**: IsGlobalAdmin
- **Response**: 200 OK with admin details

#### 17. Update Territorial Admin
- **URL**: `PUT /users/territorial_admins/<int:pk>/update/`
- **Permissions**: IsGlobalAdmin
- **Payload**:
```json
{
    "first_name": "Updated",
    "last_name": "Name",
    "email": "updated@example.com"
}
```
- **Response**: 200 OK with updated admin details

#### 18. Delete Territorial Admin
- **URL**: `DELETE /users/territorial_admins/<int:pk>/delete/`
- **Permissions**: IsGlobalAdmin
- **Response**: 204 No Content

### Country Assignment Management

#### 19. Assign Country to Territorial Admin
- **URL**: `POST /users/territorial_admins/assign/`
- **Permissions**: IsGlobalAdmin
- **Payload**:
```json
{
    "user_id": 123,
    "country_id": 456
}
```
- **Response**: 200 OK with assignment confirmation

#### 20. Unassign/Reassign Country
- **URL**: `POST /users/territorial_admins/change_assign/`
- **Permissions**: IsGlobalAdmin
- **Payload**:
```json
{
    "user_id": 123,
    "country_id": null  // or new country_id
}
```
- **Response**: 200 OK with reassignment confirmation

### Simple Users Management (by Territorial Admins)

#### 21. Create User by Territorial Admin
- **URL**: `POST /users/territorial_admins/users/create_user/`
- **Permissions**: IsTerritorialAdmin, IsTerritorialAdminAndAssignedCountry
- **Payload**:
```json
{
    "first_name": "User",
    "last_name": "Name",
    "email": "user@example.com",
    "role": "CHEF_DEPT_TECH"
}
```
- **Response**: 201 Created with user details

#### 22. Import Users from Excel (by Territorial Admin)
- **URL**: `POST /users/territorial_admins/users/import_create_user/`
- **Permissions**: IsTerritorialAdmin, IsTerritorialAdminAndAssignedCountry
- **Payload**: Multipart form with Excel file
- **File Format**: Excel with columns: firstname, lastname, email, role
- **Response**: 200 OK with creation summary

#### 23. List Simple Users
- **URL**: `GET /users/territorial_admins/users/list/`
- **Permissions**: IsTerritorialAdmin, IsTerritorialAdminAndAssignedCountry
- **Response**: 200 OK with list of users in admin's country

#### 24. Get Simple User Details
- **URL**: `GET /users/territorial_admins/users/<int:pk>/`
- **Permissions**: IsTerritorialAdmin, IsTerritorialAdminAndAssignedCountry
- **Response**: 200 OK with user details

#### 25. Update Simple User
- **URL**: `PUT /users/territorial_admins/users/<int:pk>/update/`
- **Permissions**: IsTerritorialAdmin, IsTerritorialAdminAndAssignedCountry
- **Payload**:
```json
{
    "first_name": "Updated",
    "last_name": "Name",
    "email": "updated@example.com",
    "role": "RESP_OPERATEUR"
}
```
- **Response**: 200 OK with updated user details

#### 26. Delete Simple User
- **URL**: `DELETE /users/territorial_admins/users/<int:pk>/delete/`
- **Permissions**: IsTerritorialAdmin, IsTerritorialAdminAndAssignedCountry
- **Response**: 204 No Content

### User Status Management

#### 27. Toggle User Active Status
- **URL**: `POST /users/users/<int:pk>/toggle-active/`
- **Permissions**: IsAuthenticated (hierarchical)
- **Response**: 200 OK with new status

## Permissions System

### Permission Classes

1. **IsSuperUser**: Only superusers can access
2. **IsGlobalAdmin**: Only global admins can access
3. **IsTerritorialAdmin**: Only territorial admins can access
4. **IsTerritorialAdminAndAssignedCountry**: Territorial admin with assigned country
5. **HasAccessCountry**: User with country access (superuser, global admin, or assigned user)

### Hierarchical Access Control

- **Superusers**: Can manage all users and global admins
- **Global Admins**: Can manage territorial admins and assign countries
- **Territorial Admins**: Can manage simple users within their assigned country
- **Simple Users**: No management permissions

## Serializers

### UserSerializer
Handles user data validation and serialization with country information.

### PasswordResetRequestSerializer
Validates email for password reset requests.

### PasswordResetConfirmSerializer
Validates token and password confirmation for reset.

## Utilities

### generate_password(length=12)
Generates random passwords for new users.

### send_user_email(to_email, subject, plain_text_content, html_content=None)
Sends formatted emails to users with both plain text and HTML versions.

## Authentication Backend

### UsernameOrEmailBackend
Custom authentication backend that allows login with either username or email.

## File Management

The module saves user credentials to text files in the `users_txt/` directory:
- `superuser.txt`: Superuser credentials
- `global_users.txt`: Global admin credentials
- `territorial_users.txt`: Territorial admin credentials
- `simple_users.txt`: Simple user credentials

## Error Handling

All endpoints return appropriate HTTP status codes:
- 200: Success
- 201: Created
- 204: No Content (deletion)
- 400: Bad Request (validation errors)
- 401: Unauthorized
- 403: Forbidden (permission denied)
- 404: Not Found
- 500: Internal Server Error

## Email Templates

The module sends professionally formatted emails for:
- User creation notifications
- Password reset requests
- Password reset confirmations
- Country assignment notifications

All emails include both plain text and HTML versions for maximum compatibility.
