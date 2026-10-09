"""
Correspondance des colonnes des deux fichiers vers des noms communs (décidée le 08/10/2026),
et reconnaissance de la nature d'un fichier d'après ses colonnes.

Les en-têtes sont comparés par header_key (sans accents, casse, espaces ni ponctuation) :
'Numero de sinistre', 'Numéro de Sinistre' et 'numero_de_sinistre' sont la même colonne.
"""
from .normalize import header_key

STAT = 'stat'
RECAP = 'recap'

KIND_LABELS = {STAT: 'fichier statistique', RECAP: 'fichier récap'}

# nom commun -> (libellé lisible pour les messages, en-têtes acceptés, par ordre de préférence)
STAT_COLUMNS = {
    'employer': ('Nom Employeur', ['Nom Employeur']),
    'member_id': ('Broker_SunuId', ['Broker_SunuId', 'Unnamed: 1']),
    'broker': ('Broker Name', ['Broker Name']),
    'beneficiary': ('Nom bénéficiaire', ['Nom bénéficiaire']),
    'plan': ('Acte_Contraté_Assuré', ['Acte_Contraté_Assuré', 'Acte Contracté Assuré']),
    'insured_status': ('Statut Assuré', ['Statut Assuré']),
    'policy_number': ('Numero de police', ['Numero de police']),
    'main_insured': ('Nom Assuré Principal', ['Nom Assuré Principal']),
    'partner': ('Nom du partenaire', ['Nom du partenaire']),
    'partner_address': ('Adresse du Partenaire', ['Adresse du Partenaire']),
    'partner_country': ('Pays du partenaire', ['Pays du partenaire']),
    'claim_id': ('Numero de sinistre', ['Numero de sinistre']),
    'claim_status': ('Statut', ['Statut']),
    'incident_date': ('Date de sinistre', ['Date de sinistre']),
    'settlement_date': ('Date de règlement', ['Date de règlement']),
    'act_category': ("Categorie d'acte", ["Categorie d'acte", "Catégorie d'acte"]),
    'guarantee_label': ('Famille Acte', ['Famille Acte']),
    'act_name': ('Nom Acte', ['Nom Acte']),
    'claimed_amount': ('Montant facturé', ['Montant facturé']),
    'reimbursed_amount': ('Montant remboursé', ['Montant remboursé']),
    'payment_ref': ('N°cheque/Autre_Moyent_de_payement',
                    ['N°cheque/Autre_Moyent_de_payement', 'N°cheque/Autre_Moyen_de_payement']),
    'note': ('Note Générale', ['Note Générale']),
    'invoice_number': ('Numero de Facture', ['Numero de Facture']),
    'operator': ('Modifié par', ['Modifié par']),
}

STAT_REQUIRED = [
    'claim_id', 'settlement_date', 'claimed_amount', 'reimbursed_amount', 'claim_status',
    'beneficiary', 'main_insured', 'insured_status', 'policy_number', 'employer',
    'partner', 'act_category', 'act_name', 'incident_date',
]

RECAP_COLUMNS = {
    'claim_id': ('reglementId', ['reglementId']),
    'settlement_date': ('date_reglement', ['date_reglement']),
    'beneficiary': ('beneficiaire', ['beneficiaire']),
    'cheque_number': ('N°_Cheque', ['N°_Cheque']),
    'other_payment': ('autres_Moyen_de_payement', ['autres_Moyen_de_payement']),
    'partner': ('partnerId', ['partnerId']),
    'main_insured': ('Assurés_principal', ['Assurés_principal']),
    'employer': ('Employeur', ['Employeur']),
    'policy_number': ('N°_police', ['N°_police']),
    'claimed_amount': ('totalmttreclame', ['totalmttreclame']),
    'reimbursed_amount': ('totalmttrembourse', ['totalmttrembourse']),
    'invoice_number': ('NumFacture', ['NumFacture']),
    'note': ('Note', ['Note']),
}

RECAP_REQUIRED = ['claim_id', 'settlement_date', 'claimed_amount', 'reimbursed_amount']

# Colonnes propres à chaque nature : leur présence suffit à reconnaître le fichier
SIGNATURES = {
    STAT: ['claim_id', 'act_name', 'claimed_amount'],
    RECAP: ['claim_id', 'claimed_amount', 'reimbursed_amount'],
}

SPECS = {STAT: (STAT_COLUMNS, STAT_REQUIRED), RECAP: (RECAP_COLUMNS, RECAP_REQUIRED)}


def match_columns(columns, kind):
    """{nom commun: en-tête trouvé dans le fichier} pour la nature `kind`."""
    spec, _ = SPECS[kind]
    by_key = {}
    for col in columns:
        by_key.setdefault(header_key(col), col)
    found = {}
    for canonical, (_, accepted) in spec.items():
        for header in accepted:
            col = by_key.get(header_key(header))
            if col is not None:
                found[canonical] = col
                break
    return found


def missing_columns(columns, kind):
    """Libellés des colonnes obligatoires absentes (ou à l'en-tête vide)."""
    spec, required = SPECS[kind]
    found = match_columns(columns, kind)
    return [spec[c][0] for c in required if c not in found]


def detect_kind(columns):
    """STAT, RECAP ou None selon les colonnes présentes."""
    for kind in (STAT, RECAP):
        found = match_columns(columns, kind)
        if all(c in found for c in SIGNATURES[kind]):
            return kind
    return None
