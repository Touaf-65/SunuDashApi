"""
Système de templates d'emails personnalisés pour SUNU DASH
"""

import os
from pathlib import Path

# Chemin vers les templates d'emails
TEMPLATES_DIR = Path(__file__).parent / 'email_templates'

class EmailTemplates:
    """
    Classe pour gérer les templates d'emails personnalisés
    """
    
    @staticmethod
    def get_template(template_name):
        """
        Récupère un template d'email par son nom
        """
        template_path = TEMPLATES_DIR / f"{template_name}.html"
        if template_path.exists():
            with open(template_path, 'r', encoding='utf-8') as f:
                return f.read()
        return None
    
    @staticmethod
    def render_template(template_name, context):
        """
        Rend un template avec les variables de contexte
        """
        template = EmailTemplates.get_template(template_name)
        if template:
            return template.format(**context)
        return None

# Templates d'emails personnalisés
CREDENTIALS_TEMPLATE = """<!DOCTYPE html>
<html lang="fr">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Vos identifiants de connexion - SUNU DASH</title>
    <style>
        body {{
            font-family: Verdana, sans-serif;
            background-color: #f4f4f4;
            margin: 0;
            padding: 20px;
        }}
        .container {{
            max-width: 600px;
            margin: auto;
            background: #ffffff;
            border-radius: 8px;
            box-shadow: 0 2px 10px rgba(0, 0, 0, 0.1);
            padding: 20px;
        }}
        .header {{
            text-align: center;
            margin-bottom: 30px;
        }}
        .header h2 {{
            color: #2d5be3;
            margin: 0;
        }}
        .credentials {{
            background-color: #f8f9fa;
            border: 1px solid #e9ecef;
            border-radius: 6px;
            padding: 20px;
            margin: 20px 0;
        }}
        .button {{
            display: inline-block;
            background-color: #2d5be3;
            color: white;
            padding: 12px 24px;
            text-decoration: none;
            border-radius: 6px;
            font-weight: bold;
        }}
        .footer {{
            background-color: #f8f9fa;
            padding: 20px;
            text-align: center;
            margin-top: 20px;
            border-radius: 6px;
        }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h2>SUNU DASH</h2>
        </div>
        
        <h1>🔑 Vos identifiants de connexion</h1>
        <p>Bienvenue {first_name} {last_name} ! Votre compte a été créé avec succès.</p>
        
        <div class="credentials">
            <p><strong>Email :</strong> {email}</p>
            <p><strong>Nom d'Utilisateur: </strong> {username}</p>
            <p><strong>Mot de passe :</strong> {password}</p>
            <p><strong>Rôle :</strong> {role}</p>
        </div>

        <div style="text-align: center; margin-block: 30px;">
            <a href="{frontend_url}/auth/login" class="button">🚀 Se connecter maintenant</a>
        </div>

        <p>Conseils pour votre première connexion :</p>
        <ul>
            <li>Copiez vos identifiants</li>
            <li>Changez votre mot de passe après la première connexion</li>
            <li>Explorez votre tableau de bord</li>
        </ul>
        
        <div class="footer">
            <p><strong>SUNU DASH</strong> - Votre partenaire d'analyse d'assurance</p>
            <p>Ce message est généré automatiquement, merci de ne pas y répondre.</p>
            <p>&copy; {current_year} SUNU DASH. Tous droits réservés.</p>
        </div>
    </div>
</body>
</html>"""

