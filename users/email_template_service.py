"""
Service de templates d'emails avec Django templates
"""

import os
from datetime import datetime
from django.template.loader import render_to_string
from django.conf import settings
from pathlib import Path

class EmailTemplateService:
    """
    Service pour générer des emails avec des templates Django
    """
    
    @staticmethod
    def get_template_path(template_name):
        """
        Retourne le chemin vers un template d'email
        """
        return f"email/templates/{template_name}.html"
    
    @staticmethod
    def get_logo_url():
        """
        Retourne l'URL du logo de l'entreprise
        """
        # En production, utilisez l'URL de votre CDN ou serveur statique
        if settings.DEBUG:
            # En développement, utilisez une URL relative
            return f"{settings.STATIC_URL}email/images/logo.jpg"
        else:
            # En production, utilisez l'URL complète
            return f"{settings.STATIC_URL}email/images/logo.jpg"
    
    @staticmethod
    def render_credentials_email(user, password, role_display):
        """
        Génère le contenu HTML pour l'email d'identifiants
        """
        context = {
            'user': user,
            'password': password,
            'role_display': role_display,
            'logo_url': EmailTemplateService.get_logo_url(),
            'frontend_url': getattr(settings, 'FRONTEND_URL', 'https://sunudash.netlify.app'),
            'current_year': datetime.now().year,
            'header_title': 'Bienvenue sur SUNU DASH',
            'header_subtitle': 'Vos identifiants de connexion',
            'subject': 'Vos identifiants de connexion - SUNU DASH'
        }
        
        return render_to_string('email/templates/credentials_email.html', context)
    
    @staticmethod
    def render_login_success_email(user, login_info):
        """
        Génère le contenu HTML pour l'email de confirmation de connexion
        """
        context = {
            'user': user,
            'login_info': login_info,
            'logo_url': EmailTemplateService.get_logo_url(),
            'frontend_url': getattr(settings, 'FRONTEND_URL', 'https://sunudash.netlify.app'),
            'current_year': datetime.now().year,
            'header_title': 'Connexion Réussie',
            'header_subtitle': 'Bienvenue sur votre espace personnel',
            'subject': 'Connexion Réussie - SUNU DASH'
        }
        
        return render_to_string('email/templates/login_success_email.html', context)
    
    @staticmethod
    def render_password_change_email(user, change_info):
        """
        Génère le contenu HTML pour l'email de changement de mot de passe
        """
        context = {
            'user': user,
            'change_info': change_info,
            'logo_url': EmailTemplateService.get_logo_url(),
            'frontend_url': getattr(settings, 'FRONTEND_URL', 'https://sunudash.netlify.app'),
            'current_year': datetime.now().year,
            'header_title': 'Mot de passe modifié',
            'header_subtitle': 'Confirmation de sécurité',
            'subject': 'Mot de passe modifié - SUNU DASH'
        }
        
        return render_to_string('email/templates/password_change_email.html', context)
    
    @staticmethod
    def render_reset_password_email(user, otp, expire_at):
        """
        Génère le contenu HTML pour l'email de réinitialisation de mot de passe
        """
        context = {
            'user': user,
            'otp': otp,
            'expire_at': expire_at,
            'logo_url': EmailTemplateService.get_logo_url(),
            'frontend_url': getattr(settings, 'FRONTEND_URL', 'https://sunudash.netlify.app'),
            'current_year': datetime.now().year,
            'header_title': 'Réinitialisation de mot de passe',
            'header_subtitle': 'Votre code de sécurité',
            'subject': 'Réinitialisation de mot de passe - SUNU DASH'
        }
        
        return render_to_string('email/templates/reset_password_email.html', context)
    
    @staticmethod
    def render_country_assignment_email(user, country, assignment_type):
        """
        Génère le contenu HTML pour l'email d'affectation de pays
        """
        context = {
            'user': user,
            'country': country,
            'assignment_type': assignment_type,
            'logo_url': EmailTemplateService.get_logo_url(),
            'frontend_url': getattr(settings, 'FRONTEND_URL', 'https://sunudash.netlify.app'),
            'current_year': datetime.now().year,
            'header_title': 'Affectation Territoriale',
            'header_subtitle': 'Nouvelle responsabilité',
            'subject': f"{'Affectation' if assignment_type == 'assign' else 'Réaffectation'} territoriale - SUNU DASH"
        }
        
        return render_to_string('email/templates/country_assignment_email.html', context)
