import pandas as pd
from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.exceptions import NotFound
from rest_framework import status

from .models import Country
from .serializers import CountrySerializer
from users.permissions import IsGlobalAdmin, IsSuperUser
from users.utils import read_import_file

class CreateCountryView(APIView):
    """
    View allowing a superuser or global admin to create a new country.
    It checks for duplicates based on country name and/or code before creation.
    """
    permission_classes = [IsAuthenticated, IsGlobalAdmin]

    def post(self, request):
        name = request.data.get('name', '').strip()
        code = request.data.get('code', '').strip().upper()

        if not name or not code:
            return Response(
                {"error": "Les champs 'name' et 'code' sont requis."},
                status=status.HTTP_400_BAD_REQUEST
            )

        name_exists = Country.objects.filter(name__iexact=name).exists()
        code_exists = Country.objects.filter(code__iexact=code).exists()

        if name_exists and code_exists:
            return Response(
                {"error": f"Le pays '{name}' de code '{code}' existe déjà."},
                status=status.HTTP_400_BAD_REQUEST
            )
        elif name_exists:
            return Response(
                {"error": f"Un pays avec le nom '{name}' existe déjà."},
                status=status.HTTP_400_BAD_REQUEST
            )
        elif code_exists:
            return Response(
                {"error": f"Un pays avec le code '{code}' existe déjà."},
                status=status.HTTP_400_BAD_REQUEST
            )

        serializer = CountrySerializer(data=request.data)
        if serializer.is_valid():
            serializer.save()  # nom nettoyé et code en majuscules par le serializer
            return Response(serializer.data, status=status.HTTP_201_CREATED)

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

