"""
Paramétrage des référentiels d'un pays (lot I4) : polices (taux de couverture, souscripteur).
Lecture : admin territorial et chef de département technique du pays ; modification : admin territorial seulement
(décision I). Hors du pays : 404.
"""
from django.http import Http404
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from users.models import CustomUser as User
from .family_views import CanManageFamilies
from .services import policy_settings_service as ps

READ_PERMISSIONS = [IsAuthenticated, CanManageFamilies]
EDIT_FORBIDDEN = "Seul l'admin territorial peut modifier le paramétrage des polices."


class PolicySettingsListView(APIView):
    permission_classes = READ_PERMISSIONS

    def get(self, request):
        q = request.query_params
        data = ps.list_policies(request.user.country, q.get('search', '').strip(),
                                to_complete=q.get('to_complete') in ('1', 'true'))
        data['can_edit'] = request.user.role == User.Roles.ADMIN_TERRITORIAL
        return Response(data)


class PolicySettingsDetailView(APIView):
    permission_classes = READ_PERMISSIONS

    def get(self, request, pk):
        data = ps.policy_detail(request.user.country, pk)
        if data is None:
            raise Http404("Police introuvable.")
        data['can_edit'] = request.user.role == User.Roles.ADMIN_TERRITORIAL
        return Response(data)

    def patch(self, request, pk):
        if request.user.role != User.Roles.ADMIN_TERRITORIAL:
            return Response({'error': EDIT_FORBIDDEN}, status=status.HTTP_403_FORBIDDEN)
        if ps.policy_detail(request.user.country, pk) is None:
            raise Http404("Police introuvable.")
        try:
            return Response(ps.update_policy(request.user.country, request.user, pk, request.data))
        except ps.SettingsError as exc:
            return Response({'error': str(exc)}, status=status.HTTP_400_BAD_REQUEST)


class SubscriberListView(APIView):
    permission_classes = READ_PERMISSIONS

    def get(self, request):
        return Response(ps.list_subscribers(request.user.country, request.query_params.get('search', '').strip()))
