from rest_framework import serializers
from .models import (
    Client, ClientPrimeHistory, Policy, Insured, InsuredEmployer,
    Invoice, Partner, PaymentMethod, Act, ActFamily, ActCategory,
    Operator, Claim
)
from countries.models import Country
from file_handling.models import File, ImportSession


class CountrySerializer(serializers.ModelSerializer):
    class Meta:
        model = Country
        fields = ['id', 'name']


class FileSerializer(serializers.ModelSerializer):
    class Meta:
        model = File
        fields = ['id', 'file', 'uploaded_at']


class ImportSessionSerializer(serializers.ModelSerializer):
    class Meta:
        model = ImportSession
        fields = ['id', 'status', 'started_at', 'finished_at']


class ClientSerializer(serializers.ModelSerializer):
    country = serializers.PrimaryKeyRelatedField(queryset=Country.objects.all())
    file = serializers.PrimaryKeyRelatedField(queryset=File.objects.all(), allow_null=True, required=False)
    import_session = serializers.PrimaryKeyRelatedField(queryset=ImportSession.objects.all(), allow_null=True, required=False)

    class Meta:
        model = Client
        fields = '__all__'


class ClientPrimeHistorySerializer(serializers.ModelSerializer):
    client = serializers.PrimaryKeyRelatedField(queryset=Client.objects.all())

    class Meta:
        model = ClientPrimeHistory
        fields = '__all__'


class PolicySerializer(serializers.ModelSerializer):
    client = serializers.PrimaryKeyRelatedField(queryset=Client.objects.all())
    file = serializers.PrimaryKeyRelatedField(queryset=File.objects.all(), allow_null=True, required=False)
    import_session = serializers.PrimaryKeyRelatedField(queryset=ImportSession.objects.all(), allow_null=True, required=False)

    class Meta:
        model = Policy
        fields = '__all__'


class InsuredSerializer(serializers.ModelSerializer):
    primary_insured = serializers.PrimaryKeyRelatedField(queryset=Insured.objects.all(), allow_null=True, required=False)
    file = serializers.PrimaryKeyRelatedField(queryset=File.objects.all(), allow_null=True, required=False)
    import_session = serializers.PrimaryKeyRelatedField(queryset=ImportSession.objects.all(), allow_null=True, required=False)

    class Meta:
        model = Insured
        fields = '__all__'


class InsuredEmployerSerializer(serializers.ModelSerializer):
    insured = serializers.PrimaryKeyRelatedField(queryset=Insured.objects.all())
    employer = serializers.PrimaryKeyRelatedField(queryset=Client.objects.all())
    policy = serializers.PrimaryKeyRelatedField(queryset=Policy.objects.all())
    file = serializers.PrimaryKeyRelatedField(queryset=File.objects.all(), allow_null=True, required=False)
    import_session = serializers.PrimaryKeyRelatedField(queryset=ImportSession.objects.all(), allow_null=True, required=False)
    primary_insured_ref = serializers.PrimaryKeyRelatedField(queryset=Insured.objects.all(), allow_null=True, required=False)

    class Meta:
        model = InsuredEmployer
        fields = '__all__'


class InvoiceSerializer(serializers.ModelSerializer):
    provider = serializers.PrimaryKeyRelatedField(queryset=Partner.objects.all())
    insured = serializers.PrimaryKeyRelatedField(queryset=Insured.objects.all())
    file = serializers.PrimaryKeyRelatedField(queryset=File.objects.all(), allow_null=True, required=False)
    import_session = serializers.PrimaryKeyRelatedField(queryset=ImportSession.objects.all(), allow_null=True, required=False)

    class Meta:
        model = Invoice
        fields = '__all__'


class PartnerSerializer(serializers.ModelSerializer):
    country = serializers.PrimaryKeyRelatedField(queryset=Country.objects.all())

    class Meta:
        model = Partner
        fields = '__all__'


class PaymentMethodSerializer(serializers.ModelSerializer):
    provider = serializers.PrimaryKeyRelatedField(queryset=Partner.objects.all())

    class Meta:
        model = PaymentMethod
        fields = '__all__'


class ActCategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = ActCategory
        fields = '__all__'


class ActFamilySerializer(serializers.ModelSerializer):
    category = serializers.PrimaryKeyRelatedField(queryset=ActCategory.objects.all())

    class Meta:
        model = ActFamily
        fields = '__all__'


class ActSerializer(serializers.ModelSerializer):
    family = serializers.PrimaryKeyRelatedField(queryset=ActFamily.objects.all())

    class Meta:
        model = Act
        fields = '__all__'


class OperatorSerializer(serializers.ModelSerializer):
    class Meta:
        model = Operator
        fields = '__all__'


class ClaimSerializer(serializers.ModelSerializer):
    invoice = serializers.PrimaryKeyRelatedField(queryset=Invoice.objects.all(), allow_null=True, required=False)
    act = serializers.PrimaryKeyRelatedField(queryset=Act.objects.all(), allow_null=True, required=False)
    operator = serializers.PrimaryKeyRelatedField(queryset=Operator.objects.all(), allow_null=True, required=False)
    insured = serializers.PrimaryKeyRelatedField(queryset=Insured.objects.all(), allow_null=True, required=False)
    partner = serializers.PrimaryKeyRelatedField(queryset=Partner.objects.all(), allow_null=True, required=False)
    policy = serializers.PrimaryKeyRelatedField(queryset=Policy.objects.all(), allow_null=True, required=False)
    file = serializers.PrimaryKeyRelatedField(queryset=File.objects.all(), allow_null=True, required=False)
    import_session = serializers.PrimaryKeyRelatedField(queryset=ImportSession.objects.all(), allow_null=True, required=False)

    class Meta:
        model = Claim
        fields = '__all__'
