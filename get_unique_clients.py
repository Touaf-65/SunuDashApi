#!/usr/bin/env python
import os
import sys
import django

# Configuration Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'sunu_dash.settings')
django.setup()

from core.models import Client
from django.db.models import Count

# Récupérer des clients avec des noms uniques
unique_clients = Client.objects.values('name').annotate(count=Count('name')).filter(count=1).values_list('name', flat=True)[:10]

print("=== CLIENTS AVEC NOMS UNIQUES ===")
for i, name in enumerate(unique_clients, 1):
    client = Client.objects.get(name=name)
    print(f"{i}. {client.name} (ID: {client.id}, Pays: {client.country.name}, Prime: {client.prime or 'Aucune'})")

print(f"\nTotal clients uniques trouvés: {len(unique_clients)}")
