from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.exceptions import NotFound
from rest_framework import status

from .models import Country
from .serializers import CountrySerializer
from users.permissions import IsGlobalAdmin, IsSuperUser

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
            serializer.save(name=name.title(), code=code)
            return Response(serializer.data, status=status.HTTP_201_CREATED)

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

class CreateCountryFromExcel(APIView):
    """
    View allowing a global admin to bulk create countries from an Excel file.
    Required columns: 'name', 'code'.
    Optional columns: 'currency_code', 'currency_name'.
    Existing countries (by name or code) are skipped.
    """
    permission_classes = [IsAuthenticated, IsGlobalAdmin]

    def post(self, request):
        file = request.FILES.get('file')
        if not file:
            return Response({'error': 'No file provided.'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            df = pd.read_excel(file)
        except Exception as e:
            return Response({'error': f"Error reading file: {str(e)}"}, status=status.HTTP_400_BAD_REQUEST)

        # Required columns
        required_headers = ['name', 'code']
        if not all(header in df.columns for header in required_headers):
            return Response({'error': 'Missing required columns: "name" and/or "code".'}, status=status.HTTP_400_BAD_REQUEST)

        # Optional columns
        has_currency_code = 'currency_code' in df.columns
        has_currency_name = 'currency_name' in df.columns

        created_countries = []

        for index, row in df.iterrows():
            name = str(row['name']).strip() if pd.notna(row['name']) else ''
            code = str(row['code']).strip().upper() if pd.notna(row['code']) else ''

            if not name or not code:
                skipped_rows.append({
                    'row': index + 2,
                    'reason': "Missing name or code."
                })
                continue

            name_exists = Country.objects.filter(name__iexact=name).exists()
            code_exists = Country.objects.filter(code__iexact=code).exists()


            # Optional fields
            currency_code = ''
            currency_name = ''

            if has_currency_code:
                value = row['currency_code']
                if pd.notna(value) and str(value).strip():
                    currency_code = str(value).strip().upper()

            if has_currency_name:
                value = row['currency_name']
                if pd.notna(value) and str(value).strip():
                    currency_name = str(value).strip()

            country = Country(
                name=name.title(),
                code=code,
                currency_code=currency_code,
                currency_name=currency_name,
            )
            country.save()
            created_countries.append(country)

        serializer = CountrySerializer(created_countries, many=True)
        return Response({
            'created_count': len(created_countries),
            'created_countries': serializer.data,
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
            # Remove `is_active` from output
            for data in serializer.data:
                data.pop('is_active', None)

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
