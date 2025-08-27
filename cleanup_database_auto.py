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

def cleanup_database_auto():
    """
    Épure automatiquement la base de données en supprimant les clients sans consommations
    et en gardant seulement les meilleurs clients pour chaque nom
    """
    print("=== ÉPURATION AUTOMATIQUE DE LA BASE DE DONNÉES ===")
    
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
    
    # 2. Supprimer les clients sans consommations
    print(f"\n=== ÉTAPE 1: Suppression des clients sans consommations ===")
    
    # Clients avec montant_rembourse = 0 ET montant_reclame = 0
    clients_without_consumption = Client.objects.filter(
        montant_rembourse=0,
        montant_reclame=0
    )
    
    count_without_consumption = clients_without_consumption.count()
    print(f"Clients sans consommations trouvés: {count_without_consumption}")
    
    if count_without_consumption > 0:
        # Afficher quelques exemples
        print("Exemples de clients sans consommations:")
        for client in clients_without_consumption[:5]:
            print(f"  - {client.name} (ID: {client.id}, Pays: {client.country.name})")
        
        # Supprimer automatiquement
        with transaction.atomic():
            deleted_count = clients_without_consumption.delete()[0]
            total_deleted += deleted_count
            print(f"✅ {deleted_count} clients supprimés avec succès!")
    else:
        print("✅ Aucun client sans consommations trouvé.")
    
    # 3. Pour chaque nom avec des doublons, garder le meilleur client
    print(f"\n=== ÉTAPE 2: Sélection des meilleurs clients ===")
    
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
            clients = Client.objects.filter(name=name).order_by(
                '-nombre_assures',  # Plus grand nombre d'assurés
                '-montant_reclame',  # Plus haute consommation réclamée
                '-montant_rembourse'  # Plus haut montant remboursé
            )
            
            # Garder le premier (le meilleur) et marquer les autres pour suppression
            best_client = clients.first()
            clients_to_remove = clients.exclude(id=best_client.id)
            
            print(f"\n{name}:")
            print(f"  ✅ Gardé: {best_client.name} (ID: {best_client.id})")
            print(f"    - Assurés: {best_client.nombre_assures}")
            print(f"    - Montant réclamé: {best_client.montant_reclame}")
            print(f"    - Montant remboursé: {best_client.montant_rembourse}")
            
            for client in clients_to_remove:
                print(f"  ❌ À supprimer: {client.name} (ID: {client.id})")
                print(f"    - Assurés: {client.nombre_assures}")
                print(f"    - Montant réclamé: {client.montant_reclame}")
                print(f"    - Montant remboursé: {client.montant_rembourse}")
                clients_to_delete.append(client.id)
        
        # Supprimer automatiquement les doublons
        if clients_to_delete:
            with transaction.atomic():
                deleted_count = Client.objects.filter(id__in=clients_to_delete).delete()[0]
                total_deleted += deleted_count
                print(f"✅ {deleted_count} clients en doublon supprimés avec succès!")
    
    # 4. Résultats finaux
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
    total_insured = Client.objects.aggregate(total=Sum('nombre_assures'))['total'] or 0
    total_claimed = Client.objects.aggregate(total=Sum('montant_reclame'))['total'] or Decimal('0')
    total_reimbursed = Client.objects.aggregate(total=Sum('montant_rembourse'))['total'] or Decimal('0')
    
    print(f"Total assurés: {total_insured}")
    print(f"Total montant réclamé: {total_claimed}")
    print(f"Total montant remboursé: {total_reimbursed}")
    
    return final_count

if __name__ == "__main__":
    cleanup_database_auto()

