"""
Service de chargement des primes clients
"""

import pandas as pd
from datetime import datetime
from decimal import Decimal
from django.db import transaction
from django.core.exceptions import ValidationError
from django.contrib.auth import get_user_model
from core.models import Client, ClientPrimeHistory
from file_handling.models import File, ImportSession
from countries.models import Country

User = get_user_model()


class PrimeLoaderService:
    """
    Service pour charger les primes clients depuis un fichier Excel
    """
    
    def __init__(self, user):
        """
        Initialise le service avec l'utilisateur connecté
        
        Args:
            user: Utilisateur connecté (pour filtrage par pays)
        """
        self.user = user
        self.user_country = self._get_user_country()
        
    def _get_user_country(self):
        """
        Récupère le pays de l'utilisateur connecté ou None pour l'admin global
        """
        # Vérifier si c'est un superuser ou admin global
        if self.user.role in ['SUPERUSER', 'ADMIN_GLOBAL']:
            return None  # Superuser et admin global peuvent accéder à tous les pays
        
        # Pour les autres utilisateurs, utiliser le pays assigné
        return self.user.country
    
    def validate_file_format(self, file_path):
        """
        Valide le format du fichier Excel ou CSV
        
        Args:
            file_path: Chemin vers le fichier Excel ou CSV
            
        Returns:
            bool: True si le format est valide
        """
        try:
            # Détecter le type de fichier par l'extension
            if file_path.endswith(('.xlsx', '.xls')):
                df = pd.read_excel(file_path)
            elif file_path.endswith('.csv'):
                df = pd.read_csv(file_path)
            else:
                raise ValidationError("Format de fichier non supporté. Utilisez .xlsx, .xls ou .csv")
            
            required_columns = ['Nom Client', 'Prime', 'Date Paiement Prime']
            
            # Vérifier les colonnes requises
            missing_columns = [col for col in required_columns if col not in df.columns]
            if missing_columns:
                raise ValidationError(f"Colonnes manquantes: {', '.join(missing_columns)}")
            
            # Vérifier que le fichier n'est pas vide
            if df.empty:
                raise ValidationError("Le fichier est vide")
                
            return True
            
        except Exception as e:
            raise ValidationError(f"Erreur lors de la lecture du fichier: {str(e)}")
    
    def parse_excel_file(self, file_path):
        """
        Parse le fichier Excel ou CSV et retourne les données validées
        
        Args:
            file_path: Chemin vers le fichier Excel ou CSV
            
        Returns:
            list: Liste des données de primes validées
        """
        # Détecter le type de fichier par l'extension
        if file_path.endswith(('.xlsx', '.xls')):
            df = pd.read_excel(file_path)
        elif file_path.endswith('.csv'):
            df = pd.read_csv(file_path)
        else:
            raise ValidationError("Format de fichier non supporté. Utilisez .xlsx, .xls ou .csv")
        
        # Nettoyer les données
        df = df.dropna(subset=['Nom Client', 'Prime'])  # Supprimer les lignes vides
        
        # Convertir les types
        df['Prime'] = pd.to_numeric(df['Prime'], errors='coerce')
        df['Date Paiement Prime'] = pd.to_datetime(df['Date Paiement Prime'], errors='coerce')
        
        # Filtrer les données invalides
        df = df[df['Prime'].notna() & df['Date Paiement Prime'].notna()]
        
        # Convertir en liste de dictionnaires
        data = []
        for _, row in df.iterrows():
            data.append({
                'client_name': str(row['Nom Client']).strip(),
                'prime': Decimal(str(row['Prime'])),
                'payment_date': row['Date Paiement Prime'].date(),
                'row_number': _ + 2  # +2 car Excel commence à 1 et on a un header
            })
        
        return data
    
    def find_client_by_name(self, client_name):
        """
        Trouve un client par nom exact dans le pays de l'utilisateur ou tous les pays pour l'admin global
        
        Args:
            client_name: Nom du client à rechercher
            
        Returns:
            Client: Client trouvé ou None
        """
        try:
            # Pour l'admin global, rechercher dans tous les pays
            if self.user_country is None:
                client = Client.objects.filter(
                    name__iexact=client_name
                ).first()
            else:
                # Pour les autres utilisateurs, filtrer par pays
                client = Client.objects.filter(
                    name__iexact=client_name,
                    country=self.user_country
                ).first()
            
            return client
        except Exception:
            return None
    
    def validate_prime_data(self, data):
        """
        Valide les données de prime avant import
        
        Args:
            data: Liste des données de primes
            
        Returns:
            dict: Résultats de validation
        """
        results = {
            'valid': [],
            'invalid': [],
            'clients_not_found': [],
            'duplicate_names': []
        }
        
        # Vérifier les doublons dans le fichier
        client_names = [item['client_name'] for item in data]
        duplicate_names = [name for name in set(client_names) if client_names.count(name) > 1]
        
        if duplicate_names:
            results['duplicate_names'] = duplicate_names
        
        # Valider chaque ligne
        for item in data:
            errors = []
            
            # Validation du nom client
            if not item['client_name'] or len(item['client_name'].strip()) == 0:
                errors.append("Nom client vide")
            
            # Validation de la prime
            if item['prime'] <= 0:
                errors.append("Prime doit être positive")
            
            # Validation de la date
            if item['payment_date'] > datetime.now().date():
                errors.append("Date de paiement ne peut pas être dans le futur")
            
            # Rechercher le client
            client = self.find_client_by_name(item['client_name'])
            if not client:
                results['clients_not_found'].append({
                    'client_name': item['client_name'],
                    'row_number': item['row_number']
                })
                continue
            
            # Vérifier les doublons de noms dans la base
            if self.user_country is None:
                # Pour l'admin global, vérifier dans tous les pays
                duplicate_clients = Client.objects.filter(
                    name__iexact=item['client_name']
                )
            else:
                # Pour les autres utilisateurs, vérifier dans leur pays
                duplicate_clients = Client.objects.filter(
                    name__iexact=item['client_name'],
                    country=self.user_country
                )
            
            if duplicate_clients.count() > 1:
                errors.append(f"Plusieurs clients trouvés avec le nom '{item['client_name']}'")
            
            if errors:
                results['invalid'].append({
                    **item,
                    'errors': errors
                })
            else:
                results['valid'].append({
                    **item,
                    'client': client
                })
        
        return results
    
    @transaction.atomic
    def import_primes(self, file_path, import_session=None):
        """
        Importe les primes depuis le fichier Excel
        
        Args:
            file_path: Chemin vers le fichier Excel
            import_session: Session d'import (optionnel)
            
        Returns:
            dict: Résultats de l'import
        """
        # Valider le format du fichier
        self.validate_file_format(file_path)
        
        # Parser le fichier
        data = self.parse_excel_file(file_path)
        
        # Valider les données
        validation_results = self.validate_prime_data(data)
        
        # Créer la session d'import si nécessaire
        if not import_session:
            import_session = ImportSession.objects.create(
                status='processing',
                started_at=datetime.now()
            )
        
        # Traiter les données valides
        imported_count = 0
        errors = []
        
        for item in validation_results['valid']:
            try:
                client = item['client']
                new_prime = item['prime']
                payment_date = item['payment_date']
                
                # Créer l'historique si la prime a changé
                if client.prime != new_prime:
                    # Sauvegarder l'ancienne prime dans l'historique
                    if client.prime:
                        ClientPrimeHistory.objects.create(
                            client=client,
                            prime=client.prime,
                            date=datetime.now()
                        )
                    
                    # Mettre à jour la prime
                    client.prime = new_prime
                    client.modification_date = datetime.now()
                    client.save()
                    
                    imported_count += 1
                else:
                    # Prime identique, pas de changement
                    pass
                    
            except Exception as e:
                errors.append({
                    'client_name': item['client_name'],
                    'row_number': item['row_number'],
                    'error': str(e)
                })
        
        # Finaliser la session d'import si elle existe
        if import_session:
            import_session.status = 'completed' if not errors else 'completed_with_errors'
            import_session.finished_at = datetime.now()
            import_session.save()
        
        return {
            'imported_count': imported_count,
            'total_valid': len(validation_results['valid']),
            'total_invalid': len(validation_results['invalid']),
            'clients_not_found': len(validation_results['clients_not_found']),
            'duplicate_names': validation_results['duplicate_names'],
            'errors': errors,
            'import_session_id': import_session.id if import_session else None
        }
    
    def get_import_preview(self, file_path):
        """
        Génère un aperçu de l'import sans effectuer les modifications
        
        Args:
            file_path: Chemin vers le fichier Excel ou CSV
            
        Returns:
            dict: Aperçu de l'import
        """
        # Valider le format du fichier
        self.validate_file_format(file_path)
        
        # Parser le fichier
        data = self.parse_excel_file(file_path)
        
        # Valider les données
        validation_results = self.validate_prime_data(data)
        
        # Préparer l'aperçu
        preview = {
            'total_rows': len(data),
            'valid_rows': len(validation_results['valid']),
            'invalid_rows': len(validation_results['invalid']),
            'clients_not_found': validation_results['clients_not_found'],
            'duplicate_names': validation_results['duplicate_names'],
            'sample_data': validation_results['valid'][:5] if validation_results['valid'] else [],
            'sample_errors': validation_results['invalid'][:5] if validation_results['invalid'] else []
        }
        
        return preview

