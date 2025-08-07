# Guide d'Uniformisation de la Nomenclature - Sunu Dash API

## 📋 Principes Fondamentaux

Basé sur votre nomenclature du module Dashboard, voici les principes à appliquer uniformément dans tout le projet :

### 1. **Préfixes Géographiques**
- **`Global`** : Données sans filtre sur le pays (tous les pays)
- **`Country`** : Données sur un pays spécifique
- **`Territorial`** : Données territoriales (pour les admins territoriaux)

### 2. **Suffixes Fonctionnels**
- **`Statistics`** : Services et vues qui récupèrent des statistiques
- **`List`** : Services et vues qui récupèrent des listes d'éléments
- **`Detail`** : Services et vues qui récupèrent des détails d'un élément
- **`Create`** : Services et vues qui créent des éléments
- **`Update`** : Services et vues qui mettent à jour des éléments
- **`Delete`** : Services et vues qui suppriment des éléments

### 3. **Structure des URLs**
- **`global/`** : URLs pour les données globales
- **`countries/`** : URLs pour les données par pays
- **`territorial/`** : URLs pour les données territoriales

## 🔄 Analyse de l'État Actuel

### ✅ Module Dashboard (Conforme)
```
Services:
- GlobalStatistics
- CountryStatistics
- GlobalClientStatistics
- CountryClientStatistics
- GlobalPartnerStatistics
- CountryPartnerStatistics

URLs:
- /global/statistics/
- /countries/statistics/
- /global/clients/statistics/
- /countries/<id>/statistics/
```

### ⚠️ Module Users (Partiellement Conforme)
```
Vues actuelles:
- SuperuserCreateAPIView
- LoginUserAPIView
- GlobalAdminListView
- TerritorialAdminListView
- SimpleUserListView

URLs actuelles:
- /create_superuser/
- /global_admins/list/
- /territorial_admins/list/
```

### ⚠️ Module File Handling (Non Conforme)
```
Vues actuelles:
- FileListView
- FileDeleteView
- ImportSessionListView

URLs actuelles:
- /files/
- /import-sessions/
```

### ⚠️ Module Importer (Non Conforme)
```
Vues actuelles:
- FileUploadAndImportView

URLs actuelles:
- /upload/
```

## 🎯 Propositions d'Uniformisation

### Option 1 : Nomenclature Complète (Recommandée)

#### Module Users
```python
# Vues
class GlobalUserCreateView(APIView):
class GlobalUserListView(APIView):
class GlobalUserDetailView(APIView):
class GlobalUserUpdateView(APIView):
class GlobalUserDeleteView(APIView):

class CountryUserCreateView(APIView):
class CountryUserListView(APIView):
class CountryUserDetailView(APIView):
class CountryUserUpdateView(APIView):
class CountryUserDeleteView(APIView):

class TerritorialUserCreateView(APIView):
class TerritorialUserListView(APIView):
class TerritorialUserDetailView(APIView):
class TerritorialUserUpdateView(APIView):
class TerritorialUserDeleteView(APIView):

# URLs
urlpatterns = [
    # Global
    path('global/users/create/', GlobalUserCreateView.as_view(), name='global-user-create'),
    path('global/users/list/', GlobalUserListView.as_view(), name='global-user-list'),
    path('global/users/<int:pk>/', GlobalUserDetailView.as_view(), name='global-user-detail'),
    path('global/users/<int:pk>/update/', GlobalUserUpdateView.as_view(), name='global-user-update'),
    path('global/users/<int:pk>/delete/', GlobalUserDeleteView.as_view(), name='global-user-delete'),
    
    # Country
    path('countries/<int:country_id>/users/create/', CountryUserCreateView.as_view(), name='country-user-create'),
    path('countries/<int:country_id>/users/list/', CountryUserListView.as_view(), name='country-user-list'),
    path('countries/<int:country_id>/users/<int:pk>/', CountryUserDetailView.as_view(), name='country-user-detail'),
    
    # Territorial
    path('territorial/users/create/', TerritorialUserCreateView.as_view(), name='territorial-user-create'),
    path('territorial/users/list/', TerritorialUserListView.as_view(), name='territorial-user-list'),
    path('territorial/users/<int:pk>/', TerritorialUserDetailView.as_view(), name='territorial-user-detail'),
]
```

