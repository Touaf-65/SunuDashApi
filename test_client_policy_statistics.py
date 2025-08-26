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

def test_client_policy_statistics():
    """Tester les nouvelles vues API des statistiques des polices d'un client"""
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
    
    print("\n=== TEST DES STATISTIQUES DES POLICES D'UN CLIENT ===")
    
    # 1. Test des statistiques de toutes les polices du client
    print("\n1. Test des statistiques de toutes les polices du client...")
    try:
        response = requests.post(
            f"{base_url}/dashboard/clients/{client.id}/policies/statistics/",
            json={
                'date_start': start_date.strftime('%Y-%m-%d'),
                'date_end': end_date.strftime('%Y-%m-%d')
            },
            headers=headers
        )
        
        if response.status_code == 200:
            data = response.json()
            print("✅ Statistiques des polices récupérées avec succès!")
            print(f"   - Nom du client: {data.get('client_name', 'N/A')}")
            print(f"   - Granularité: {data.get('granularity', 'N/A')}")
            print(f"   - Nombre de polices: {len(data.get('policies_table', []))}")
            print(f"   - Répartition par rôle: {data.get('role_consumption_share', [])}")
            
            if 'consistency_warning' in data:
                print(f"   ⚠️  Avertissement de cohérence: {data['consistency_warning']['message']}")
        else:
            print(f"❌ Erreur: {response.status_code}")
            print(f"   Réponse: {response.text}")
            
    except Exception as e:
        print(f"❌ Erreur lors du test: {e}")
    
    # 2. Test des statistiques d'une police spécifique
    print("\n2. Test des statistiques d'une police spécifique...")
    try:
        response = requests.post(
            f"{base_url}/dashboard/clients/{client.id}/policies/{policy.id}/statistics/",
            json={
                'date_start': start_date.strftime('%Y-%m-%d'),
                'date_end': end_date.strftime('%Y-%m-%d')
            },
            headers=headers
        )
        
        if response.status_code == 200:
            data = response.json()
            print("✅ Statistiques de la police récupérées avec succès!")
            print(f"   - Numéro de police: {data.get('policy_number', 'N/A')}")
            print(f"   - Granularité: {data.get('granularity', 'N/A')}")
            print(f"   - Consommation actuelle: {data.get('actual_consumption_value', 'N/A')}")
            print(f"   - Nombre d'assurés primaires: {data.get('actual_nb_primary_value', 'N/A')}")
            print(f"   - Nombre total d'assurés: {data.get('actual_nb_total_value', 'N/A')}")
            
            # Afficher quelques séries temporelles
            consumption_series = data.get('consumption_series', [])
            if consumption_series:
                print(f"   - Points de données de consommation: {len(consumption_series)}")
        else:
            print(f"❌ Erreur: {response.status_code}")
            print(f"   Réponse: {response.text}")
            
    except Exception as e:
        print(f"❌ Erreur lors du test: {e}")
    
    print("\n=== FIN DES TESTS ===")

if __name__ == "__main__":
    test_client_policy_statistics()
