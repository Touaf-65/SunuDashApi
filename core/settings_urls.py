from django.urls import path

from . import settings_views as v

urlpatterns = [
    path('policies/', v.PolicySettingsListView.as_view(), name='settings-policies'),
    path('policies/<int:pk>/', v.PolicySettingsDetailView.as_view(), name='settings-policy'),
    path('subscribers/', v.SubscriberListView.as_view(), name='settings-subscribers'),
]
