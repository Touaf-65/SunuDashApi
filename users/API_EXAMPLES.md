# Users API - Examples and Usage

## Authentication Examples

### 1. Create Superuser (First Time Setup)

```bash
curl -X POST http://localhost:8000/users/create_superuser/ \
  -H "Content-Type: application/json" \
  -d '{
    "first_name": "Admin",
    "last_name": "System",
    "email": "admin@sunudash.com"
  }'
```

**Response:**
```json
{
  "message": "Superutilisateur créé avec succès",
  "username": "admin.system",
  "password": "Ax7Kp9mN2qRw"
}
```

### 2. User Login

```bash
curl -X POST http://localhost:8000/users/login/ \
  -H "Content-Type: application/json" \
  -d '{
    "login": "admin.system",
    "password": "Ax7Kp9mN2qRw"
  }'
```

**Response:**
```json
{
  "access_token": "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9...",
  "refresh_token": "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9...",
  "username": "admin.system",
  "email": "admin@sunudash.com",
  "role": "SUPERUSER"
}
```

### 3. Password Reset Request

```bash
curl -X POST http://localhost:8000/users/password_reset/ \
  -H "Content-Type: application/json" \
  -d '{
    "email": "user@example.com"
  }'
```

**Response:**
```json
{
  "message": "Un email de réinitialisation de mot de passe a été envoyé."
}
```

## Global Administrators Management

### 4. Create Global Admin

```bash
curl -X POST http://localhost:8000/users/global_admins/create/ \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer YOUR_ACCESS_TOKEN" \
  -d '{
    "first_name": "Global",
    "last_name": "Admin",
    "email": "global.admin@example.com"
  }'
```

**Response:**
```json
{
  "message": "Administrateur global créé avec succès",
  "username": "global.admin",
  "password": "Kj8mN2pQ9rSx"
}
```

### 5. List Global Admins

```bash
curl -X GET http://localhost:8000/users/global_admins/list/ \
  -H "Authorization: Bearer YOUR_ACCESS_TOKEN"
```

**Response:**
```json
[
  {
    "id": 2,
    "username": "global.admin",
    "email": "global.admin@example.com",
    "first_name": "Global",
    "last_name": "Admin",
    "country": null,
    "role": "ADMIN_GLOBAL",
    "is_active": true
  }
]
```

### 6. Import Global Admins from Excel

```bash
curl -X POST http://localhost:8000/users/global_admins/import_create/ \
  -H "Authorization: Bearer YOUR_ACCESS_TOKEN" \
  -F "file=@global_admins.xlsx"
```

**Excel Format:**
| first_name | last_name | email | role |
|------------|-----------|-------|------|
| John | Doe | john.doe@example.com | Administrateur Global |
| Jane | Smith | jane.smith@example.com | Admin Global |

**Response:**
```json
{
  "message": "2 administrateur(s) global(aux) créé(s) avec succès.",
  "lignes_ignores": 0
}
```

## Territorial Administrators Management

### 7. Create Territorial Admin

```bash
curl -X POST http://localhost:8000/users/territorial_admins/create/ \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer YOUR_ACCESS_TOKEN" \
  -d '{
    "first_name": "Territorial",
    "last_name": "Admin",
    "email": "territorial.admin@example.com"
  }'
```

### 8. Assign Country to Territorial Admin

```bash
curl -X POST http://localhost:8000/users/territorial_admins/assign/ \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer YOUR_ACCESS_TOKEN" \
  -d '{
    "user_id": 3,
    "country_id": 1
  }'
```

**Response:**
```json
{
  "message": "Pays assigné avec succès à l'administrateur territorial",
  "admin": {
    "id": 3,
    "username": "territorial.admin",
    "email": "territorial.admin@example.com",
    "country": {
      "id": 1,
      "name": "Senegal",
      "code": "SN"
    }
  }
}
```

### 9. List Territorial Admins

```bash
curl -X GET http://localhost:8000/users/territorial_admins/list/ \
  -H "Authorization: Bearer YOUR_ACCESS_TOKEN"
```

