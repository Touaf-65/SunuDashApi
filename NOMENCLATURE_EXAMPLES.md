# Exemples d'Application de la Nomenclature - Sunu Dash API

## 📋 Exemples Concrets par Module

### Module Users - Application de la Nomenclature

#### État Actuel vs État Proposé

**État Actuel (Non Uniforme)**
```python
# Vues actuelles
class SuperuserCreateAPIView(APIView):
class LoginUserAPIView(APIView):
class GlobalAdminListView(APIView):
class TerritorialAdminListView(APIView):
class SimpleUserListView(APIView):

# URLs actuelles
urlpatterns = [
    path('create_superuser/', SuperuserCreateAPIView.as_view(), name='create_superuser'),
    path('login/', LoginUserAPIView.as_view(), name='login_user'),
    path('global_admins/list/', GlobalAdminListView.as_view(), name='register_globalal_admin'),
    path('territorial_admins/list/', TerritorialAdminListView.as_view(), name='list_countries'),
    path('territorial_admins/users/list/', SimpleUserListView.as_view(), name='list_countries'),
]
```

**État Proposé (Uniforme)**
```python
# Vues uniformisées
class GlobalSuperuserCreateView(APIView):
class GlobalUserLoginView(APIView):
class GlobalAdminListView(APIView):
class GlobalAdminDetailView(APIView):
class GlobalAdminUpdateView(APIView):
class GlobalAdminDeleteView(APIView):

class TerritorialAdminListView(APIView):
class TerritorialAdminDetailView(APIView):
class TerritorialAdminUpdateView(APIView):
class TerritorialAdminDeleteView(APIView):

class CountryUserListView(APIView):
class CountryUserDetailView(APIView):
class CountryUserUpdateView(APIView):
class CountryUserDeleteView(APIView):

# URLs uniformisées
urlpatterns = [
    # Global
    path('global/superusers/create/', GlobalSuperuserCreateView.as_view(), name='global-superuser-create'),
    path('global/users/login/', GlobalUserLoginView.as_view(), name='global-user-login'),
    path('global/admins/list/', GlobalAdminListView.as_view(), name='global-admin-list'),
    path('global/admins/<int:pk>/', GlobalAdminDetailView.as_view(), name='global-admin-detail'),
    path('global/admins/<int:pk>/update/', GlobalAdminUpdateView.as_view(), name='global-admin-update'),
    path('global/admins/<int:pk>/delete/', GlobalAdminDeleteView.as_view(), name='global-admin-delete'),
    
    # Territorial
    path('territorial/admins/list/', TerritorialAdminListView.as_view(), name='territorial-admin-list'),
    path('territorial/admins/<int:pk>/', TerritorialAdminDetailView.as_view(), name='territorial-admin-detail'),
    path('territorial/admins/<int:pk>/update/', TerritorialAdminUpdateView.as_view(), name='territorial-admin-update'),
    path('territorial/admins/<int:pk>/delete/', TerritorialAdminDeleteView.as_view(), name='territorial-admin-delete'),
    
    # Country
    path('countries/<int:country_id>/users/list/', CountryUserListView.as_view(), name='country-user-list'),
    path('countries/<int:country_id>/users/<int:pk>/', CountryUserDetailView.as_view(), name='country-user-detail'),
    path('countries/<int:country_id>/users/<int:pk>/update/', CountryUserUpdateView.as_view(), name='country-user-update'),
    path('countries/<int:country_id>/users/<int:pk>/delete/', CountryUserDeleteView.as_view(), name='country-user-delete'),
]
```

### Module File Handling - Application de la Nomenclature

#### État Actuel vs État Proposé

**État Actuel (Non Uniforme)**
```python
# Vues actuelles
class FileListView(APIView):
class FileDeleteView(APIView):
class FileDownloadView(APIView):
class FilePreviewView(APIView):
class ImportSessionListView(APIView):
class ImportSessionDownloadView(APIView):

# URLs actuelles
urlpatterns = [
    path('', FileListView.as_view(), name='file-list'),
    path('<int:pk>/delete/', FileDeleteView.as_view(), name='file-delete'),
    path('<int:pk>/download/', FileDownloadView.as_view(), name='file-download'),
    path('<int:pk>/preview/', FilePreviewView.as_view(), name='file-preview'),
    path('', ImportSessionListView.as_view(), name='import-session-list'),
    path('<int:pk>/download/', ImportSessionDownloadView.as_view(), name='import-session-download'),
]
```

**État Proposé (Uniforme)**
```python
# Vues uniformisées
class CountryFileListView(APIView):
class CountryFileDetailView(APIView):
class CountryFileDeleteView(APIView):
class CountryFileDownloadView(APIView):
class CountryFilePreviewView(APIView):

class CountryImportSessionListView(APIView):
class CountryImportSessionDetailView(APIView):
class CountryImportSessionDownloadView(APIView):

# URLs uniformisées
urlpatterns = [
    # Country Files
    path('countries/<int:country_id>/files/list/', CountryFileListView.as_view(), name='country-file-list'),
    path('countries/<int:country_id>/files/<int:pk>/', CountryFileDetailView.as_view(), name='country-file-detail'),
    path('countries/<int:country_id>/files/<int:pk>/delete/', CountryFileDeleteView.as_view(), name='country-file-delete'),
    path('countries/<int:country_id>/files/<int:pk>/download/', CountryFileDownloadView.as_view(), name='country-file-download'),
    path('countries/<int:country_id>/files/<int:pk>/preview/', CountryFilePreviewView.as_view(), name='country-file-preview'),
    
    # Country Import Sessions
    path('countries/<int:country_id>/import-sessions/list/', CountryImportSessionListView.as_view(), name='country-import-session-list'),
    path('countries/<int:country_id>/import-sessions/<int:pk>/', CountryImportSessionDetailView.as_view(), name='country-import-session-detail'),
    path('countries/<int:country_id>/import-sessions/<int:pk>/download/', CountryImportSessionDownloadView.as_view(), name='country-import-session-download'),
]
```

