#!/usr/bin/env python
import os
import sys
import django

# Configuration Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'sunu_dash.settings')
django.setup()

from core.models import Client
from django.db.models import Count

def check_client_fields():
    """Vérifier les champs disponibles dans le modèle Client"""
    print("=== CHAMPS DISPONIBLES DANS LE MODÈLE CLIENT ===")
    
    # Obtenir un client pour voir ses champs
    client = Client.objects.first()
    if client:
        print(f"Exemple de client: {client.name}")
        print(f"Champs disponibles:")
        for field in client._meta.fields:
            print(f"  - {field.name}: {field.get_internal_type()}")
            if hasattr(client, field.name):
                value = getattr(client, field.name)
                print(f"    Valeur: {value}")
    
    # Compter les clients par nom
    print(f"\n=== ANALYSE DES DOUBLONS ===")
    clients_by_name = Client.objects.values('name').annotate(
        count=Count('id')
    ).filter(count__gt=1).order_by('-count')
    
    print(f"Nombre de noms avec des doublons: {clients_by_name.count()}")
    print(f"Top 10 des noms avec le plus de doublons:")
    for item in clients_by_name[:10]:
        print(f"  - {item['name']}: {item['count']} clients")
    
    # Analyser les relations
    print(f"\n=== RELATIONS DISPONIBLES ===")
    print(f"Relations du modèle Client:")
    for field in client._meta.get_fields():
        if field.is_relation:
            print(f"  - {field.name}: {field.related_model.__name__ if field.related_model else 'None'}")
    
    # Vérifier s'il y a des assurés liés
    print(f"\n=== ANALYSE DES ASSURÉS ===")
    total_insured = 0
    for client in Client.objects.all()[:5]:  # Analyser les 5 premiers clients
        insured_count = client.client_insureds.count()
        total_insured += insured_count
        print(f"  - {client.name}: {insured_count} assurés")
    
    print(f"Total assurés pour les 5 premiers clients: {total_insured}")

if __name__ == "__main__":
    check_client_fields()