**Response:**
```json
[
  {
    "id": 3,
    "username": "territorial.admin",
    "email": "territorial.admin@example.com",
    "first_name": "Territorial",
    "last_name": "Admin",
    "country": {
      "id": 1,
      "name": "Senegal",
      "code": "SN"
    },
    "role": "ADMIN_TERRITORIAL",
    "is_active": true
  }
]
```

## Simple Users Management

### 10. Create User by Territorial Admin

```bash
curl -X POST http://localhost:8000/users/territorial_admins/users/create_user/ \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer TERRITORIAL_ADMIN_TOKEN" \
  -d '{
    "first_name": "Technical",
    "last_name": "Manager",
    "email": "tech.manager@example.com",
    "role": "CHEF_DEPT_TECH"
  }'
```

**Response:**
```json
{
  "message": "Utilisateur créé avec succès",
  "username": "technical.manager",
  "password": "Pq9rSx2kL8mN"
}
```

### 11. Import Users from Excel (Territorial Admin)

```bash
curl -X POST http://localhost:8000/users/territorial_admins/users/import_create_user/ \
  -H "Authorization: Bearer TERRITORIAL_ADMIN_TOKEN" \
  -F "file=@users.xlsx"
```

**Excel Format:**
| firstname | lastname | email | role |
|-----------|----------|-------|------|
| John | Manager | john.manager@example.com | Chef Département Technique |
| Sarah | Operator | sarah.operator@example.com | Responsable Opérateur |

### 12. List Simple Users

```bash
curl -X GET http://localhost:8000/users/territorial_admins/users/list/ \
  -H "Authorization: Bearer TERRITORIAL_ADMIN_TOKEN"
```

**Response:**
```json
[
  {
    "id": 4,
    "username": "technical.manager",
    "email": "tech.manager@example.com",
    "first_name": "Technical",
    "last_name": "Manager",
    "country": {
      "id": 1,
      "name": "Senegal",
      "code": "SN"
    },
    "role": "CHEF_DEPT_TECH",
    "is_active": true
  }
]
```

## User Status Management

### 13. Toggle User Active Status

```bash
curl -X POST http://localhost:8000/users/users/4/toggle-active/ \
  -H "Authorization: Bearer YOUR_ACCESS_TOKEN"
```

**Response:**
```json
{
  "message": "Utilisateur désactivé avec succès",
  "is_active": false
}
```

## Error Handling Examples

### 400 Bad Request - Missing Required Fields

```bash
curl -X POST http://localhost:8000/users/global_admins/create/ \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer YOUR_ACCESS_TOKEN" \
  -d '{
    "first_name": "Admin"
  }'
```

**Response:**
```json
{
  "detail": "Le champ last_name est requis."
}
```

### 401 Unauthorized - Invalid Token

```bash
curl -X GET http://localhost:8000/users/global_admins/list/ \
  -H "Authorization: Bearer INVALID_TOKEN"
```

**Response:**
```json
{
  "detail": "Given token not valid for any token type"
}
```

### 403 Forbidden - Insufficient Permissions

```bash
curl -X POST http://localhost:8000/users/global_admins/create/ \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer TERRITORIAL_ADMIN_TOKEN" \
  -d '{
    "first_name": "Admin",
    "last_name": "Global",
    "email": "admin@example.com"
  }'
```

**Response:**
```json
{
  "detail": "You do not have permission to perform this action."
}
```

### 404 Not Found - User Doesn't Exist

```bash
curl -X GET http://localhost:8000/users/global_admins/999/ \
  -H "Authorization: Bearer YOUR_ACCESS_TOKEN"
```

**Response:**
```json
{
  "error": "Administrateur global non trouvé"
}
```

## Python Client Examples

### Using requests library