#### Module File Handling
```python
# Vues
class GlobalFileListView(APIView):
class GlobalFileDetailView(APIView):
class GlobalFileDeleteView(APIView):
class GlobalFileDownloadView(APIView):
class GlobalFilePreviewView(APIView):

class CountryFileListView(APIView):
class CountryFileDetailView(APIView):
class CountryFileDeleteView(APIView):
class CountryFileDownloadView(APIView):
class CountryFilePreviewView(APIView):

class GlobalImportSessionListView(APIView):
class GlobalImportSessionDetailView(APIView):
class GlobalImportSessionDownloadView(APIView):

class CountryImportSessionListView(APIView):
class CountryImportSessionDetailView(APIView):
class CountryImportSessionDownloadView(APIView):

# URLs
urlpatterns = [
    # Global Files
    path('global/files/list/', GlobalFileListView.as_view(), name='global-file-list'),
    path('global/files/<int:pk>/', GlobalFileDetailView.as_view(), name='global-file-detail'),
    path('global/files/<int:pk>/delete/', GlobalFileDeleteView.as_view(), name='global-file-delete'),
    path('global/files/<int:pk>/download/', GlobalFileDownloadView.as_view(), name='global-file-download'),
    path('global/files/<int:pk>/preview/', GlobalFilePreviewView.as_view(), name='global-file-preview'),
    
    # Country Files
    path('countries/<int:country_id>/files/list/', CountryFileListView.as_view(), name='country-file-list'),
    path('countries/<int:country_id>/files/<int:pk>/', CountryFileDetailView.as_view(), name='country-file-detail'),
    
    # Global Import Sessions
    path('global/import-sessions/list/', GlobalImportSessionListView.as_view(), name='global-import-session-list'),
    path('global/import-sessions/<int:pk>/', GlobalImportSessionDetailView.as_view(), name='global-import-session-detail'),
    path('global/import-sessions/<int:pk>/download/', GlobalImportSessionDownloadView.as_view(), name='global-import-session-download'),
    
    # Country Import Sessions
    path('countries/<int:country_id>/import-sessions/list/', CountryImportSessionListView.as_view(), name='country-import-session-list'),
    path('countries/<int:country_id>/import-sessions/<int:pk>/', CountryImportSessionDetailView.as_view(), name='country-import-session-detail'),
]
```

#### Module Importer
```python
# Vues
class GlobalFileUploadAndImportView(APIView):
class CountryFileUploadAndImportView(APIView):
class TerritorialFileUploadAndImportView(APIView):

# URLs
urlpatterns = [
    path('global/upload-and-import/', GlobalFileUploadAndImportView.as_view(), name='global-upload-and-import'),
    path('countries/<int:country_id>/upload-and-import/', CountryFileUploadAndImportView.as_view(), name='country-upload-and-import'),
    path('territorial/upload-and-import/', TerritorialFileUploadAndImportView.as_view(), name='territorial-upload-and-import'),
]
```

### Option 2 : Nomenclature Simplifiée

#### Module Users
```python
# Vues
class UserCreateView(APIView):
class UserListView(APIView):
class UserDetailView(APIView):
class UserUpdateView(APIView):
class UserDeleteView(APIView):

# URLs
urlpatterns = [
    path('users/create/', UserCreateView.as_view(), name='user-create'),
    path('users/list/', UserListView.as_view(), name='user-list'),
    path('users/<int:pk>/', UserDetailView.as_view(), name='user-detail'),
    path('users/<int:pk>/update/', UserUpdateView.as_view(), name='user-update'),
    path('users/<int:pk>/delete/', UserDeleteView.as_view(), name='user-delete'),
]
```

#### Module File Handling
```python
# Vues
class FileListView(APIView):
class FileDetailView(APIView):
class FileDeleteView(APIView):
class FileDownloadView(APIView):
class FilePreviewView(APIView):

class ImportSessionListView(APIView):
class ImportSessionDetailView(APIView):
class ImportSessionDownloadView(APIView):

# URLs
urlpatterns = [
    path('files/list/', FileListView.as_view(), name='file-list'),
    path('files/<int:pk>/', FileDetailView.as_view(), name='file-detail'),
    path('files/<int:pk>/delete/', FileDeleteView.as_view(), name='file-delete'),
    path('files/<int:pk>/download/', FileDownloadView.as_view(), name='file-download'),
    path('files/<int:pk>/preview/', FilePreviewView.as_view(), name='file-preview'),
    
    path('import-sessions/list/', ImportSessionListView.as_view(), name='import-session-list'),
    path('import-sessions/<int:pk>/', ImportSessionDetailView.as_view(), name='import-session-detail'),
    path('import-sessions/<int:pk>/download/', ImportSessionDownloadView.as_view(), name='import-session-download'),
]
```

