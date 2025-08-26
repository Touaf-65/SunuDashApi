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

# Récupérer les premiers clients de chaque nom
client_names = [
    'COOPEC AD',
    'COOPEC GRACE PLUS', 
    'FAMILLE TETE KWAME YAYRA',
    'GROUPE SOMATRANS INTERNATIONAL',
    'GULF OF GUINEA TRADING COMPANY',
    'INSTITUT AFRICAIN D\'INFORMATIQUE (IAI)'
]

# Récupérer le premier client de chaque nom
test_clients = []
for name in client_names:
    client = Client.objects.filter(name=name).first()
    if client:
        test_clients.append(client.name)
        print(f"Client sélectionné: {client.name} (ID: {client.id})")

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
filename = 'test_import_primes.xlsx'
df.to_excel(filename, index=False)

print(f"\nFichier {filename} créé avec succès!")
print("\nContenu du fichier:")
print(df.to_string(index=False))

print(f"\nPrimes actuelles des clients:")
for i, name in enumerate(test_clients):
    client = Client.objects.filter(name=name).first()
    print(f"- {name}: {client.prime or 'Aucune prime'}")
