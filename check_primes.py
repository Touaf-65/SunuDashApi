#!/usr/bin/env python
import os
import sys
import django

# Configuration Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'sunu_dash.settings')
django.setup()

from core.models import Client

# Clients à vérifier
client_names = [
    'COOPEC AD',
    'COOPEC GRACE PLUS', 
    'FAMILLE TETE KWAME YAYRA',
    'GROUPE SOMATRANS INTERNATIONAL',
    'GULF OF GUINEA TRADING COMPANY',
    'INSTITUT AFRICAIN D\'INFORMATIQUE (IAI)'
]

print("=== PRIMES ACTUELLES DES CLIENTS ===")
for name in client_names:
    try:
        clients = Client.objects.filter(name=name)
        if clients.count() == 1:
            client = clients.first()
            print(f"- {client.name}: {client.prime or 'Aucune prime'} (ID: {client.id})")
        else:
            print(f"- {name}: {clients.count()} clients trouvés (doublons)")
            for i, client in enumerate(clients[:3]):  # Afficher les 3 premiers
                print(f"  {i+1}. ID: {client.id}, Prime: {client.prime or 'Aucune'}")
    except Exception as e:
        print(f"- {name}: Erreur - {e}")

print(f"\nTotal clients vérifiés: {len(client_names)}")
