"""
Lot I3 (09/10/2026) — suppression de l'ancien modèle des sinistres.

Décision H : les sinistres et tout ce que l'ancien import en avait tiré (assurés, adhésions, polices, factures,
paiements, actes, partenaires, opérateurs) ne sont pas migrés mais **réimportés** : leurs montants et leurs actes
étaient faux (un sinistre = une seule ligne d'acte, montant d'une facture partagée compté une fois par sinistre,
dates inversées). Les employeurs (Client) et l'historique de leurs primes sont conservés.
Le nouveau modèle est créé par la migration suivante.
"""
from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0003_alter_client_creation_date_and_more'),
        ('file_handling', '0009_importsession_recap_files_sheet_summary'),
    ]

    operations = [
        # Les tables dépendantes d'abord
        migrations.DeleteModel(name='Claim'),
        migrations.DeleteModel(name='Invoice'),
        migrations.DeleteModel(name='PaymentMethod'),
        migrations.DeleteModel(name='InsuredEmployer'),
        migrations.DeleteModel(name='Insured'),
        migrations.DeleteModel(name='Act'),
        migrations.DeleteModel(name='ActFamily'),
        migrations.DeleteModel(name='ActCategory'),
        migrations.DeleteModel(name='Partner'),
        migrations.DeleteModel(name='Operator'),
        migrations.DeleteModel(name='Policy'),
    ]
