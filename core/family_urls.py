from django.urls import path

from . import family_views as v

urlpatterns = [
    path('', v.FamilyListView.as_view(), name='family-list'),
    path('filters/', v.FamilyFiltersView.as_view(), name='family-filters'),
    path('insureds/', v.InsuredSearchView.as_view(), name='family-insured-search'),
    path('insureds/merge/', v.MergeInsuredsView.as_view(), name='family-insured-merge'),
    path('insureds/<int:insured_id>/name/', v.RenameInsuredView.as_view(), name='family-insured-rename'),
    path('<int:policy_id>/principals/', v.PolicyPrincipalsView.as_view(), name='family-policy-principals'),
    path('<int:policy_id>/members/<int:insured_id>/attach/', v.AttachMemberView.as_view(), name='family-attach'),
    path('<int:policy_id>/members/<int:insured_id>/role/', v.ChangeRoleView.as_view(), name='family-role'),
    path('<int:policy_id>/<int:principal_id>/', v.FamilyDetailView.as_view(), name='family-detail'),
    path('<int:policy_id>/<int:principal_id>/claims/', v.FamilyClaimsView.as_view(), name='family-claims'),
]
