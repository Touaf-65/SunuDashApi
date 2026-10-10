from django.urls import path

from . import premium_views as pv
from . import settings_views as v

urlpatterns = [
    path('policies/', v.PolicySettingsListView.as_view(), name='settings-policies'),
    path('policies/<int:pk>/', v.PolicySettingsDetailView.as_view(), name='settings-policy'),
    path('subscribers/', v.SubscriberListView.as_view(), name='settings-subscribers'),
    path('premiums/', pv.PremiumListView.as_view(), name='settings-premiums'),
    path('premiums/import/', pv.PremiumImportView.as_view(), name='settings-premiums-import'),
    path('premiums/template/', pv.PremiumTemplateView.as_view(), name='settings-premiums-template'),
    path('premiums/sp/', pv.PremiumSPView.as_view(), name='settings-premiums-sp'),
    path('premiums/history/<int:client_id>/', pv.PremiumHistoryView.as_view(), name='settings-premiums-history'),
    path('premiums/<int:pk>/', pv.PremiumDetailView.as_view(), name='settings-premium'),
]
