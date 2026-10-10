"""
Référentiel des actes, commun à tous les pays (lot I4, décisions N1 / N2 du 10/10/2026) :
modification par l'admin global ; consultation aussi par l'admin territorial et le chef de département technique.
"""
from django.http import Http404
from rest_framework import status
from rest_framework.permissions import BasePermission, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from users.models import CustomUser as User
from .services import act_referential_service as ars

EDIT_ROLES = (User.Roles.ADMIN_GLOBAL,)
READ_ROLES = (User.Roles.ADMIN_GLOBAL, User.Roles.ADMIN_TERRITORIAL, User.Roles.CHEF_DEPT_TECH)


class ReferentialAccess(BasePermission):
    message = "Le référentiel des actes est géré par l'admin global."

    def has_permission(self, request, view):
        user = request.user
        if not (user and user.is_authenticated):
            return False
        if request.method in ('GET', 'HEAD', 'OPTIONS'):
            return user.role in READ_ROLES
        return user.role in EDIT_ROLES


PERMISSIONS = [IsAuthenticated, ReferentialAccess]


def _int(value, default=None):
    try:
        return int(value) if value not in (None, '') else default
    except (TypeError, ValueError):
        return default


def _run(fn, *args):
    try:
        return Response(fn(*args))
    except ars.ReferentialError as exc:
        return Response({'error': str(exc)}, status=status.HTTP_400_BAD_REQUEST)


class CategoryListView(APIView):
    permission_classes = PERMISSIONS

    def get(self, request):
        return Response(ars.categories())


class ActListView(APIView):
    permission_classes = PERMISSIONS

    def get(self, request):
        q = request.query_params
        data = ars.list_acts(q.get('search', '').strip(), _int(q.get('category')), q.get('unused') in ('1', 'true'),
                             _int(q.get('page'), 1), _int(q.get('page_size'), 50))
        data['can_edit'] = request.user.role in EDIT_ROLES
        return Response(data)


class ActDetailView(APIView):
    permission_classes = PERMISSIONS

    def get(self, request, pk):
        data = ars.act_detail(pk)
        if data is None:
            raise Http404("Acte introuvable.")
        data['can_edit'] = request.user.role in EDIT_ROLES
        return Response(data)

    def patch(self, request, pk):
        return _run(ars.update_act, request.user, pk, request.data)


class ActMergeView(APIView):
    permission_classes = PERMISSIONS

    def post(self, request):
        return _run(ars.merge_acts, request.user, _int(request.data.get('keep_id')), request.data.get('absorb_ids') or [])


class AliasCreateView(APIView):
    permission_classes = PERMISSIONS

    def post(self, request, pk):
        return _run(ars.create_alias, request.user, pk, request.data.get('label'))


class AliasDeleteView(APIView):
    permission_classes = PERMISSIONS

    def delete(self, request, pk):
        return _run(ars.delete_alias, request.user, pk)
