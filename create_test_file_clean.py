#!/usr/bin/env python
import os
import sys
import django
import pandas as pd
import random
from datetime import datetime, timedelta

# Configuration Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'sunu_dash.settings')
django.setup()

from core.models import Client

# Récupérer tous les clients uniques (après épuration)
clients = Client.objects.all().order_by('name')[:10]  # Prendre les 10 premiers

if not clients:
    print("Aucun client trouvé dans la base de données!")
    exit()

print("=== CLIENTS SÉLECTIONNÉS POUR LE TEST ===")
test_clients = []
for i, client in enumerate(clients, 1):
    test_clients.append(client.name)
    print(f"{i}. {client.name} (ID: {client.id}, Pays: {client.country.name})")

# Générer des primes aléatoires
primes = [random.randint(1000, 5000) for _ in range(len(test_clients))]
dates = [(datetime.now() - timedelta(days=random.randint(1, 30))).strftime('%Y-%m-%d') for _ in range(len(test_clients))]

# Créer le DataFrame
df = pd.DataFrame({
    'Nom Client': test_clients,
    'Prime': primes,
    'Date Paiement Prime': dates
})

# Sauvegarder le fichier
filename = 'test_import_primes_clean.xlsx'
df.to_excel(filename, index=False)

print(f"\nFichier {filename} créé avec succès!")
print("\nContenu du fichier:")
print(df.to_string(index=False))

print(f"\nPrimes actuelles des clients:")
for i, name in enumerate(test_clients):
    client = Client.objects.filter(name=name).first()
    if client:
        print(f"- {name}: {client.prime or 'Aucune prime'}")
