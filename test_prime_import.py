#!/usr/bin/env python
import os
import sys
import django
import requests
import json

# Configuration Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'sunu_dash.settings')
django.setup()

from django.contrib.auth import get_user_model
from rest_framework_simplejwt.tokens import RefreshToken

User = get_user_model()

def get_auth_token():
    """Obtenir un token d'authentification pour un utilisateur existant"""
    # Récupérer le premier utilisateur admin
    user = User.objects.filter(role__in=['SUPERUSER', 'ADMIN_GLOBAL', 'ADMIN_TERRITORIAL']).first()
    if not user:
        print("Aucun utilisateur admin trouvé!")
        return None
    
    print(f"Utilisateur connecté: {user.username} ({user.email}) - Rôle: {user.role}")
    
    # Générer le token
    refresh = RefreshToken.for_user(user)
    access_token = str(refresh.access_token)
    
    return access_token

def test_prime_import():
    """Tester l'import des primes"""
    base_url = "http://127.0.0.1:8000"
    
    # Obtenir le token d'authentification
    token = get_auth_token()
    if not token:
        return
    
    headers = {
        'Authorization': f'Bearer {token}',
        'Content-Type': 'application/json'
    }
    
    print("\n=== TEST DE L'IMPORT DES PRIMES ===")
    
    # 1. Test de la prévisualisation
    print("\n1. Test de la prévisualisation...")
    try:
        with open('test_import_primes.xlsx', 'rb') as f:
            files = {'file': f}
            response = requests.post(
                f"{base_url}/data/prime-import/preview/",
                files=files,
                headers={'Authorization': f'Bearer {token}'}
            )
            
            if response.status_code == 200:
                data = response.json()
                print("✅ Prévisualisation réussie!")
                print(f"   - Total lignes: {data['data']['total_rows']}")
                print(f"   - Lignes valides: {data['data']['valid_rows']}")
                print(f"   - Lignes invalides: {data['data']['invalid_rows']}")
                if data['data']['clients_not_found']:
                    print(f"   - Clients non trouvés: {len(data['data']['clients_not_found'])}")
                if data['data']['duplicate_names']:
                    print(f"   - Noms en doublon: {data['data']['duplicate_names']}")
            else:
                print(f"❌ Erreur prévisualisation: {response.status_code}")
                print(f"   Réponse: {response.text}")
                
    except Exception as e:
        print(f"❌ Erreur lors de la prévisualisation: {e}")
    
    # 2. Test de l'import effectif
    print("\n2. Test de l'import effectif...")
    try:
        with open('test_import_primes.xlsx', 'rb') as f:
            files = {'file': f}
            response = requests.post(
                f"{base_url}/data/prime-import/",
                files=files,
                headers={'Authorization': f'Bearer {token}'}
            )
            
            if response.status_code == 200:
                data = response.json()
                print("✅ Import réussi!")
                print(f"   - Primes importées: {data['data']['imported_count']}")
                print(f"   - Total valide: {data['data']['total_valid']}")
                print(f"   - Total invalide: {data['data']['total_invalid']}")
                print(f"   - Clients non trouvés: {data['data']['clients_not_found']}")
                if data['data']['errors']:
                    print(f"   - Erreurs: {len(data['data']['errors'])}")
            else:
                print(f"❌ Erreur import: {response.status_code}")
                print(f"   Réponse: {response.text}")
                
    except Exception as e:
        print(f"❌ Erreur lors de l'import: {e}")
    
    # 3. Vérifier les primes après import
    print("\n3. Vérification des primes après import...")
    try:
        response = requests.get(
            f"{base_url}/data/prime-import/clients/",
            headers=headers
        )
        
        if response.status_code == 200:
            data = response.json()
            print("✅ Liste des clients récupérée!")
            print("   Primes mises à jour:")
            for client in data['data'][:5]:  # Afficher les 5 premiers
                print(f"   - {client['name']}: {client['prime']}")
        else:
            print(f"❌ Erreur récupération clients: {response.status_code}")
            
    except Exception as e:
        print(f"❌ Erreur lors de la vérification: {e}")

if __name__ == "__main__":
    test_prime_import()