LOGIN_SUCCESS_TEMPLATE = """<!DOCTYPE html>
<html lang="fr">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Connexion Réussie - SUNU DASH</title>
    <style>
        body {{
            font-family: 'Poppins', Verdana, sans-serif;
            line-height: 1.6;
            color: #333;
            margin: 0;
            padding: 20px;
            background-color: #f4f4f4;
        }}
        .container {{
            max-width: 600px;
            margin: auto;
            background-color: #ffffff;
            border-radius: 12px;
            box-shadow: 0 4px 20px rgba(0, 0, 0, 0.1);
            padding: 20px;
        }}
        .header {{
            text-align: center;
            margin-bottom: 30px;
        }}
        .header h2 {{
            color: #2d5be3;
            margin: 0;
        }}
        .success-banner {{
            background-color: #d4edda;
            border: 1px solid #c3e6cb;
            border-radius: 6px;
            padding: 20px;
            text-align: center;
            margin: 20px 0;
        }}
        .connection-details {{
            background-color: #f8f9fa;
            border: 1px solid #e9ecef;
            border-radius: 6px;
            padding: 20px;
            margin: 20px 0;
        }}
        .connection-details table {{
            width: 100%;
        }}
        .connection-details td {{
            padding: 8px 0;
        }}
        .button {{
            display: inline-block;
            background-color: #2d5be3;
            color: white;
            padding: 12px 24px;
            text-decoration: none;
            border-radius: 6px;
            font-weight: bold;
        }}
        .footer {{
            background-color: #f8f9fa;
            padding: 20px;
            text-align: center;
            margin-top: 20px;
            border-radius: 6px;
        }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h2>SUNU DASH</h2>
        </div>
        
        <div class="content">
            <div class="success-banner">
                <h1>🎊 Connexion Réussie ! 🎊</h1>
                <p>Bienvenue sur votre espace personnel</p>
            </div>
            
            <p>Bonjour <strong>{first_name} {last_name}</strong>,</p>
            <p>Vous êtes maintenant <strong>connecté avec succès</strong> à votre compte SUNU DASH !</p>
            
            <div class="connection-details">
                <h3>Détails de votre connexion</h3>
                <table>
                    <tr>
                        <td>Date et heure :</td>
                        <td><strong>{login_time}</strong></td>
                    </tr>
                    <tr>
                        <td>Adresse IP :</td>
                        <td><strong>{ip_address}</strong></td>
                    </tr>
                    <tr>
                        <td>Navigateur :</td>
                        <td><strong>{user_agent}</strong></td>
                    </tr>
                    <tr>
                        <td>Rôle :</td>
                        <td><strong>{role}</strong></td>
                    </tr>
                </table>
            </div>

            <div style="text-align: center; margin-top: 30px;">
                <a href="{dashboard_url}" class="button">Accéder au Tableau de Bord</a>
            </div>
        </div>
        
        <div class="footer">
            <p><strong>SUNU DASH</strong> - Votre partenaire d'analyse d'assurance</p>
            <p>Cet email a été envoyé automatiquement, merci de ne pas y répondre directement.</p>
            <p>&copy; {current_year} SUNU DASH. Tous droits réservés.</p>
        </div>
    </div>
</body>
</html>"""

PASSWORD_CHANGE_TEMPLATE = """<!DOCTYPE html>
<html lang="fr">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Mot de passe modifié - SUNU DASH</title>
    <style>
        body {{
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            line-height: 1.6;
            color: #333;
            background-color: #f4f4f4;
            margin: 0;
            padding: 20px;
        }}
        .container {{
            max-width: 600px;
            margin: 0 auto;
            background-color: #ffffff;
            border-radius: 10px;
            overflow: hidden;
            box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
            padding: 20px;
        }}
        .header {{
            text-align: center;
            margin-bottom: 30px;
        }}
        .header h2 {{
            color: #2d5be3;
            margin: 0;
        }}
        .details-container {{
            background-color: #f8f9fa;
            border: 1px solid #e9ecef;
            border-radius: 6px;
            padding: 20px;
            margin: 30px 0;
        }}
        .success-title {{
            font-size: 16px;
            font-weight: bold;
            color: #155724;
        }}
        .success-message {{
            font-size: 14px;
            color: #155724;
            margin-bottom: 10px;
        }}
        .message {{
            font-size: 14px;
            margin-bottom: 30px;
            color: #555;
            line-height: 1.8;
        }}
        .detail-item {{
            margin: 10px 0;
        }}
        .detail-label {{
            font-weight: bold;
            color: #333;
        }}
        .detail-value {{
            color: #666;
        }}
        .button {{
            display: inline-block;
            background-color: #2d5be3;
            color: white;
            padding: 12px 24px;
            text-decoration: none;
            border-radius: 6px;
            font-weight: bold;
        }}
        .footer {{
            background-color: #f8f9fa;
            padding: 20px;
            text-align: center;
            margin-top: 20px;
            border-radius: 6px;
        }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h2>SUNU DASH</h2>
        </div>
        
        <h1>Mot de passe modifié</h1>
        <p>Confirmation de sécurité</p>
        
        <div class="content">
            <div class="greeting">
                Bonjour {first_name} {last_name},
            </div>
            
            <div class="message">
                Nous confirmons que votre mot de passe a été modifié avec succès. 
                Cette action a été effectuée pour votre compte SUNU DASH.
            </div>
            
            <div class="details-container">
                <div class="success-title">Mot de passe mis à jour</div>
                <div class="success-message">
                    Votre nouveau mot de passe est maintenant actif
                </div>
                
                <div class="detail-item">
                    <span class="detail-label">Compte :</span>
                    <span class="detail-value">{email}</span>
                </div>
                <div class="detail-item">
                    <span class="detail-label">Date de modification :</span>
                    <span class="detail-value">{changed_at}</span>
                </div>
                <div class="detail-item">
                    <span class="detail-label">Adresse IP :</span>
                    <span class="detail-value">{ip_address}</span>
                </div>
            </div>
            
            <div style="text-align: center; margin-top: 30px; margin-bottom: 30px;">
                <a href="{frontend_url}/login" class="button">
                    Se connecter maintenant
                </a>
            </div>
        </div>
        
        <div class="footer">
            <p>© {current_year} SUNU DASH. Tous droits réservés.</p>
            <div class="contact-info">
                Besoin d'aide ? Contactez-nous à <a href="mailto:support@sunudash.com">support@sunudash.com</a>
            </div>
        </div>
    </div>
</body>
</html>"""

