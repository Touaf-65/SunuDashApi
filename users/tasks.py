"""
Tâches Celery pour l'envoi asynchrone d'emails
"""

import logging
from celery import shared_task
from django.core.mail import send_mail
from django.conf import settings
from .email_templates import (
    CREDENTIALS_TEMPLATE, LOGIN_SUCCESS_TEMPLATE, 
    PASSWORD_CHANGE_TEMPLATE, RESET_PASSWORD_TEMPLATE,
    COUNTRY_ASSIGNMENT_TEMPLATE
)

logger = logging.getLogger(__name__)

@shared_task(bind=True, max_retries=3)
def send_email_task(self, to_email, subject, plain_text, html_content=None):
    """
    Tâche Celery pour l'envoi asynchrone d'emails
    """
    try:
        send_mail(
            subject=subject,
            message=plain_text,
            from_email=settings.EMAIL_HOST_USER,
            recipient_list=[to_email],
            fail_silently=False,
            html_message=html_content,
        )
        logger.info(f"Email envoyé avec succès à {to_email}")
        return True
        
    except Exception as exc:
        logger.error(f"Erreur envoi email à {to_email}: {str(exc)}")
        # Retry avec backoff exponentiel
        raise self.retry(exc=exc, countdown=60 * (2 ** self.request.retries))

@shared_task
def send_credentials_email_task(user_data, password, role_display):
    """
    Tâche pour l'envoi d'email d'identifiants
    """
    try:
        context = {
            'first_name': user_data['first_name'],
            'last_name': user_data['last_name'],
            'email': user_data['email'],
            'username': user_data['username'],
            'password': password,
            'role': role_display,
            'frontend_url': getattr(settings, 'FRONTEND_URL', 'https://sunudash.netlify.app'),
            'current_year': 2024
        }
        
        subject = "Vos identifiants de connexion - SUNU DASH"
        plain_text = f"""
        Bonjour {user_data['first_name']} {user_data['last_name']},
        
        Votre compte SUNU DASH a été créé avec succès.
        
        Email : {user_data['email']}
        Nom d'utilisateur : {user_data['username']}
        Mot de passe : {password}
        Rôle : {role_display}
        
        Connectez-vous à : {context['frontend_url']}/auth/login
        
        SUNU DASH - Votre partenaire d'analyse d'assurance
        """
        
        html_content = CREDENTIALS_TEMPLATE.format(**context)
        
        send_email_task.delay(
            to_email=user_data['email'],
            subject=subject,
            plain_text=plain_text,
            html_content=html_content
        )
        
        logger.info(f"Tâche d'envoi d'identifiants programmée pour {user_data['email']}")
        return True
        
    except Exception as e:
        logger.error(f"Erreur programmation tâche identifiants pour {user_data['email']}: {str(e)}")
        return False

@shared_task
def send_country_assignment_email_task(user_data, country_name, assignment_type="assign"):
    """
    Tâche pour l'envoi d'email d'affectation de pays
    """
    try:
        from datetime import datetime
        
        context = {
            'first_name': user_data['first_name'],
            'last_name': user_data['last_name'],
            'country_name': country_name,
            'assignment_date': datetime.now().strftime('%d/%m/%Y à %H:%M'),
            'current_year': 2024
        }
        
        if assignment_type == "assign":
            subject = "Affectation territoriale - SUNU DASH"
            plain_text = f"""
            Bonjour {user_data['first_name']},
            
            Vous avez été désigné comme Administrateur Territorial pour le pays : {country_name}.
            
            Date d'affectation : {context['assignment_date']}
            Rôle : Administrateur Territorial
            
            SUNU DASH - Votre partenaire d'analyse d'assurance
            """
        elif assignment_type == "reassign":
            subject = "Réaffectation territoriale - SUNU DASH"
            plain_text = f"""
            Bonjour {user_data['first_name']},
            
            Vous avez été réaffecté comme Administrateur Territorial pour le pays : {country_name}.
            
            Date de réaffectation : {context['assignment_date']}
            Rôle : Administrateur Territorial
            
            SUNU DASH - Votre partenaire d'analyse d'assurance
            """
        else:  # unassign
            subject = "Désaffectation territoriale - SUNU DASH"
            plain_text = f"""
            Bonjour {user_data['first_name']},
            
            Vous avez été désaffecté en tant qu'administrateur territorial de votre pays actuel.
            
            Date de désaffectation : {context['assignment_date']}
            
            SUNU DASH - Votre partenaire d'analyse d'assurance
            """
            html_content = None
            send_email_task.delay(
                to_email=user_data['email'],
                subject=subject,
                plain_text=plain_text,
                html_content=html_content
            )
            return True
        
        html_content = COUNTRY_ASSIGNMENT_TEMPLATE.format(**context)
        
        send_email_task.delay(
            to_email=user_data['email'],
            subject=subject,
            plain_text=plain_text,
            html_content=html_content
        )
        
        logger.info(f"Tâche d'affectation territoriale programmée pour {user_data['email']}")
        return True
        
    except Exception as e:
        logger.error(f"Erreur programmation tâche affectation pour {user_data['email']}: {str(e)}")
        return False

@shared_task
def send_reset_password_email_task(user_data, otp, expire_at_str):
    """
    Tâche pour l'envoi d'email de réinitialisation de mot de passe
    """
    try:
        context = {
            'first_name': user_data['first_name'],
            'last_name': user_data['last_name'],
            'otp': otp,
            'expire_at': expire_at_str,
            'current_year': 2024
        }
        
        subject = "Réinitialisation de mot de passe - SUNU DASH"
        plain_text = f"""
        Bonjour {user_data['first_name']} {user_data['last_name']},
        
        Nous avons reçu une demande de réinitialisation de mot de passe pour votre compte SUNU DASH.
        
        Code de sécurité : {otp}
        Ce code expire le : {expire_at_str}
        
        SUNU DASH - Votre partenaire d'analyse d'assurance
        """
        
        html_content = RESET_PASSWORD_TEMPLATE.format(**context)
        
        send_email_task.delay(
            to_email=user_data['email'],
            subject=subject,
            plain_text=plain_text,
            html_content=html_content
        )
        
        logger.info(f"Tâche de réinitialisation de mot de passe programmée pour {user_data['email']}")
        return True
        
    except Exception as e:
        logger.error(f"Erreur programmation tâche réinitialisation pour {user_data['email']}: {str(e)}")
        return False


