# Column name synonyms for harmonization in normalize_columns

COLUMN_SYNONYMS = {
    'reglementid': 'claim_id',
    'id_reglement': 'claim_id',
    'id_sinistre': 'claim_id',
    'numero_de_sinistre': 'claim_id',

    'date_reglement': 'payment_date',
    'date_de_reglement': 'payment_date',

    'beneficiaire': 'beneficiary_name',
    'nom_beneficiaire': 'beneficiary_name',
    'nom_de_beneficiaire': 'beneficiary_name',

    'assures_principal': 'main_insured',
    'assure_principal': 'main_insured',
    'nom_assuré_principal': 'main_insured',
    'nom_assures_principal': 'main_insured',

    'partnerid': 'partner_name',
    'nom_du_partenaire': 'partner_name',
    'nom_partenaire': 'partner_name',

    'employeur': 'employer_name',
    'nom_employeur': 'employer_name',

    'n°_police': 'policy_number',
    'numero_de_police': 'policy_number',
    'numero_police': 'policy_number',


    'n°_cheque': 'payment_method',
    'autres_moyen_de_payement': 'payment_method',
    'n°cheque/autre_moyent_de_payement': 'payment_method',

    'totalmttreclame': 'amount_claimed',
    'montant_facture': 'amount_claimed',

    'totalmttrembourse': 'amount_reimbursed',
    'montant_rembourse': 'amount_reimbursed',
    'montant remboursé': 'amount_reimbursed',

    'numfacture': 'invoice_number',
    'numero_de_facture': 'invoice_number',

    'note': 'note',
    'note_generale': 'note',

    # Champs supplémentaires pour STAT
    'broker name': 'broker_name',
    'statut_assure': 'insured_status',
    'statut': 'claim_status',
    'categorie_d\'acte': 'act_category',
    'famille_acte': 'act_family',
    'nom_acte': 'act_name',
    'adresse du partenaire': 'partner_address',
    'pays du partenaire': 'partner_country',
    'date_de_sinistre': 'incident_date',
    'date_sinistre': 'incident_date',
    'modifié par': 'modified_by',
}
