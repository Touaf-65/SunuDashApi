import pandas as pd

from core.models import (
    Client, Policy, Insured, Invoice, Partner, 
    PaymentMethod, Operator, Claim, Act, ActFamily, ActCategory
)
from users.models import Country
from datetime import datetime
from django.utils.timezone import make_aware, is_naive
from rest_framework.response import Response
from rest_framework import status
# from .logging_service import ImportLoggerService
from importer.services.logging_service import ImportLoggerService

class DataMapper:
    def __init__(self, df_stat, import_session):
        """
        Initialize a DataMapper object.

        Args:
            df_stat (pandas.DataFrame): Dataframe containing the stat data
            import_session (File): The import session object associated
                with this data mapper.
        """
        self.df_stat = df_stat
        self.import_session = import_session
        self.country = import_session.country
        self.file = import_session.stat_file 
        self.user = import_session.user
        
        # Initialisation du logger
        self.logger_service = ImportLoggerService(import_session.id)
        
        # Lists pour tracking
        self.logs = []
        self.orphan_claims = []
        self.errors = []

    def map_data(self):
        """
        Map the data from the stat file to the database avec logging détaillé.
        """
        try:
            self.logger_service.log_step_start("DÉBUT DU MAPPING DES DONNÉES")
            self.logger_service.log_info("Initialisation du mapping", {
                "session_id": self.import_session.id,
                "nombre_lignes": len(self.df_stat),
                "utilisateur": self.user.username if hasattr(self.user, 'username') else str(self.user),
                "pays": self.country.name if hasattr(self.country, 'name') else str(self.country)
            })
            
            df = self.df_stat.copy()
            insured_dict = {}
            
            # Compteurs
            insured_created = 0
            claims_created = 0
            total_claimed = 0
            total_reimbursed = 0

            # Nettoyage des données
            self.logger_service.log_step_start("Nettoyage des données", 1)
            original_rows = len(df)
            original_cols = len(df.columns)
            
            df = df.dropna(how='all', axis=1)
            df = df.dropna(how='all', axis=0)
            
            cleaned_rows = len(df)
            cleaned_cols = len(df.columns)
            
            self.logger_service.log_step_end("Nettoyage des données", True, {
                "lignes_supprimées": original_rows - cleaned_rows,
                "colonnes_supprimées": original_cols - cleaned_cols,
                "lignes_restantes": cleaned_rows
            })

            # ÉTAPE 1: Création des objets de base
            self.logger_service.log_step_start("Création des objets de base (catégories, familles, actes, etc.)", 2)
            step1_errors = 0
            
            for index, row in df.iterrows():
                try:
                    self.logger_service.log_info(f"Traitement ligne {index}", {
                        "beneficiary_name": row.get("beneficiary_name", "N/A"),
                        "act_category": row.get("act_category", "N/A"),
                        "act_family": row.get("act_family", "N/A")
                    })

                    cat = self.get_or_create_category(row["act_category"])
                    fam = self.get_or_create_family(row["act_family"], cat)
                    act = self.get_or_create_act(row["act_name"], fam)
                    partner = self.get_or_create_partner(row["partner_name"], row["partner_country"])
                    payment_method = self.get_or_create_payment_method(row["payment_method"], row["payment_date"], partner)
                    operator = self.get_or_create_operator(row["modified_by"])
                    client = self.get_or_create_client(row["employer_name"])
                    policy = self.get_or_create_policy(row["policy_number"], client)

                    self.logger_service.log_info(f"✅ Ligne {index} traitée avec succès", {
                        "category": cat.label,
                        "family": fam.label,
                        "act": act.label,
                        "partner": partner.name,
                        "client": client.name,
                        "policy": policy.policy_number
                    })

                except Exception as e:
                    step1_errors += 1
                    self.logger_service.log_error(
                        f"Erreur lors du traitement des objets de base",
                        details={
                            "beneficiary_name": row.get("beneficiary_name", "N/A"),
                            "act_category": row.get("act_category", "N/A"),
                            "partner_name": row.get("partner_name", "N/A")
                        },
                        line_index=index,
                        exception=e
                    )
                    self.errors.append(f"[ÉTAPE 1 - ligne {index}] {str(e)}")

            self.logger_service.log_step_end("Création des objets de base", step1_errors == 0, {
                "erreurs": step1_errors,
                "lignes_traitées": len(df)
            })

            # ÉTAPE 2: Création des assurés principaux
            self.logger_service.log_step_start("Création des assurés principaux", 3)
            df_primary = df[df["insured_status"].str.upper() == "A"]
            step2_errors = 0
            
            for index, row in df_primary.iterrows():
                try:
                    name = row["beneficiary_name"]
                    insured = self.get_or_create_primary_insured(name, row["insured_status"])
                    
                    if insured:
                        insured_dict[name.strip()] = insured
                        insured_created += 1
                        self.logger_service.log_info(f"✅ Assuré principal créé: {insured.name}", {
                            "ligne": index,
                            "status": row["insured_status"]
                        })
                    else:
                        self.logger_service.log_warning(f"Assuré principal non créé", {
                            "nom": name,
                            "status": row["insured_status"]
                        }, line_index=index)

                except Exception as e:
                    step2_errors += 1
                    self.logger_service.log_error(
                        f"Erreur création assuré principal",
                        details={"nom": row.get('beneficiary_name', 'N/A')},
                        line_index=index,
                        exception=e
                    )
                    self.errors.append(f"[ÉTAPE 2 - ligne {index}] {str(e)}")

            self.logger_service.log_step_end("Création des assurés principaux", step2_errors == 0, {
                "erreurs": step2_errors,
                "assurés_créés": insured_created,
                "lignes_traitées": len(df_primary)
            })

            # ÉTAPE 3: Création des assurés dépendants
            self.logger_service.log_step_start("Création des assurés dépendants", 4)
            df_dependents = df[df["insured_status"].str.upper().isin(["C", "E"])]
            step3_errors = 0
            
            for index, row in df_dependents.iterrows():
                try:
                    name_primary = row["main_insured"]
                    if name_primary not in insured_dict:
                        self.logger_service.log_warning(
                            f"Assuré principal manquant, création automatique",
                            details={
                                "nom_principal": name_primary,
                                "dépendant": row["beneficiary_name"]
                            },
                            line_index=index
                        )
                        
                        primary_insured = self.get_or_create_primary_insured(name_primary, "A")
                        if primary_insured:
                            insured_dict[name_primary.strip()] = primary_insured
                            insured_created += 1

                    name = row["beneficiary_name"]
                    statut = row["insured_status"]
                    principal_name = row["main_insured"]
                    insured = self.get_or_create_dependent_insured(name, statut, principal_name, insured_dict)
                    
                    if insured:
                        insured_dict[name.strip()] = insured
                        insured_created += 1
                        self.logger_service.log_info(f"✅ Assuré dépendant créé: {insured.name}", {
                            "ligne": index,
                            "status": statut,
                            "principal": principal_name
                        })

                except Exception as e:
                    step3_errors += 1
                    self.logger_service.log_error(
                        f"Erreur création assuré dépendant",
                        details={
                            "nom": row.get('beneficiary_name', 'N/A'),
                            "principal": row.get('main_insured', 'N/A')
                        },
                        line_index=index,
                        exception=e
                    )
                    self.errors.append(f"[ÉTAPE 3 - ligne {index}] {str(e)}")

            self.logger_service.log_step_end("Création des assurés dépendants", step3_errors == 0, {
                "erreurs": step3_errors,
                "dépendants_créés": insured_created - len(df_primary),
                "lignes_traitées": len(df_dependents)
            })

            # ÉTAPE 4: Création des sinistres et factures
            self.logger_service.log_step_start("Création des sinistres et factures", 5)
            step4_errors = 0
            
            for index, row in df.iterrows():
                try:
                    name = row["beneficiary_name"].strip()
                    insured = insured_dict.get(name)
                    
                    if not insured:
                        self.logger_service.log_error(
                            f"Assuré introuvable pour le sinistre",
                            details={
                                "nom_recherché": name,
                                "claim_id": row.get("claim_id", "N/A"),
                                "assurés_disponibles": list(insured_dict.keys())[:5]  # Limite à 5 pour lisibilité
                            },
                            line_index=index
                        )
                        raise Exception(f"Aucun assuré trouvé pour '{name}'")

                    # Création des objets liés
                    provider = self.get_or_create_partner(row["partner_name"], row["partner_country"])
                    invoice = self.get_or_create_invoice(
                        row["invoice_number"], 
                        row["amount_claimed"], 
                        row["amount_reimbursed"], 
                        provider, 
                        insured
                    )

                    cat = self.get_or_create_category(row["act_category"])
                    fam = self.get_or_create_family(row["act_family"], cat)
                    act = self.get_or_create_act(row["act_name"], fam)
                    operator = self.get_or_create_operator(row["modified_by"])
                    client = self.get_or_create_client(row["employer_name"])
                    policy = self.get_or_create_policy(row["policy_number"], client)

                    claim = self.get_or_create_claim(
                        claim_id=row["claim_id"],
                        status=row["claim_status"],
                        date_claim=row["payment_date"],
                        settlement_date=row["incident_date"],
                        invoice=invoice,
                        act=act,
                        operator=operator,
                        insured=insured,
                        partner=provider,
                        policy=policy,
                    )
                    
                    if claim:
                        claims_created += 1
                        total_claimed += row["amount_claimed"] or 0
                        total_reimbursed += row["amount_reimbursed"] or 0
                        
                        self.logger_service.log_info(f"✅ Sinistre créé: {claim.id}", {
                            "ligne": index,
                            "assuré": insured.name,
                            "montant_réclamé": row["amount_claimed"],
                            "montant_remboursé": row["amount_reimbursed"]
                        })

                except Exception as e:
                    step4_errors += 1
                    self.logger_service.log_error(
                        f"Erreur création sinistre/facture",
                        details={
                            "claim_id": row.get("claim_id", "N/A"),
                            "beneficiary_name": row.get("beneficiary_name", "N/A"),
                            "invoice_number": row.get("invoice_number", "N/A")
                        },
                        line_index=index,
                        exception=e
                    )
                    self.errors.append(f"[ÉTAPE 4 - ligne {index}] {str(e)}")

            self.logger_service.log_step_end("Création des sinistres et factures", step4_errors == 0, {
                "erreurs": step4_errors,
                "sinistres_créés": claims_created,
                "total_réclamé": total_claimed,
                "total_remboursé": total_reimbursed
            })

            # Mise à jour de la session d'import
            self.import_session.insured_created_count = insured_created
            self.import_session.claims_created_count = claims_created
            self.import_session.total_claimed_amount = total_claimed
            self.import_session.total_reimbursed_amount = total_reimbursed
            self.import_session.save()

            # Résumé final
            self.logger_service.log_step_start("RÉSUMÉ FINAL DE L'IMPORT")
            self.logger_service.log_info("Import terminé", {
                "session_id": self.import_session.id,
                "assurés_créés": insured_created,
                "sinistres_créés": claims_created,
                "total_réclamé": total_claimed,
                "total_remboursé": total_reimbursed,
                "erreurs_totales": len(self.errors),
                "fichier_log": self.logger_service.get_log_file_path()
            })

            if self.errors:
                self.logger_service.log_warning(f"Import terminé avec {len(self.errors)} erreurs", {
                    "liste_erreurs": self.errors
                })
                
        except Exception as e:
            self.logger_service.log_critical("Erreur critique durant le mapping", exception=e)
            raise
        finally:
            # Sauvegarde du chemin du fichier de log dans la session
            self.import_session.log_file_path = self.logger_service.get_log_file_path()
            self.import_session.save()
            self.logger_service.close()




    @staticmethod
    def get_or_create_category(label):
        """
        Retrieves or creates an ActCategory object based on the given label.
        
        The label is stripped and uppercased before being used in the get_or_create call.
        If the label is not a string, it is replaced with a single space.
        """
        
        if isinstance(label, str):
            label = label.strip()
        else:
            label = " "
        return ActCategory.objects.get_or_create(label=label.strip().upper())[0]


    @staticmethod
    def get_or_create_family(label, category):
        """
        Retrieves or creates an ActFamily object based on the given label and category.
        
        The label is stripped and uppercased before being used in the get_or_create call.
        If the label is not a string, it is replaced with a single space.
        """
        
        if isinstance(label, str):
            label = label.strip()
        else:
            label = " "
        return ActFamily.objects.get_or_create(label=label.strip().upper(), category=category)[0]

    @staticmethod
    def get_or_create_act(label, family):
        """
        Retrieves or creates an Act object based on the given label, family, and category.

        The label is cleaned up by stripping and uppercasing it before being used to search or create the Act object.

        Args:
            label (str): The act's label.
            family (ActFamily): The act's family.
            category (ActCategory): The act's category.

        Returns:
            Act: The retrieved or created Act object.
        """
        if isinstance(label, str):
            label = label.strip().upper()
        else:
            label = " "
        return Act.objects.get_or_create(label=label.strip().upper(), family=family)[0]


    def get_or_create_partner(self, name, country_name):                
        """
        Retrieves or creates a Partner object based on the given name, country name, and user.

        Attempts to find a country matching the provided country name, or uses the user's country if no match is found.
        If no country can be found, a ValueError is raised.

        Args:
            name (str): The partner's name.
            country_name (str): The country name associated with the partner.
            user (User): The user associated with the partner.

        Returns:
            Partner: The retrieved or created Partner object.
        """
        if isinstance(country_name, str):
            country_name = country_name.strip()
        else:
            country_name = None

        country = Country.objects.filter(name__iexact=country_name).first()
        if not country:
            country = self.user.country

        if not country:
            raise ValueError(
                f"Impossible de déterminer le pays pour le partenaire '{name}'. "
                f"Ni '{country_name}' ni le pays de l'utilisateur ({getattr(user, 'username', user)}) n'existent."
            )

        return Partner.objects.get_or_create(name=name.strip().upper(), country=country)[0]
    
    @staticmethod
    def get_or_create_payment_method(number, date, provider):            
        """
        Retrieves or creates a PaymentMethod object based on the given payment number, date, and provider.

        This method attempts to parse the provided date string or object into an aware datetime object.
        Supported date formats include "%m/%d/%Y", "%Y-%m-%d", pandas Timestamp, and Excel serial date numbers.
        If the date format is unrecognized, a ValueError is raised.

        Args:
            number (str): The payment number.
            date (Union[str, datetime, pd.Timestamp, int, float]): The date of the payment, which can be a string,
                datetime object, pandas Timestamp, or an Excel serial date number.
            provider (Partner): The provider associated with this payment method.

        Returns:
            PaymentMethod: The retrieved or created PaymentMethod object.
        """

        if isinstance(date, str):
            try:
                date = make_aware(datetime.strptime(date, "%m/%d/%Y"))
            except ValueError:
                try:
                    date = make_aware(datetime.strptime(date, "%Y-%m-%d"))
                except ValueError:
                    date = make_aware(pd.to_datetime(date).to_pydatetime())

        elif isinstance(date, (pd.Timestamp, datetime)):
            date = make_aware(pd.to_datetime(date).to_pydatetime())

        elif isinstance(date, (int, float)):
            date = make_aware(pd.to_datetime(date, unit='d', origin='1899-12-30').to_pydatetime())

        else:
            raise ValueError(f"Format de date non reconnu : {type(date)}")

        return PaymentMethod.objects.get_or_create(
            payment_number=number.strip(),
            provider=provider,
            defaults=dict(emission_date=date)
        )[0]



    def get_or_create_client(self, name):
        """
        Retrieves or creates a Client object based on the given name.

        Args:
            name (str): The client name.

        Returns:
            Client: The retrieved or created Client object.
        """
        return Client.objects.get_or_create(name=name.strip().upper(), country=self.country, file=self.file)[0]

    def get_or_create_policy(self, number, client):
        
        """
        Retrieves or creates a Policy object based on the given policy number and client.

        Args:
            number (str): The policy number.
            client (Client): The client object associated with this policy.

        Returns:
            Policy: The retrieved or created Policy object.
        """

        return Policy.objects.get_or_create(policy_number=number.strip().upper(), client=client, file=self.file)[0]

    
    def get_or_create_operator(self, name):
        """
        Retrieves or creates an Operator object based on the given name.

        Args:
            name (str): The name of the operator.

        Returns:
            Operator: The retrieved or created Operator object.
        """
        if isinstance(name, str):
            name = name.strip()
        else:
            name = " "
        return Operator.objects.get_or_create(name=name.strip().upper(), country=self.country)[0]


    def get_or_create_primary_insured(self, name, statut):
        
        """
        Retrieves or creates a primary insured based on the given name and status.

        Args:
            name (str): The name of the primary insured.
            statut (str): The status of the primary insured, used to determine if the insured is a primary or not.

        Returns:
            Insured or None: The Insured object for the primary insured if created or found, otherwise None if the status is not "A".
        """
        if statut.upper() != "A":
            return None

        insured, _ = Insured.objects.get_or_create(
            name=name.strip().upper(),
            defaults=dict(
                is_primary_insured=True,
                is_spouse=False,
                is_child=False,
                primary_insured=None,
                file=self.file
            )
        )
        return insured
    
    def get_or_create_dependent_insured(self, name, statut, principal_name, insured_dict):

        """
        Retrieves or creates a dependent insured based on the given name and status.

        Args:
            name (str): The name of the dependent insured.
            statut (str): The status of the dependent insured, used to determine if they are a spouse or child.
            principal_name (str): The name of the primary insured to which the dependent is linked.
            insured_dict (dict): A dictionary mapping primary insured names to their respective Insured objects.

        Returns:
            Insured or None: The Insured object for the dependent if created or found, otherwise None if conditions are not met.
        """

        if statut.upper() == "A" or not principal_name:
            return None  

        primary_insured = insured_dict.get(principal_name.strip())
        if not primary_insured:

            print(f"[WARN] Assuré principal introuvable pour : {name} (réf: {principal_name})")
            return None

        is_spouse = statut.upper() == "C"
        is_child = statut.upper() == "E"

        insured, _ = Insured.objects.get_or_create(
            name=name.strip().upper(),
            defaults=dict(
                is_primary_insured=False,
                is_spouse=is_spouse,
                is_child=is_child,
                primary_insured=primary_insured,
                file=self.file
            )
        )
        return insured



    def get_or_create_invoice(self, number, claimed, reimbursed, provider, insured):
        """
        Retrieves or creates an invoice object based on the given parameters.

        Args:
            number (str|float|None): The invoice number, or None if no invoice number is provided.
            claimed (float): The claimed amount.
            reimbursed (float): The reimbursed amount.
            provider (Partner): The provider object associated with this invoice.
            insured (Insured): The insured object associated with this invoice.

        Returns:
            Invoice: The retrieved or created Invoice object.
        """
        cleaned_number = ""
        if number is None:
            cleaned_number = ""
        elif isinstance(number, float):
            if str(number).lower() == 'nan':
                cleaned_number = ""
            else:
                cleaned_number = str(int(number)) if number.is_integer() else str(number).upper()
        else:
            cleaned_number = str(number).upper()
        cleaned_number = cleaned_number.strip()

        return Invoice.objects.get_or_create(
            invoice_number=cleaned_number,
            provider=provider,
            insured=insured,
            defaults=dict(
                claimed_amount=claimed,
                reimbursed_amount=reimbursed,
                file=self.file
            )
        )[0]



    def get_or_create_claim(self, claim_id, status, date_claim, settlement_date, invoice, act, operator, insured, partner, policy):
        """
        Retrieves or creates a claim object based on the given parameters.

        Args:
            claim_id (str): The claim id.
            status (str): The claim status.
            date_claim (str|datetime|int|float): The claim date.
            settlement_date (str|datetime|int|float): The settlement date.

            invoice (Invoice): The invoice object associated with this claim.
            act (Act): The act object associated with this claim.
            operator (Operator): The operator object associated with this claim.
            insured (Insured): The insured object associated with this claim.
            partner (Partner): The partner object associated with this claim.
            policy (Policy): The policy object associated with this claim.

        Returns:
            Claim: The retrieved or created Claim object.
        """
        if isinstance(date_claim, str):
            try:
                date_claim = make_aware(datetime.strptime(date_claim, "%m/%d/%Y"))
            except ValueError:
                try:
                    date_claim = make_aware(datetime.strptime(date_claim, "%Y-%m-%d"))
                except ValueError:
                    date_claim = make_aware(pd.to_datetime(date_claim).to_pydatetime())

        elif isinstance(date_claim, (pd.Timestamp, datetime)):
            date_claim = make_aware(pd.to_datetime(date_claim).to_pydatetime())

        elif isinstance(date_claim, (int, float)):
            date_claim = make_aware(pd.to_datetime(date_claim, unit='d', origin='1899-12-30').to_pydatetime())

        else:
            raise ValueError(f"Format de date non reconnu : {type(date_claim)}")
        return Claim.objects.update_or_create(
            id=claim_id.strip(),
            defaults=dict(
                status=status[0] if isinstance(status, str) and status else " ",
                claim_date=date_claim,
                settlement_date = make_aware(settlement_date) if is_naive(settlement_date) else settlement_date,
                invoice=invoice,
                act=act,
                operator=operator,
                insured=insured,
                partner=partner,
                policy=policy,
                file=self.file
            )
        )[0]


