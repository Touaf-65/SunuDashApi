#!/usr/bin/env python
import os
import sys
import django
import requests
import json
from datetime import datetime, timedelta

# Configuration Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'sunu_dash.settings')
django.setup()

from django.contrib.auth import get_user_model
from rest_framework_simplejwt.tokens import RefreshToken
from core.models import Client, Policy

User = get_user_model()

def test_policy_insured_services():
    """Tester les nouveaux services des statistiques des assurés d'une police"""
    base_url = "http://127.0.0.1:8000"
    
    # Obtenir un utilisateur admin
    user = User.objects.filter(role__in=['SUPERUSER', 'ADMIN_GLOBAL']).first()
    if not user:
        print("Aucun utilisateur admin trouvé!")
        return
    
    print(f"Utilisateur connecté: {user.username} ({user.email}) - Rôle: {user.role}")
    
    # Générer le token
    refresh = RefreshToken.for_user(user)
    access_token = str(refresh.access_token)
    
    # Obtenir un client avec des polices
    client = Client.objects.prefetch_related('policies').first()
    if not client:
        print("Aucun client trouvé dans la base de données!")
        return
    
    print(f"\nClient sélectionné: {client.name} (ID: {client.id})")
    
    # Obtenir une police du client
    policy = client.policies.first()
    if not policy:
        print("Aucune police trouvée pour ce client!")
        return
    
    print(f"Police sélectionnée: {policy.policy_number} (ID: {policy.id})")
    
    # Définir la période de test (derniers 6 mois)
    end_date = datetime.now().date()
    start_date = end_date - timedelta(days=180)
    
    print(f"\nPériode de test: {start_date} à {end_date}")
    
    headers = {'Authorization': f'Bearer {access_token}'}
    
    print("\n=== TEST DES NOUVEAUX SERVICES DES ASSURÉS D'UNE POLICE ===")
    
    # 1. Test des statistiques des assurés d'une police
    print("\n1. Test des statistiques des assurés d'une police...")
    try:
        response = requests.post(
            f"{base_url}/dashboard/policies/{policy.id}/insureds/statistics/",
            json={
                'date_start': start_date.strftime('%Y-%m-%d'),
                'date_end': end_date.strftime('%Y-%m-%d')
            },
            headers=headers
        )
        
        if response.status_code == 200:
            data = response.json()
            print("✅ Statistiques des assurés de la police récupérées avec succès!")
            print(f"   - Numéro de police: {data.get('policy', {}).get('policy_number', 'N/A')}")
            print(f"   - Nom du client: {data.get('policy', {}).get('client_name', 'N/A')}")
            print(f"   - Nombre total d'assurés: {data.get('total_insured_count', 'N/A')}")
            print(f"   - Répartition par rôle: {data.get('insured_role_distribution', {})}")
            print(f"   - Consommation totale: {data.get('total_consumption', 'N/A')}")
            print(f"   - Ratio S/P: {data.get('sp_ratio', 'N/A')}%")
            
            # Afficher le classement des assurés
            top_insureds = data.get('top_insureds_consumption_ranking', [])
            if top_insureds:
                print(f"   - Top assurés consommateurs: {len(top_insureds)} assurés")
                for i, insured in enumerate(top_insureds[:3]):
                    print(f"     {i+1}. {insured.get('insured_name', 'N/A')} ({insured.get('role', 'N/A')}) - {insured.get('total_consumption', 0)}")
        else:
            print(f"❌ Erreur: {response.status_code}")
            print(f"   Réponse: {response.text}")
            
    except Exception as e:
        print(f"❌ Erreur lors du test: {e}")
    
    # 2. Test de la liste des assurés d'une police
    print("\n2. Test de la liste des assurés d'une police...")
    try:
        response = requests.post(
            f"{base_url}/dashboard/policies/{policy.id}/insureds/list/",
            json={
                'date_start': start_date.strftime('%Y-%m-%d'),
                'date_end': end_date.strftime('%Y-%m-%d')
            },
            headers=headers
        )
        
        if response.status_code == 200:
            data = response.json()
            print("✅ Liste des assurés de la police récupérée avec succès!")
            print(f"   - Nombre d'assurés: {data.get('summary_statistics', {}).get('total_insured_count', 'N/A')}")
            print(f"   - Consommation totale: {data.get('summary_statistics', {}).get('total_consumption', 'N/A')}")
            print(f"   - Répartition par rôle: {data.get('summary_statistics', {}).get('role_distribution', {})}")
            
            # Afficher quelques assurés
            insureds_list = data.get('insureds_list', [])
            if insureds_list:
                print(f"   - Détails des assurés: {len(insureds_list)} assurés")
                for i, insured in enumerate(insureds_list[:3]):
                    print(f"     {i+1}. {insured.get('insured_name', 'N/A')} - {insured.get('role', 'N/A')} - Consommation: {insured.get('total_consumption', 0)}")
        else:
            print(f"❌ Erreur: {response.status_code}")
            print(f"   Réponse: {response.text}")
            
    except Exception as e:
        print(f"❌ Erreur lors du test: {e}")
    
    print("\n=== FIN DES TESTS ===")

if __name__ == "__main__":
    test_policy_insured_services()