### Module Importer - Application de la Nomenclature

#### État Actuel vs État Proposé

**État Actuel (Non Uniforme)**
```python
# Vues actuelles
class FileUploadAndImportView(APIView):

# URLs actuelles
urlpatterns = [
    path('upload/', FileUploadAndImportView.as_view(), name='file-upload-import'),
]
```

**État Proposé (Uniforme)**
```python
# Vues uniformisées
class CountryFileUploadAndImportView(APIView):
class TerritorialFileUploadAndImportView(APIView):

# URLs uniformisées
urlpatterns = [
    # Country
    path('countries/<int:country_id>/upload-and-import/', CountryFileUploadAndImportView.as_view(), name='country-upload-and-import'),
    
    # Territorial
    path('territorial/upload-and-import/', TerritorialFileUploadAndImportView.as_view(), name='territorial-upload-and-import'),
]
```

## 🔄 Plan de Migration Détaillé

### Phase 1 : URLs (Semaine 1)

#### Module Users
```python
# Avant
path('create_superuser/', SuperuserCreateAPIView.as_view(), name='create_superuser'),
path('global_admins/list/', GlobalAdminListView.as_view(), name='register_globalal_admin'),
path('territorial_admins/list/', TerritorialAdminListView.as_view(), name='list_countries'),

# Après
path('global/superusers/create/', SuperuserCreateAPIView.as_view(), name='global-superuser-create'),
path('global/admins/list/', GlobalAdminListView.as_view(), name='global-admin-list'),
path('territorial/admins/list/', TerritorialAdminListView.as_view(), name='territorial-admin-list'),
```

#### Module File Handling
```python
# Avant
path('', FileListView.as_view(), name='file-list'),
path('<int:pk>/delete/', FileDeleteView.as_view(), name='file-delete'),

# Après
path('countries/<int:country_id>/files/list/', FileListView.as_view(), name='country-file-list'),
path('countries/<int:country_id>/files/<int:pk>/delete/', FileDeleteView.as_view(), name='country-file-delete'),
```

### Phase 2 : Vues (Semaine 2-3)

#### Module Users
```python
# Avant
class SuperuserCreateAPIView(APIView):
class GlobalAdminListView(APIView):
class TerritorialAdminListView(APIView):

# Après
class GlobalSuperuserCreateView(APIView):
class GlobalAdminListView(APIView):  # Déjà conforme
class TerritorialAdminListView(APIView):  # Déjà conforme
```

#### Module File Handling
```python
# Avant
class FileListView(APIView):
class FileDeleteView(APIView):

# Après
class CountryFileListView(APIView):
class CountryFileDeleteView(APIView):
```

### Phase 3 : Services (Semaine 4)

#### Module Dashboard (Déjà conforme)
```python
# Services existants (déjà conformes)
- GlobalStatistics
- CountryStatistics
- GlobalClientStatistics
- CountryClientStatistics
```

#### Module Users (À créer)
```python
# Nouveaux services
class GlobalUserStatistics:
class CountryUserStatistics:
class TerritorialUserStatistics:
```

## 📊 Impact de la Migration

### Avantages
1. **Cohérence** : Tous les modules suivent la même nomenclature
2. **Lisibilité** : Les noms sont plus explicites et descriptifs
3. **Maintenabilité** : Plus facile de comprendre et maintenir le code
4. **Évolutivité** : Structure claire pour ajouter de nouvelles fonctionnalités

### Risques et Mitigations
1. **Breaking Changes** : Migration progressive pour éviter les interruptions
2. **Documentation** : Mise à jour simultanée de la documentation
3. **Tests** : Tests complets après chaque phase de migration

## 🎯 Exemples de Noms Uniformisés

### Services
```
GlobalClientStatistics
CountryClientStatistics
TerritorialClientStatistics

GlobalPartnerList
CountryPartnerList
TerritorialPartnerList

GlobalUserCreate
CountryUserCreate
TerritorialUserCreate
```

### Vues
```
GlobalClientStatisticsView
CountryClientStatisticsView
TerritorialClientStatisticsView

GlobalPartnerListView
CountryPartnerListView
TerritorialPartnerListView

GlobalUserCreateView
CountryUserCreateView
TerritorialUserCreateView
```

### URLs
```
/global/clients/statistics/
/countries/<id>/clients/statistics/
/territorial/clients/statistics/

/global/partners/list/
/countries/<id>/partners/list/
/territorial/partners/list/

/global/users/create/
/countries/<id>/users/create/
/territorial/users/create/
```

## 📝 Checklist de Validation

### Avant la Migration
- [ ] Sauvegarder le code actuel
- [ ] Créer des tests pour valider le comportement actuel
- [ ] Documenter les changements prévus

### Pendant la Migration
- [ ] Tester chaque changement individuellement
- [ ] Valider que les URLs fonctionnent correctement
- [ ] Vérifier que les imports sont corrects
- [ ] Mettre à jour la documentation

### Après la Migration
- [ ] Tests complets de régression
- [ ] Validation des performances
- [ ] Mise à jour de la documentation utilisateur
- [ ] Formation de l'équipe sur la nouvelle nomenclature

---

**Exemples Version**: 1.0  
**Last Updated**: December 2024  
**Status**: Complete ✅
