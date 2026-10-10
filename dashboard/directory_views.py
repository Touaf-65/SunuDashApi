"""
Listes et fiches des assurés, prestataires et opérateurs de saisie (lot D4). Toutes en GET, période en paramètres
d'URL (`?date_start=AAAA-MM-JJ&date_end=AAAA-MM-JJ`), pagination `?page=&page_size=`.
Accès : dashboard.access.StatisticsAccess (le pays de l'URL ou de l'objet est contrôlé) ; les vues des opérateurs
sont aussi ouvertes au responsable opérateur de leur pays.
"""
import logging

from django.core.exceptions import ObjectDoesNotExist
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from .access import StatisticsAccess
from .services import directory_service as ds

logger = logging.getLogger(__name__)


class _DirectoryView(APIView):
    permission_classes = [StatisticsAccess]
    handler = None          # fonction de directory_service : handler(identifiant, params)
    url_kwarg = None        # paramètre d'URL passé à la fonction

    def get(self, request, **kwargs):
        try:
            data = type(self).handler(kwargs[self.url_kwarg], request.query_params)
        except ds.DirectoryError as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)
        except ObjectDoesNotExist:
            return Response({"error": "Introuvable."}, status=status.HTTP_404_NOT_FOUND)
        return Response(data, status=status.HTTP_200_OK)


class InsuredDirectoryView(_DirectoryView):
    handler, url_kwarg = ds.insured_directory, 'country_id'


class InsuredSheetView(_DirectoryView):
    handler, url_kwarg = ds.insured_sheet, 'insured_id'


class InsuredClaimsView(_DirectoryView):
    handler, url_kwarg = ds.insured_claims, 'insured_id'


class PartnerDirectoryView(_DirectoryView):
    handler, url_kwarg = ds.partner_directory, 'country_id'


class PartnerSheetView(_DirectoryView):
    handler, url_kwarg = ds.partner_sheet, 'partner_id'


class PartnerClaimsView(_DirectoryView):
    handler, url_kwarg = ds.partner_claims, 'partner_id'


class OperatorDirectoryView(_DirectoryView):
    handler, url_kwarg = ds.operator_directory, 'country_id'
    operator_view = True


class OperatorSheetView(_DirectoryView):
    handler, url_kwarg = ds.operator_sheet, 'operator_id'
    operator_view = True


class OperatorLinesView(_DirectoryView):
    handler, url_kwarg = ds.operator_lines, 'operator_id'
    operator_view = True
