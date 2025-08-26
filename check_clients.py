#!/usr/bin/env python
import os
import sys
import django

# Configuration Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'sunu_dash.settings')
django.setup()

from core.models import Client

print("=== CLIENTS DISPONIBLES ===")
clients = Client.objects.all()[:10]

for i, client in enumerate(clients, 1):
    print(f"{i}. {client.name} (ID: {client.id}, Pays: {client.country.name})")

print(f"\nTotal clients: {Client.objects.count()}")
