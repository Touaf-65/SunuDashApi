import pandas as pd

from core.models import (
    File, Client, Policy, Insured, InsuredEmployer, Invoice, Partner, 
    PaymentMethod, Operator, Claim, Act, ActFamily, ActCategory
)
from users.models import Country
from datetime import datetime
from django.utils.timezone import make_aware, is_naive



class DataMapper:
    def __init__(self, df_stat, import_session):
        self.df_stat = df_stat
        self.import_session = import_session
        self.country = import_session.country
        self.file = import_session.file_stat
        self.user = import_session.user

    def map_data(self):
        df = self.df_stat.copy()
        insured_dict = {}
        self.errors = []  


        insured_created = 0
        claims_created = 0
        total_claimed = 0
        total_reimbursed = 0

        df = df.dropna(how='all', axis=1)
        df = df.dropna(how='all', axis=0)

        for index, row in df.iterrows():
            try:
                cat = self.get_or_create_category(row["act_category"])
                fam = self.get_or_create_family(row["act_family"], cat)
                act = self.get_or_create_act(row["act_name"], fam, cat)

                partner = self.get_or_create_partner(row["partner_name"], row["partner_country"], self.user)
                self.get_or_create_payment_method(row["payment_method"], row["payment_date"], partner)

                self.get_or_create_operator(row["modified_by"])
                client = self.get_or_create_client(row["employer_name"])
                self.get_or_create_policy(row["policy_number"], client)
            except Exception as e:
                self.errors.append(f"[ETAPE 1 - index {index}] Erreur : {e}")


        df_primary = df[df["insured_status"].str.upper() == "A"]
        for index, row in df_primary.iterrows():
            try:
                name = row["beneficiary_name"]
                insured = self.get_or_create_primary_insured(name, row["insured_status"])
                if insured:
                    insured_dict[name.strip()] = insured
                    insured_created += 1
            except Exception as e:
                self.errors.append(f"[ETAPE 2 - index {index}] Erreur création assuré principal '{row['beneficiary_name']}' : {e}")


        df_dependents = df[df["insured_status"].str.upper().isin(["C", "E"])]
        for index, row in df_dependents.iterrows():
            try:
                name = row["beneficiary_name"]
                statut = row["insured_status"]
                principal_name = row["main_insured"]
                insured = self.get_or_create_dependent_insured(name, statut, principal_name, insured_dict)
                if insured:
                    insured_dict[name.strip()] = insured
                    insured_created += 1
            except Exception as e:
                self.errors.append(f"[ETAPE 3 - index {index}] Erreur création assuré dépendant '{row['beneficiary_name']}' : {e}")


        for index, row in df.iterrows():
            try:
                name = row["beneficiary_name"].strip()
                insured = insured_dict.get(name)
                if not insured:
                    raise Exception(f"Aucun assuré trouvé pour '{name}'")

                provider = self.get_or_create_partner(row["partner_name"], row["partner_country"], self.user)
                invoice = self.get_or_create_invoice(row["invoice_number"], row["claimed_amount"], row["reimbursed_amount"], provider, insured)

                cat = self.get_or_create_category(row["act_category"])
                fam = self.get_or_create_family(row["act_family"], cat)
                act = self.get_or_create_act(row["act_name"], fam, cat)

                operator = self.get_or_create_operator(row["modified_by"])
                client = self.get_or_create_client(row["employer_name"], self.country, self.file)
                policy = self.get_or_create_policy(row["policy_number"], client)

                claim = self.get_or_create_claim(
                    claim_id=row["claim_id"],
                    status=row["claim_status"],
                    date_claim=row["claim_date"],
                    settlement_date=row["incident_date"],
                    invoice=invoice,
                    act=act,
                    operator=operator,
                    insured=insured,
                    partner=provider,
                    policy=policy,
                    file=self.file
                )
                if claim:
                    claims_created += 1
                    total_claimed += row["claimed_amount"] or 0
                    total_reimbursed += row["reimbursed_amount"] or 0

            except Exception as e:
                self.errors.append(f"[ETAPE 4 - index {index}] Erreur sinistre/facture '{row['claim_id']}' : {e}")
        

        self.import_session.insured_created_count = insured_created
        self.import_session.claims_created_count = claims_created
        self.import_session.total_claimed_amount = total_claimed
        self.import_session.total_reimbursed_amount = total_reimbursed

        self.import_session.save()



    @staticmethod
    def get_or_create_category(label):
        if isinstance(label, str):
            label = label.strip()
        else:
            label = " "
        return ActCategory.objects.get_or_create(label=label.strip().upper())[0]


    @staticmethod
    def get_or_create_family(label, category):
        if isinstance(label, str):
            label = label.strip()
        else:
            label = " "
        return ActFamily.objects.get_or_create(label=label.strip().upper(), category=category)[0]

    @staticmethod
    def get_or_create_act(label, family, category):
        if isinstance(label, str):
            label = label.strip().upper()
        else:
            label = " "
        return Act.objects.get_or_create(label=label.strip().upper(), category=category, family=family)[0]


    def get_or_create_partner(self, name, country_name, user):
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

        return Partner.objects.get_or_create(name=name.strip().upper(), user=user, country=country)[0]
    
    @staticmethod
    def get_or_create_payment_method(number, date, provider):
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
        return Client.objects.get_or_create(name=name.strip().upper(), country=self.country, file=self.file)[0]

    def get_or_create_policy(self, number, client):
        
        return Policy.objects.get_or_create(policy_number=number.strip().upper(), client=client, file=self.file)[0]

    
    def get_or_create_operator(self, name):
        if isinstance(name, str):
            name = name.strip()
        else:
            name = " "
        return Operator.objects.get_or_create(name=name.strip().upper(), country=self.country)[0]


    def get_or_create_primary_insured(self, name, statut):
        
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
