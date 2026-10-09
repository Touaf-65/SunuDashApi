"""
Routes des familles (lot F1) : uniquement l'admin territorial et le chef de département technique, sur les familles
de **leur pays** (hors de ce périmètre : 404). Chaque correction exige le mot de passe de l'utilisateur connecté,
vérifié ici, et est tracée (FamilyChange).
"""
from django.http import Http404
from rest_framework import status
from rest_framework.permissions import BasePermission, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from users.models import CustomUser as User
from .services import family_service as fs

INVALID_PASSWORD_MESSAGE = "Mot de passe incorrect : aucune modification n'a été faite."


class CanManageFamilies(BasePermission):
    message = "Seuls l'admin territorial et le chef de département technique d'un pays ont accès à ses familles."

    def has_permission(self, request, view):
        user = request.user
        return bool(user and user.is_authenticated
                    and user.role in (User.Roles.ADMIN_TERRITORIAL, User.Roles.CHEF_DEPT_TECH)
                    and user.country_id is not None)


FAMILY_PERMISSIONS = [IsAuthenticated, CanManageFamilies]


def _bad_request(message):
    return Response({'error': message}, status=status.HTTP_400_BAD_REQUEST)


def _int(value, default=None):
    try:
        return int(value) if value not in (None, '') else default
    except (TypeError, ValueError):
        return default


def _period(request):
    return fs.parse_period(request.query_params.get('start'), request.query_params.get('end'))


class FamilyFiltersView(APIView):
    permission_classes = FAMILY_PERMISSIONS

    def get(self, request):
        return Response(fs.filter_options(request.user.country))


class FamilyListView(APIView):
    permission_classes = FAMILY_PERMISSIONS

    def get(self, request):
        q = request.query_params
        try:
            start, end = _period(request)
        except ValueError as exc:
            return _bad_request(str(exc))
        return Response(fs.list_families(
            request.user.country, search=q.get('search', '').strip(), policy_id=_int(q.get('policy')),
            employer_id=_int(q.get('employer')), start=start, end=end, ordering=q.get('ordering', 'name'),
            page=_int(q.get('page'), 1), page_size=_int(q.get('page_size'), 25)))


class FamilyDetailView(APIView):
    permission_classes = FAMILY_PERMISSIONS

    def get(self, request, policy_id, principal_id):
        try:
            start, end = _period(request)
        except ValueError as exc:
            return _bad_request(str(exc))
        data = fs.family_detail(request.user.country, policy_id, principal_id, start, end)
        if data is None:
            raise Http404("Famille introuvable.")
        return Response(data)


class FamilyClaimsView(APIView):
    permission_classes = FAMILY_PERMISSIONS

    def get(self, request, policy_id, principal_id):
        country = request.user.country
        if not fs.family_exists(country, policy_id, principal_id):
            raise Http404("Famille introuvable.")
        q = request.query_params
        try:
            start, end = _period(request)
        except ValueError as exc:
            return _bad_request(str(exc))
        return Response(fs.family_claims(country, policy_id, principal_id, start, end,
                                         member_id=_int(q.get('member')), page=_int(q.get('page'), 1),
                                         page_size=_int(q.get('page_size'), 20)))


class PolicyPrincipalsView(APIView):
    """Principaux d'une police : cibles possibles d'un rattachement."""
    permission_classes = FAMILY_PERMISSIONS

    def get(self, request, policy_id):
        q = request.query_params
        return Response(fs.principal_choices(request.user.country, policy_id, q.get('search', '').strip(),
                                             exclude=_int(q.get('exclude'))))


class InsuredSearchView(APIView):
    """Assurés du pays : candidats à une fusion."""
    permission_classes = FAMILY_PERMISSIONS

    def get(self, request):
        q = request.query_params
        return Response(fs.insured_choices(request.user.country, q.get('search', '').strip(),
                                           exclude=_int(q.get('exclude'))))


class _CorrectionView(APIView):
    """Correction : mot de passe vérifié avant toute modification ; refus métier -> 400 avec le motif."""
    permission_classes = FAMILY_PERMISSIONS

    def post(self, request, **kwargs):
        if not request.user.check_password(request.data.get('password') or ''):
            return Response({'error': INVALID_PASSWORD_MESSAGE, 'code': 'invalid_password'},
                            status=status.HTTP_403_FORBIDDEN)
        try:
            return Response(self.apply(request, request.user.country, request.data, **kwargs))
        except fs.FamilyError as exc:
            return _bad_request(str(exc))

    def apply(self, request, country, data, **kwargs):
        raise NotImplementedError


class AttachMemberView(_CorrectionView):
    def apply(self, request, country, data, policy_id, insured_id):
        principal_id = _int(data.get('principal_id'))
        if not principal_id:
            raise fs.FamilyError("Choisissez l'assuré principal de rattachement.")
        return fs.attach_member(country, request.user, policy_id, insured_id, principal_id)


class ChangeRoleView(_CorrectionView):
    def apply(self, request, country, data, policy_id, insured_id):
        return fs.change_role(country, request.user, policy_id, insured_id, data.get('role'),
                              _int(data.get('principal_id')))


class MergeInsuredsView(_CorrectionView):
    def apply(self, request, country, data):
        keep_id, absorb_id = _int(data.get('keep_id')), _int(data.get('absorb_id'))
        if not keep_id or not absorb_id:
            raise fs.FamilyError("Choisissez la fiche à conserver et la fiche à fusionner.")
        return fs.merge_insureds(country, request.user, keep_id, absorb_id)


class RenameInsuredView(_CorrectionView):
    def apply(self, request, country, data, insured_id):
        return fs.rename_insured(country, request.user, insured_id, data.get('name'))
