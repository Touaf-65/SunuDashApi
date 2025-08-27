#!/usr/bin/env python
import os
import sys
import django

# Configuration Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'sunu_dash.settings')
django.setup()

from core.models import Client, Policy
from dashboard.services.insured_statistics import PolicyInsuredStatisticsService, PolicyInsuredListService
from datetime import datetime, timedelta

def test_services():
    """Test simple des nouveaux services"""
    print("=== TEST DES NOUVEAUX SERVICES DES ASSURÉS D'UNE POLICE ===")
    
    # Obtenir un client avec des polices
    client = Client.objects.prefetch_related('policies').first()
    if not client:
        print("❌ Aucun client trouvé dans la base de données!")
        return
    
    print(f"✅ Client sélectionné: {client.name} (ID: {client.id})")
    
    # Obtenir une police du client
    policy = client.policies.first()
    if not policy:
        print("❌ Aucune police trouvée pour ce client!")
        return
    
    print(f"✅ Police sélectionnée: {policy.policy_number} (ID: {policy.id})")
    
    # Définir la période de test (derniers 6 mois)
    end_date = datetime.now().date()
    start_date = end_date - timedelta(days=180)
    
    print(f"📅 Période de test: {start_date} à {end_date}")
    
    try:
        # Test du service de statistiques
        print("\n🔍 Test du service PolicyInsuredStatisticsService...")
        stats_service = PolicyInsuredStatisticsService(policy.id, start_date.strftime('%Y-%m-%d'), end_date.strftime('%Y-%m-%d'))
        stats = stats_service.get_complete_statistics()
        
        if stats:
            print("✅ Statistiques récupérées avec succès!")
            print(f"   - Numéro de police: {stats.get('policy', {}).get('policy_number', 'N/A')}")
            print(f"   - Nombre total d'assurés: {stats.get('total_insured_count', 'N/A')}")
            print(f"   - Répartition par rôle: {stats.get('insured_role_distribution', {})}")
        else:
            print("⚠️ Aucune statistique retournée")
            
    except Exception as e:
        print(f"❌ Erreur avec PolicyInsuredStatisticsService: {e}")
    
    try:
        # Test du service de liste
        print("\n🔍 Test du service PolicyInsuredListService...")
        list_service = PolicyInsuredListService(policy.id, start_date.strftime('%Y-%m-%d'), end_date.strftime('%Y-%m-%d'))
        insured_list = list_service.get_complete_insureds_list()
        
        if insured_list:
            print("✅ Liste des assurés récupérée avec succès!")
            print(f"   - Nombre d'assurés: {insured_list.get('summary_statistics', {}).get('total_insured_count', 'N/A')}")
            print(f"   - Répartition par rôle: {insured_list.get('summary_statistics', {}).get('role_distribution', {})}")
        else:
            print("⚠️ Aucune liste retournée")
            
    except Exception as e:
        print(f"❌ Erreur avec PolicyInsuredListService: {e}")
    
    print("\n=== FIN DES TESTS ===")

if __name__ == "__main__":
    test_services()
