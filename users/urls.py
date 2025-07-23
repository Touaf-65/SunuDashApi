from django.urls import path
from .views import ( SuperuserCreateAPIView, LoginUserAPIView, GetConnectedUserByLogin, VerifyPassword, CreateGlobalAdminView, PasswordResetRequestView, PasswordResetConfirmView, CreateAdminGlobalFromFileView, 
    GlobalAdminListView, GlobalAdminDetailView, GlobalAdminUpdateView, GlobalAdminDeleteView, CreateTerritorialAdminView, CreateTerritorialAdminsFromExcel, TerritorialAdminListView,
    TerritorialAdminDetailView, TerritorialAdminUpdateView, TerritorialAdminDeleteView, AssignCountryToTerritorialAdminView, UnassignOrReassignCountryView,
    CreateUserByTerritorialAdmin, CreateUsersByTerritorialAdminFromExcel, SimpleUserListView, SimpleUserDetailView, SimpleUserUpdateView, SimpleUserDeleteView, ToggleUserActiveView )

urlpatterns = [
    path('create_superuser/', SuperuserCreateAPIView.as_view(), name='create_superuser'),

    path('login/', LoginUserAPIView.as_view(), name='login_user'),
    path('getConnectedUser/<str:login>/', GetConnectedUserByLogin.as_view(), name='get_connected_user_by_login'),
    path('verify_password/', VerifyPassword.as_view(), name='verify_password'),

    path('password_reset/', PasswordResetRequestView.as_view(), name='password_reset_request'),
    path('password_reset_confirm/', PasswordResetConfirmView.as_view(), name='password_reset_confirm'),

    path('global_admins/create/', CreateGlobalAdminView.as_view(), name='register_globalal_admin'),
    path('global_admins/import_create/', CreateAdminGlobalFromFileView.as_view(), name='import_globalal_admins'),
    path('global_admins/list/', GlobalAdminListView.as_view(), name='register_globalal_admin'),
    path('global_admins/<int:pk>/', GlobalAdminDetailView.as_view(), name='global_admin_detail'),
    path('global_admins/<int:pk>/update/', GlobalAdminUpdateView.as_view(), name='global_admin_update'),
    path('global_admins/<int:pk>/delete/', GlobalAdminDeleteView.as_view(), name='global_admin_delete'),
    
    path('territorial_admins/create/', CreateTerritorialAdminView.as_view(), name='register_territorial_admin'),
    path('territorial_admins/import_create/', CreateTerritorialAdminsFromExcel.as_view(), name='import_territorial_admins'),
    path('territorial_admins/list/', TerritorialAdminListView.as_view(), name='list_countries'),
    path('territorial_admins/<int:pk>/', TerritorialAdminDetailView.as_view(), name='country_detail'),
    path('territorial_admins/<int:pk>/update/', TerritorialAdminUpdateView.as_view(), name='country_detail'),
    path('territorial_admins/<int:pk>/delete/', TerritorialAdminDeleteView.as_view(), name='country_detail'),

    path('territorial_admins/assign/', AssignCountryToTerritorialAdminView.as_view(), name='assign_admin'),  
    path('territorial_admins/change_assign/', UnassignOrReassignCountryView.as_view(), name='assign_admin'),  

    path('territorial_admins/users/create_user/', CreateUserByTerritorialAdmin.as_view(), name='create_user_by_territorial_admin'),
    path('territorial_admins/users/import_create_user/', CreateUsersByTerritorialAdminFromExcel.as_view(), name='import_users_by_territorial_admin'),
    path('territorial_admins/users/list/', SimpleUserListView.as_view(), name='list_countries'),
    path('territorial_admins/users/<int:pk>/', SimpleUserDetailView.as_view(), name='country_detail'),
    path('territorial_admins/users/<int:pk>/update/', SimpleUserUpdateView.as_view(), name='country_detail'),
    path('territorial_admins/users/<int:pk>/delete/', SimpleUserDeleteView.as_view(), name='country_detail'),

    path('users/<int:pk>/toggle-active/', ToggleUserActiveView.as_view(), name='toggle-user-active'),
]