```python
import requests

# Base URL
BASE_URL = "http://localhost:8000"

# Login
def login(username, password):
    response = requests.post(f"{BASE_URL}/users/login/", json={
        "login": username,
        "password": password
    })
    return response.json()

# Create global admin
def create_global_admin(token, first_name, last_name, email):
    headers = {"Authorization": f"Bearer {token}"}
    response = requests.post(f"{BASE_URL}/users/global_admins/create/", 
                           json={"first_name": first_name, "last_name": last_name, "email": email},
                           headers=headers)
    return response.json()

# Usage
login_data = login("admin.system", "password123")
token = login_data["access_token"]

admin_data = create_global_admin(token, "John", "Doe", "john.doe@example.com")
print(admin_data)
```

### Using Django REST Framework test client

```python
from django.test import TestCase
from django.urls import reverse
from rest_framework.test import APIClient
from users.models import CustomUser

class UserAPITestCase(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.superuser = CustomUser.objects.create_superuser(
            first_name="Admin",
            last_name="Test",
            email="admin@test.com",
            password="testpass123"
        )
        self.client.force_authenticate(user=self.superuser)

    def test_create_global_admin(self):
        url = reverse('register_globalal_admin')
        data = {
            "first_name": "Global",
            "last_name": "Admin",
            "email": "global@test.com"
        }
        response = self.client.post(url, data)
        self.assertEqual(response.status_code, 201)
        self.assertIn("username", response.data)
```

## JavaScript/Frontend Examples

### Using fetch API

```javascript
// Login function
async function login(login, password) {
    const response = await fetch('/users/login/', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
        },
        body: JSON.stringify({ login, password })
    });
    return response.json();
}

// Create global admin
async function createGlobalAdmin(token, userData) {
    const response = await fetch('/users/global_admins/create/', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
            'Authorization': `Bearer ${token}`
        },
        body: JSON.stringify(userData)
    });
    return response.json();
}

// Usage
const loginData = await login('admin.system', 'password123');
const token = loginData.access_token;

const adminData = await createGlobalAdmin(token, {
    first_name: 'John',
    last_name: 'Doe',
    email: 'john.doe@example.com'
});
console.log(adminData);
```

### Using axios

```javascript
import axios from 'axios';

// Configure base URL
axios.defaults.baseURL = 'http://localhost:8000';

// Login
const login = async (login, password) => {
    const response = await axios.post('/users/login/', { login, password });
    return response.data;
};

// Create global admin with interceptor for auth
axios.interceptors.request.use(config => {
    const token = localStorage.getItem('access_token');
    if (token) {
        config.headers.Authorization = `Bearer ${token}`;
    }
    return config;
});

const createGlobalAdmin = async (userData) => {
    const response = await axios.post('/users/global_admins/create/', userData);
    return response.data;
};

// Usage
const loginData = await login('admin.system', 'password123');
localStorage.setItem('access_token', loginData.access_token);

const adminData = await createGlobalAdmin({
    first_name: 'John',
    last_name: 'Doe',
    email: 'john.doe@example.com'
});
```

## File Upload Examples

### Excel File Upload for Bulk User Creation

```bash
# Create global admins from Excel
curl -X POST http://localhost:8000/users/global_admins/import_create/ \
  -H "Authorization: Bearer YOUR_ACCESS_TOKEN" \
  -F "file=@global_admins.xlsx"

# Create territorial admins from Excel
curl -X POST http://localhost:8000/users/territorial_admins/import_create/ \
  -H "Authorization: Bearer YOUR_ACCESS_TOKEN" \
  -F "file=@territorial_admins.xlsx"

# Create simple users from Excel (by territorial admin)
curl -X POST http://localhost:8000/users/territorial_admins/users/import_create_user/ \
  -H "Authorization: Bearer TERRITORIAL_ADMIN_TOKEN" \
  -F "file=@users.xlsx"
```

### Python file upload example

```python
import requests

def upload_users_excel(token, file_path, endpoint):
    with open(file_path, 'rb') as file:
        files = {'file': file}
        headers = {'Authorization': f'Bearer {token}'}
        response = requests.post(endpoint, files=files, headers=headers)
        return response.json()

# Usage
result = upload_users_excel(
    token,
    'users.xlsx',
    'http://localhost:8000/users/territorial_admins/users/import_create_user/'
)
print(result)
```