### Option 3 : Nomenclature Hybride (Recommandée pour la Transition)

#### Module Users
```python
# Vues (garder les noms actuels mais uniformiser les URLs)
class SuperuserCreateAPIView(APIView):
class GlobalAdminListView(APIView):
class TerritorialAdminListView(APIView):
class SimpleUserListView(APIView):

# URLs (uniformiser selon les principes)
urlpatterns = [
    # Global
    path('global/superusers/create/', SuperuserCreateAPIView.as_view(), name='global-superuser-create'),
    path('global/admins/list/', GlobalAdminListView.as_view(), name='global-admin-list'),
    path('global/admins/<int:pk>/', GlobalAdminDetailView.as_view(), name='global-admin-detail'),
    
    # Territorial
    path('territorial/admins/list/', TerritorialAdminListView.as_view(), name='territorial-admin-list'),
    path('territorial/admins/<int:pk>/', TerritorialAdminDetailView.as_view(), name='territorial-admin-detail'),
    
    # Country (pour les utilisateurs simples)
    path('countries/<int:country_id>/users/list/', SimpleUserListView.as_view(), name='country-user-list'),
    path('countries/<int:country_id>/users/<int:pk>/', SimpleUserDetailView.as_view(), name='country-user-detail'),
]
```

## 📊 Matrice de Décision

| Critère | Option 1 (Complète) | Option 2 (Simplifiée) | Option 3 (Hybride) |
|---------|---------------------|----------------------|-------------------|
| **Cohérence** | ⭐⭐⭐⭐⭐ | ⭐⭐⭐ | ⭐⭐⭐⭐ |
| **Effort de Migration** | ⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐ |
| **Lisibilité** | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐ | ⭐⭐⭐⭐ |
| **Maintenabilité** | ⭐⭐⭐⭐⭐ | ⭐⭐⭐ | ⭐⭐⭐⭐ |
| **Évolutivité** | ⭐⭐⭐⭐⭐ | ⭐⭐⭐ | ⭐⭐⭐⭐ |

## 🚀 Plan de Migration Recommandé

### Phase 1 : Standardisation des URLs (Immédiat)
1. **Uniformiser les patterns d'URL** selon les principes
2. **Garder les noms de vues actuels** pour éviter les breaking changes
3. **Mettre à jour la documentation** avec les nouvelles URLs

### Phase 2 : Standardisation des Vues (Court terme)
1. **Renommer progressivement les vues** selon la nomenclature
2. **Mettre à jour les imports** dans les fichiers
3. **Tester chaque changement** pour éviter les régressions

### Phase 3 : Standardisation des Services (Moyen terme)
1. **Renommer les services** selon la nomenclature
2. **Mettre à jour les références** dans les vues
3. **Standardiser les noms de fichiers** des services

## 📝 Checklist de Migration

### URLs
- [ ] Préfixer les URLs globales avec `global/`
- [ ] Préfixer les URLs par pays avec `countries/<id>/`
- [ ] Préfixer les URLs territoriales avec `territorial/`
- [ ] Uniformiser les suffixes (`/list/`, `/detail/`, `/create/`, etc.)

### Vues
- [ ] Préfixer les vues globales avec `Global`
- [ ] Préfixer les vues par pays avec `Country`
- [ ] Préfixer les vues territoriales avec `Territorial`
- [ ] Suffixer avec `Statistics`, `List`, `Detail`, etc.

### Services
- [ ] Appliquer la même nomenclature aux services
- [ ] Renommer les fichiers de services
- [ ] Mettre à jour les imports

### Documentation
- [ ] Mettre à jour la documentation des APIs
- [ ] Mettre à jour les exemples de code
- [ ] Mettre à jour les guides d'intégration

## 🎯 Recommandation Finale

**Option 3 (Hybride)** est recommandée car elle :
- ✅ Respecte vos principes de nomenclature
- ✅ Minimise l'effort de migration
- ✅ Maintient la cohérence
- ✅ Permet une transition progressive
- ✅ Évite les breaking changes majeurs

Cette approche permet d'uniformiser progressivement tout le projet tout en maintenant la stabilité du système.

---

**Guide Version**: 1.0  
**Last Updated**: December 2024  
**Status**: Complete ✅
