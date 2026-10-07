from rest_framework import serializers
from .models import Country, CountryDeactivationRequest


def clean_label(value):
    """
    Nettoie un libellé saisi (nom de pays, de devise) sans en changer la casse :
    espaces superflus retirés, première lettre en majuscule. Contrairement à
    str.title(), « Côte d'Ivoire » et « F CFA » restent intacts.
    """
    value = " ".join(value.split())
    return value[:1].upper() + value[1:]


class CountrySerializer(serializers.ModelSerializer):
    class Meta:
        model = Country
        fields = (
            'id',
            'name',
            'code',
            'currency_code',
            'currency_name',
            'is_active',
        )
        # L'unicité du nom et du code est vérifiée dans validate_name / validate_code
        # (sans tenir compte de la casse, messages en français) : on retire les
        # validateurs d'unicité automatiques, sensibles à la casse et en anglais.
        extra_kwargs = {
            'name': {'validators': [], 'error_messages': {'blank': "Le nom du pays est requis."}},
            'code': {'validators': [], 'error_messages': {
                'blank': "Le code pays est requis.",
                'max_length': "Le code pays doit contenir uniquement des lettres (max 4).",
            }},
        }

    def validate_name(self, value):
        """
        Nom unique sans tenir compte de la casse (« togo » = « TOGO »). La contrainte
        unique de la base est sensible à la casse et ne suffit pas. Le pays modifié
        est exclu, pour pouvoir changer la casse de son propre nom.
        """
        value = clean_label(value)
        if not value:
            raise serializers.ValidationError("Le nom du pays est requis.")
        duplicates = Country.objects.filter(name__iexact=value)
        if self.instance is not None:
            duplicates = duplicates.exclude(pk=self.instance.pk)
        if duplicates.exists():
            raise serializers.ValidationError(f"Un pays avec le nom « {value} » existe déjà.")
        return value

    def validate_code(self, value):
        if not value.isalpha() or len(value) > 4:
            raise serializers.ValidationError("Le code pays doit contenir uniquement des lettres (max 4).")
        value = value.upper()
        duplicates = Country.objects.filter(code__iexact=value)
        if self.instance is not None:
            duplicates = duplicates.exclude(pk=self.instance.pk)
        if duplicates.exists():
            raise serializers.ValidationError(f"Un pays avec le code « {value} » existe déjà.")
        return value

    def validate_currency_code(self, value):
        if value and (not value.isalpha() or len(value) > 10):
            raise serializers.ValidationError("Code devise invalide.")
        return value.upper()

    def validate_currency_name(self, value):
        return clean_label(value) if value else value


class CountryDeactivationRequestSerializer(serializers.ModelSerializer):
    """Demande de désactivation, avec l'avancement du vote et ce que l'utilisateur connecté peut faire."""
    country = CountrySerializer(read_only=True)
    requested_by = serializers.SerializerMethodField()
    decided_by = serializers.SerializerMethodField()
    status_label = serializers.CharField(source='get_status_display', read_only=True)
    approvals = serializers.SerializerMethodField()
    rejections = serializers.SerializerMethodField()
    votes = serializers.SerializerMethodField()
    my_vote = serializers.SerializerMethodField()
    can_vote = serializers.SerializerMethodField()
    can_cancel = serializers.SerializerMethodField()

    class Meta:
        model = CountryDeactivationRequest
        fields = (
            'id', 'country', 'reason', 'status', 'status_label', 'requested_by', 'decided_by',
            'eligible_voters', 'required_approvals', 'approvals', 'rejections', 'votes',
            'created_at', 'expires_at', 'decided_at', 'my_vote', 'can_vote', 'can_cancel',
        )

    @staticmethod
    def _person(user):
        return {'id': user.id, 'name': f"{user.first_name} {user.last_name}".strip(), 'email': user.email} if user else None

    def _user(self):
        return self.context['request'].user

    def get_requested_by(self, obj):
        return self._person(obj.requested_by)

    def get_decided_by(self, obj):
        return self._person(obj.decided_by)

    def get_approvals(self, obj):
        return sum(v.decision == 'APPROVE' for v in obj.votes.all())

    def get_rejections(self, obj):
        return sum(v.decision == 'REJECT' for v in obj.votes.all())

    def get_votes(self, obj):
        return [{'admin': self._person(v.admin), 'decision': v.decision, 'comment': v.comment,
                 'created_at': v.created_at} for v in obj.votes.all()]

    def get_my_vote(self, obj):
        vote = next((v for v in obj.votes.all() if v.admin_id == self._user().pk), None)
        return vote.decision if vote else None

    def get_can_vote(self, obj):
        user = self._user()
        if obj.status != 'PENDING':
            return False
        if user.is_superuser_role():
            return True
        return user.is_admin_global() and self.get_my_vote(obj) is None

    def get_can_cancel(self, obj):
        user = self._user()
        return obj.status == 'PENDING' and (obj.requested_by_id == user.pk or user.is_superuser_role())
