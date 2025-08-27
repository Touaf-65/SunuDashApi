#!/usr/bin/env python
import os
import sys
import django
from decimal import Decimal

# Configuration Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'sunu_dash.settings')
django.setup()

from core.models import Client
from django.db.models import Count, Sum, Q
from django.db import transaction

def cleanup_database_simple():
    """
    Épure la base de données en gardant seulement les meilleurs clients pour chaque nom
    basé sur le nombre d'assurés et la date de création
    """
    print("=== ÉPURATION SIMPLIFIÉE DE LA BASE DE DONNÉES ===")
    
    # 1. Analyser la situation actuelle
    total_clients = Client.objects.count()
    print(f"Nombre total de clients avant épuration: {total_clients}")
    
    # Compter les clients par nom
    clients_by_name = Client.objects.values('name').annotate(
        count=Count('id')
    ).filter(count__gt=1).order_by('-count')
    
    print(f"\nClients avec des doublons:")
    for item in clients_by_name[:10]:  # Afficher les 10 premiers
        print(f"- {item['name']}: {item['count']} clients")
    
    total_deleted = 0
    
    # 2. Pour chaque nom avec des doublons, garder le meilleur client
    print(f"\n=== SÉLECTION DES MEILLEURS CLIENTS ===")
    
    # Récupérer les noms avec des doublons
    duplicate_names = Client.objects.values('name').annotate(
        count=Count('id')
    ).filter(count__gt=1).values_list('name', flat=True)
    
    total_duplicates = len(duplicate_names)
    print(f"Noms avec des doublons trouvés: {total_duplicates}")
    
    if total_duplicates > 0:
        clients_to_delete = []
        
        for name in duplicate_names:
            # Récupérer tous les clients avec ce nom
            clients = Client.objects.filter(name=name)
            
            # Calculer le nombre d'assurés pour chaque client
            clients_with_insured_count = []
            for client in clients:
                insured_count = client.client_insureds.count()
                clients_with_insured_count.append({
                    'client': client,
                    'insured_count': insured_count
                })
            
            # Trier par nombre d'assurés (décroissant), puis par date de création (croissant)
            clients_with_insured_count.sort(
                key=lambda x: (-x['insured_count'], x['client'].creation_date)
            )
            
            # Garder le premier (le meilleur) et marquer les autres pour suppression
            best_client_info = clients_with_insured_count[0]
            best_client = best_client_info['client']
            clients_to_remove = [info['client'] for info in clients_with_insured_count[1:]]
            
            print(f"\n{name}:")
            print(f"  ✅ Gardé: {best_client.name} (ID: {best_client.id})")
            print(f"    - Assurés: {best_client_info['insured_count']}")
            print(f"    - Date création: {best_client.creation_date}")
            print(f"    - Pays: {best_client.country.name}")
            
            for client_info in clients_with_insured_count[1:]:
                client = client_info['client']
                print(f"  ❌ À supprimer: {client.name} (ID: {client.id})")
                print(f"    - Assurés: {client_info['insured_count']}")
                print(f"    - Date création: {client.creation_date}")
                print(f"    - Pays: {client.country.name}")
                clients_to_delete.append(client.id)
        
        # Supprimer automatiquement les doublons
        if clients_to_delete:
            print(f"\nSuppression de {len(clients_to_delete)} clients en doublon...")
            with transaction.atomic():
                deleted_count = Client.objects.filter(id__in=clients_to_delete).delete()[0]
                total_deleted += deleted_count
                print(f"✅ {deleted_count} clients en doublon supprimés avec succès!")
    
    # 3. Résultats finaux
    print(f"\n=== RÉSULTATS FINAUX ===")
    final_count = Client.objects.count()
    print(f"Nombre total de clients après épuration: {final_count}")
    print(f"Réduction: {total_deleted} clients supprimés")
    
    # Vérifier qu'il n'y a plus de doublons
    remaining_duplicates = Client.objects.values('name').annotate(
        count=Count('id')
    ).filter(count__gt=1).count()
    
    if remaining_duplicates == 0:
        print("✅ Aucun doublon restant!")
    else:
        print(f"⚠️  {remaining_duplicates} noms ont encore des doublons")
    
    # Afficher quelques statistiques
    print(f"\n=== STATISTIQUES ===")
    total_insured = 0
    for client in Client.objects.all():
        total_insured += client.client_insureds.count()
    
    print(f"Total assurés: {total_insured}")
    print(f"Nombre de clients uniques: {final_count}")
    
    return final_count

if __name__ == "__main__":
    cleanup_database_simple()

