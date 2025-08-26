#!/usr/bin/env python
"""
Script de test pour le nouveau système d'emails optimisé
"""

import os
import sys
import django
from datetime import datetime, timedelta

# Configuration Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'sunu_dash.settings')
django.setup()

from users.models import CustomUser
from countries.models import Country
from users.email_service import EmailService
from users.tasks import (
    send_credentials_email_task,
    send_country_assignment_email_task,
    send_reset_password_email_task
)

def test_email_templates():
    """Test des templates d'emails"""
    print("🧪 Test des templates d'emails...")
    
    # Créer un utilisateur de test
    user, created = CustomUser.objects.get_or_create(
        email='test@sunudash.com',
        defaults={
            'username': 'testuser',
            'first_name': 'Test',
            'last_name': 'User',
            'role': 'GLOBAL_ADMIN',
            'is_active': True
        }
    )
    
    # Créer un pays de test
    country, created = Country.objects.get_or_create(
        name='Test Country',
        defaults={'code': 'TC'}
    )
    
    print(f"✅ Utilisateur de test créé : {user.email}")
    print(f"✅ Pays de test créé : {country.name}")
    
    return user, country

def test_sync_email_service():
    """Test du service d'emails synchrone"""
    print("\n📧 Test du service d'emails synchrone...")
    
    user, country = test_email_templates()
    
    try:
        # Test envoi d'identifiants
        print("📤 Test envoi d'identifiants...")
        success = EmailService.send_credentials_email(user, "test123", "Test Role")
        print(f"✅ Envoi d'identifiants : {'Succès' if success else 'Échec'}")
        
        # Test envoi d'affectation de pays
        print("📤 Test envoi d'affectation de pays...")
        success = EmailService.send_country_assignment_email(user, country, "assign")
        print(f"✅ Envoi d'affectation : {'Succès' if success else 'Échec'}")
        
        # Test envoi de réinitialisation de mot de passe
        print("📤 Test envoi de réinitialisation...")
        otp = "123456"
        expire_at = datetime.now() + timedelta(hours=1)
        success = EmailService.send_reset_password_email(user, otp, expire_at)
        print(f"✅ Envoi de réinitialisation : {'Succès' if success else 'Échec'}")
        
    except Exception as e:
        print(f"❌ Erreur lors du test : {str(e)}")

def test_async_email_tasks():
    """Test des tâches d'emails asynchrones"""
    print("\n🚀 Test des tâches d'emails asynchrones...")
    
    user, country = test_email_templates()
    
    try:
        # Préparer les données utilisateur
        user_data = {
            'first_name': user.first_name,
            'last_name': user.last_name,
            'email': user.email,
            'username': user.username
        }
        
        # Test tâche d'envoi d'identifiants
        print("📤 Test tâche d'identifiants...")
        task = send_credentials_email_task.delay(user_data, "test123", "Test Role")
        print(f"✅ Tâche d'identifiants programmée : {task.id}")
        
        # Test tâche d'affectation de pays
        print("📤 Test tâche d'affectation...")
        task = send_country_assignment_email_task.delay(user_data, country.name, "assign")
        print(f"✅ Tâche d'affectation programmée : {task.id}")
        
        # Test tâche de réinitialisation
        print("📤 Test tâche de réinitialisation...")
        expire_at_str = (datetime.now() + timedelta(hours=1)).strftime('%d/%m/%Y à %H:%M')
        task = send_reset_password_email_task.delay(user_data, "123456", expire_at_str)
        print(f"✅ Tâche de réinitialisation programmée : {task.id}")
        
    except Exception as e:
        print(f"❌ Erreur lors du test asynchrone : {str(e)}")

def test_email_configuration():
    """Test de la configuration email"""
    print("\n⚙️ Test de la configuration email...")
    
    from django.conf import settings
    
    config_ok = True
    
    # Vérifier les paramètres SMTP
    print(f"📧 EMAIL_HOST : {settings.EMAIL_HOST}")
    print(f"📧 EMAIL_PORT : {settings.EMAIL_PORT}")
    print(f"📧 EMAIL_USE_TLS : {settings.EMAIL_USE_TLS}")
    print(f"📧 EMAIL_HOST_USER : {settings.EMAIL_HOST_USER}")
    print(f"📧 EMAIL_TIMEOUT : {getattr(settings, 'EMAIL_TIMEOUT', 'Non défini')}")
    print(f"📧 FRONTEND_URL : {getattr(settings, 'FRONTEND_URL', 'Non défini')}")
    
    # Vérifier Celery
    print(f"🔧 CELERY_BROKER_URL : {getattr(settings, 'CELERY_BROKER_URL', 'Non défini')}")
    
    if config_ok:
        print("✅ Configuration email OK")
    else:
        print("❌ Problèmes de configuration détectés")

def main():
    """Fonction principale de test"""
    print("🎯 TEST DU SYSTÈME D'EMAILS OPTIMISÉ")
    print("=" * 50)
    
    # Test de la configuration
    test_email_configuration()
    
    # Test du service synchrone
    test_sync_email_service()
    
    # Test des tâches asynchrones
    test_async_email_tasks()
    
    print("\n" + "=" * 50)
    print("🎉 Tests terminés !")
    print("\n📝 Prochaines étapes :")
    print("1. Vérifier que les emails sont bien reçus")
    print("2. Tester l'envoi asynchrone avec Celery")
    print("3. Intégrer les nouveaux services dans les vues")
    print("4. Monitorer les performances")

if __name__ == "__main__":
    main()