RESET_PASSWORD_TEMPLATE = """<!DOCTYPE html>
<html lang="fr">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Réinitialisation de mot de passe - SUNU DASH</title>
    <style>
        body {{
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            line-height: 1.6;
            color: #333;
            background-color: #f4f4f4;
            margin: 0;
            padding: 20px;
        }}
        .container {{
            max-width: 600px;
            margin: 0 auto;
            background-color: #ffffff;
            border-radius: 10px;
            overflow: hidden;
            box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
            padding: 20px;
        }}
        .header {{
            text-align: center;
            margin-bottom: 30px;
        }}
        .header h2 {{
            color: #2d5be3;
            margin: 0;
        }}
        .otp-container {{
            background-color: #f8f9fa;
            border: 2px solid #e9ecef;
            border-radius: 8px;
            padding: 25px;
            text-align: center;
            margin: 30px 0;
        }}
        .otp-code {{
            font-size: 32px;
            font-weight: bold;
            color: #2c3e50;
            letter-spacing: 8px;
            background-color: white;
            padding: 15px 25px;
            border-radius: 6px;
            border: 2px solid #dee2e6;
            display: inline-block;
            margin: 10px 0;
        }}
        .expiry-info {{
            font-size: 14px;
            color: #666;
            margin-top: 10px;
        }}
        .footer {{
            background-color: #f8f9fa;
            padding: 20px;
            text-align: center;
            margin-top: 20px;
            border-radius: 6px;
        }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h2>SUNU DASH</h2>
        </div>
        
        <h1>Réinitialisation de mot de passe</h1>
        <p>Votre code de sécurité</p>
        
        <div class="content">
            <div class="greeting">
                Bonjour {first_name} {last_name},
            </div>
            
            <div class="message">
                Nous avons reçu une demande de réinitialisation de mot de passe pour votre compte SUNU DASH. 
                Pour continuer, veuillez utiliser le code de sécurité ci-dessous.
            </div>
            
            <div class="otp-container">
                <div class="otp-label">Code de sécurité</div>
                <div class="otp-code">{otp}</div>
                <div class="expiry-info">
                    Ce code expire le {expire_at}
                </div>
            </div>
        </div>
        
        <div class="footer">
            <p>© {current_year} SUNU DASH. Tous droits réservés.</p>
            <div class="contact-info">
                Besoin d'aide ? Contactez-nous à <a href="mailto:support@sunudash.com">support@sunudash.com</a>
            </div>
        </div>
    </div>
</body>
</html>"""

COUNTRY_ASSIGNMENT_TEMPLATE = """<!DOCTYPE html>
<html lang="fr">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Affectation territoriale - SUNU DASH</title>
    <style>
        body {{
            font-family: Arial, sans-serif;
            padding: 32px;
            background-color: #f9f9f9;
            margin: 0;
        }}
        .container {{
            max-width: 480px;
            margin: auto;
            background: #fff;
            padding: 32px;
            border-radius: 8px;
            box-shadow: 0 2px 6px rgba(0,0,0,0.1);
        }}
        .header h2 {{
            color: #2d5be3;
            margin-bottom: 12px;
        }}
        .assignment-info {{
            background-color: #f8f9fa;
            border: 1px solid #e9ecef;
            border-radius: 6px;
            padding: 20px;
            margin: 20px 0;
        }}
        .footer {{
            font-size: 13px;
            color: #888;
            margin-top: 20px;
            padding-top: 20px;
            border-top: 1px solid #eee;
        }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h2>Nouvelle affectation</h2>
        </div>
        <p>Bonjour <strong>{first_name}</strong>,</p>
        <p>Vous avez été désigné comme <strong>Administrateur Territorial</strong> pour le pays : <strong style='color:#2d5be3;'>{country_name}</strong>.</p>
        
        <div class="assignment-info">
            <p><strong>Pays assigné :</strong> {country_name}</p>
            <p><strong>Date d'affectation :</strong> {assignment_date}</p>
            <p><strong>Rôle :</strong> Administrateur Territorial</p>
        </div>
        
        <p>Connectez-vous à votre tableau de bord pour accéder à vos nouvelles responsabilités.</p>
        
        <div class="footer">
            <p>Ceci est un message automatique de SUNU DASH.</p>
            <p>&copy; {current_year} SUNU DASH. Tous droits réservés.</p>
        </div>
    </div>
</body>
</html>"""
