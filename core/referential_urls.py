from django.urls import path

from . import referential_views as v

urlpatterns = [
    path('categories/', v.CategoryListView.as_view(), name='referential-categories'),
    path('acts/', v.ActListView.as_view(), name='referential-acts'),
    path('acts/merge/', v.ActMergeView.as_view(), name='referential-acts-merge'),
    path('acts/<int:pk>/', v.ActDetailView.as_view(), name='referential-act'),
    path('acts/<int:pk>/aliases/', v.AliasCreateView.as_view(), name='referential-alias-create'),
    path('aliases/<int:pk>/', v.AliasDeleteView.as_view(), name='referential-alias-delete'),
]
