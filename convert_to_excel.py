import pandas as pd

# Lire le fichier CSV
df = pd.read_csv('test_import_primes.csv')

# Sauvegarder en Excel
df.to_excel('test_import_primes.xlsx', index=False)

print("Fichier Excel créé avec succès!")
print("Contenu:")
print(df)

