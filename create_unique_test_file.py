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
from django.db.models import Count

# Récupérer des clients avec des noms uniques (pas de doublons)
unique_clients = Client.objects.values('name').annotate(count=Count('name')).filter(count=1).values_list('name', flat=True)[:10]

if not unique_clients:
    # Si aucun client unique, prendre les premiers clients de chaque nom
    all_clients = Client.objects.all()[:10]
    unique_clients = []
    seen_names = set()
    
    for client in all_clients:
        if client.name not in seen_names:
            unique_clients.append(client.name)
            seen_names.add(client.name)
            if len(unique_clients) >= 6:
                break

print("=== CLIENTS SÉLECTIONNÉS ===")
for i, name in enumerate(unique_clients, 1):
    client = Client.objects.filter(name=name).first()
    if client:
        print(f"{i}. {client.name} (ID: {client.id}, Pays: {client.country.name})")

# Générer des primes aléatoires
primes = [random.randint(1000, 5000) for _ in range(len(unique_clients))]
dates = [(datetime.now() - timedelta(days=random.randint(1, 30))).strftime('%Y-%m-%d') for _ in range(len(unique_clients))]

# Créer le DataFrame
df = pd.DataFrame({
    'Nom Client': unique_clients,
    'Prime': primes,
    'Date Paiement Prime': dates
})

# Sauvegarder le fichier
filename = 'test_import_primes_unique.xlsx'
df.to_excel(filename, index=False)

print(f"\nFichier {filename} créé avec succès!")
print("\nContenu du fichier:")
print(df.to_string(index=False))

print(f"\nPrimes actuelles des clients:")
for i, name in enumerate(unique_clients):
    client = Client.objects.filter(name=name).first()
    if client:
        print(f"- {name}: {client.prime or 'Aucune prime'}")