class CreateCountryFromExcel(APIView):
    """
    View allowing a global admin to bulk create countries from an Excel or CSV file
    (.xlsx, .xls, .csv).
    Required columns: 'name', 'code'.
    Optional columns: 'currency_code', 'currency_name' (defaults: XOF / F CFA).
    Rows are skipped, with their reason, when the name or code is missing or invalid,
    or when a country with the same name or code (case-insensitive) already exists.
    """
    permission_classes = [IsAuthenticated, IsGlobalAdmin]

    def post(self, request):
        file = request.FILES.get('file')
        if not file:
            return Response({'error': 'Aucun fichier fourni.'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            df = read_import_file(file)
        except Exception as e:
            return Response({'error': f"Fichier invalide : {e}"}, status=status.HTTP_400_BAD_REQUEST)

        # Required columns
        required_headers = ['name', 'code']
        if not all(header in df.columns for header in required_headers):
            return Response({'error': 'Le fichier doit contenir les colonnes : name, code.'}, status=status.HTTP_400_BAD_REQUEST)

        def cell(row, column):
            """Cleaned text of an optional cell, or '' if the column is absent or the cell empty."""
            if column not in df.columns or pd.isna(row[column]):
                return ''
            return str(row[column]).strip()

        created_countries = []
        skipped_rows = []

        for index, row in df.iterrows():
            line = index + 2  # line number in the file (header is line 1)
            name = cell(row, 'name')
            code = cell(row, 'code').upper()

            if not name or not code:
                skipped_rows.append({'row': line, 'reason': "Nom ou code manquant."})
                continue

            if Country.objects.filter(name__iexact=name).exists():
                skipped_rows.append({'row': line, 'reason': f"Un pays nommé « {name} » existe déjà."})
                continue
            if Country.objects.filter(code__iexact=code).exists():
                skipped_rows.append({'row': line, 'reason': f"Un pays de code « {code} » existe déjà."})
                continue

            data = {'name': name, 'code': code}  # nom nettoyé par le serializer
            # Empty currency cells keep the model defaults (XOF / F CFA)
            if cell(row, 'currency_code'):
                data['currency_code'] = cell(row, 'currency_code')
            if cell(row, 'currency_name'):
                data['currency_name'] = cell(row, 'currency_name')

            serializer = CountrySerializer(data=data)
            if not serializer.is_valid():
                reasons = " ".join(str(msg) for errors in serializer.errors.values() for msg in errors)
                skipped_rows.append({'row': line, 'reason': reasons})
                continue
            created_countries.append(serializer.save())

        message = f"{len(created_countries)} pays créé(s) avec succès."
        if skipped_rows:
            message += f" {len(skipped_rows)} ligne(s) ignorée(s)."
        return Response({
            'message': message,
            'created_count': len(created_countries),
            'created_countries': CountrySerializer(created_countries, many=True).data,
            'lignes_ignores': len(skipped_rows),
            'skipped_rows': skipped_rows,
        }, status=status.HTTP_201_CREATED)


class CountryMixin:
    """
    Mixin to provide a method for retrieving a Country instance by pk,
    with optional filtering based on the user's role.
    """

    def get_country(self, pk, user=None):
        try:
            if user and not user.is_superuser:
                # Global Admins can only access active countries
                return Country.objects.get(pk=pk, is_active=True)
            return Country.objects.get(pk=pk)
        except Country.DoesNotExist:
            raise NotFound(detail="Country not found.")


class ListCountriesView(APIView):
    """
    View to list all countries.
    - Global Admins: only active countries, without 'is_active' field.
    - Superusers: all countries, with 'is_active' included.
    """
    permission_classes = [IsAuthenticated, IsSuperUser | IsGlobalAdmin]

    def get(self, request):
        user = request.user

        if user.is_superuser_role():
            countries = Country.objects.all()
            serializer = CountrySerializer(countries, many=True)
        else:
            countries = Country.objects.filter(is_active=True)
            serializer = CountrySerializer(countries, many=True)
            
        return Response(serializer.data, status=status.HTTP_200_OK)


class CountryDetailView(APIView, CountryMixin):
    """
    Retrieve a country's details by its ID.
    - Global Admins: only active countries, and 'is_active' is hidden.
    - Superusers: see everything.
    """
    permission_classes = [IsAuthenticated, IsSuperUser | IsGlobalAdmin]

    def get(self, request, pk):
        country = self.get_country(pk, request.user)

        data = {
            "name": country.name,
            "code": country.code,
            "currency": country.currency_name,
            "currency code": country.currency_code
        }

        if request.user.is_superuser:
            data["is_active"] = country.is_active

        return Response(data, status=status.HTTP_200_OK)


class CountryUpdateView(APIView, CountryMixin):
    """
    Update a country's information.
    Only allowed for Global Admins and only on active countries.
    """
    permission_classes = [IsAuthenticated, IsGlobalAdmin]

    def put(self, request, pk):
        country = self.get_country(pk, request.user)

        if not country.is_active:
            raise PermissionDenied("Cannot modify an inactive country.")

        serializer = CountrySerializer(country, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_200_OK)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class CountryDeleteView(APIView, CountryMixin):
    """
    Soft-delete a country by setting its 'is_active' field to False.
    Only allowed for Global Admins and only on active countries.
    """
    permission_classes = [IsAuthenticated, IsGlobalAdmin]

    def delete(self, request, pk):
        country = self.get_country(pk, request.user)

        if not country.is_active:
            return Response(
                {"detail": "Country is already inactive."},
                status=status.HTTP_400_BAD_REQUEST
            )

        country.is_active = False
        country.save()
        return Response({"message": "Country has been deactivated."}, status=status.HTTP_200_OK)


class CountryReactivateView(APIView):
    """
    Allows a superuser to reactivate a previously deactivated country.
    """
    permission_classes = [IsAuthenticated, IsSuperUser]

    def post(self, request, pk):
        try:
            country = Country.objects.get(pk=pk)
        except Country.DoesNotExist:
            raise NotFound("Country not found.")

        if country.is_active:
            return Response({"message": "Country is already active."}, status=status.HTTP_200_OK)

        country.is_active = True
        country.save()
        return Response({"message": "Country has been reactivated."}, status=status.HTTP_200_OK)
