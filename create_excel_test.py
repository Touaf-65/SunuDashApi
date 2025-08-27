import pandas as pd

# Créer des données de test
data = {
    'Nom Client': [
        'AXE CAPITAL HUMAIN SA/PC LCT',
        'BRIGHTNESS MARITIME AGENCY', 
        'COOPEC AD',
        'COOPEC GRACE PLUS',
        'FAMILLE TETE KWAME YAYRA'
    ],
    'Prime': [2500, 1800, 3200, 2100, 1500],
    'Date Paiement Prime': ['2025-08-20', '2025-08-15', '2025-08-18', '2025-08-22', '2025-08-25']
}

# Créer le DataFrame
df = pd.DataFrame(data)

# Sauvegarder en Excel
df.to_excel('test_import_primes.xlsx', index=False)

print("Fichier Excel créé avec succès!")
print("Contenu:")
print(df)

