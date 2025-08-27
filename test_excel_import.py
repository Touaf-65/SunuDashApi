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

def test_excel_import():
    """Tester l'import des primes avec le fichier Excel"""
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
    
    print("\n=== TEST DE L'IMPORT EXCEL ===")
    
    # 1. Test de la prévisualisation avec le fichier Excel
    print("\n1. Test de la prévisualisation...")
    try:
        with open('primes_clients_reels.xlsx', 'rb') as f:
            files = {'file': ('primes_clients_reels.xlsx', f, 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')}
            response = requests.post(
                f"{base_url}/data/prime-import/preview/",
                files=files,
                headers={'Authorization': f'Bearer {access_token}'}
            )
            
            if response.status_code == 200:
                data = response.json()
                print("✅ Prévisualisation réussie!")
                print(f"   - Total lignes: {data['data']['total_rows']}")
                print(f"   - Lignes valides: {data['data']['valid_rows']}")
                print(f"   - Lignes invalides: {data['data']['invalid_rows']}")
                if data['data']['clients_not_found']:
                    print(f"   - Clients non trouvés: {len(data['data']['clients_not_found'])}")
            else:
                print(f"❌ Erreur prévisualisation: {response.status_code}")
                print(f"   Réponse: {response.text}")
                
    except Exception as e:
        print(f"❌ Erreur lors de la prévisualisation: {e}")
    
    # 2. Test de l'import effectif
    print("\n2. Test de l'import effectif...")
    try:
        with open('primes_clients_reels.xlsx', 'rb') as f:
            files = {'file': ('primes_clients_reels.xlsx', f, 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')}
            response = requests.post(
                f"{base_url}/data/prime-import/",
                files=files,
                headers={'Authorization': f'Bearer {access_token}'}
            )
            
            if response.status_code == 200:
                data = response.json()
                print("✅ Import réussi!")
                print(f"   - Primes importées: {data['data']['imported_count']}")
                print(f"   - Total valide: {data['data']['total_valid']}")
                print(f"   - Total invalide: {data['data']['total_invalid']}")
            else:
                print(f"❌ Erreur import: {response.status_code}")
                print(f"   Réponse: {response.text}")
                
    except Exception as e:
        print(f"❌ Erreur lors de l'import: {e}")

if __name__ == "__main__":
    test_excel_import()

