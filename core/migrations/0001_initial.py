# Generated by Django 5.1.6 on 2025-07-21 11:03

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ("countries", "0001_initial"),
        ("file_handling", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="ActCategory",
            fields=[
                ("id", models.AutoField(primary_key=True, serialize=False)),
                ("creation_date", models.DateTimeField(auto_now_add=True)),
                ("modification_date", models.DateTimeField(auto_now=True)),
                ("label", models.CharField(max_length=255)),
            ],
        ),
        migrations.CreateModel(
            name="Operator",
            fields=[
                ("id", models.AutoField(primary_key=True, serialize=False)),
                ("name", models.CharField(max_length=255)),
            ],
        ),
        migrations.CreateModel(
            name="ActFamily",
            fields=[
                ("id", models.AutoField(primary_key=True, serialize=False)),
                ("creation_date", models.DateTimeField(auto_now_add=True)),
                ("modification_date", models.DateTimeField(auto_now=True)),
                ("label", models.CharField(max_length=255)),
                (
                    "category",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="families",
                        to="core.actcategory",
                    ),
                ),
            ],
        ),
        migrations.CreateModel(
            name="Act",
            fields=[
                ("id", models.AutoField(primary_key=True, serialize=False)),
                ("creation_date", models.DateTimeField(auto_now_add=True)),
                ("modification_date", models.DateTimeField(auto_now=True)),
                ("label", models.CharField(max_length=255)),
                (
                    "family",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="acts",
                        to="core.actfamily",
                    ),
                ),
            ],
        ),
        migrations.CreateModel(
            name="Client",
            fields=[
                ("id", models.AutoField(primary_key=True, serialize=False)),
                ("contact", models.CharField(blank=True, max_length=255, null=True)),
                ("creation_date", models.DateTimeField(auto_now_add=True)),
                ("modification_date", models.DateTimeField(auto_now=True)),
                ("name", models.CharField(max_length=255)),
                (
                    "prime",
                    models.DecimalField(
                        blank=True, decimal_places=2, max_digits=10, null=True
                    ),
                ),
                (
                    "country",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="clients",
                        to="countries.country",
                    ),
                ),
                (
                    "file",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="clients",
                        to="file_handling.file",
                    ),
                ),
                (
                    "import_session",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="imported_clients",
                        to="file_handling.importsession",
                    ),
                ),
            ],
        ),
        migrations.CreateModel(
            name="ClientPrimeHistory",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("prime", models.DecimalField(decimal_places=2, max_digits=10)),
                ("date", models.DateTimeField(auto_now_add=True)),
                (
                    "client",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="prime_history",
                        to="core.client",
                    ),
                ),
            ],
        ),
        migrations.CreateModel(
            name="Insured",
            fields=[
                ("id", models.AutoField(primary_key=True, serialize=False)),
                ("name", models.CharField(max_length=255)),
                ("birth_date", models.DateField(blank=True, null=True)),
                ("creation_date", models.DateTimeField(auto_now_add=True)),
                ("modification_date", models.DateTimeField(auto_now=True)),
                (
                    "card_number",
                    models.CharField(blank=True, max_length=255, null=True),
                ),
                (
                    "phone_number",
                    models.CharField(blank=True, max_length=20, null=True),
                ),
                ("email", models.EmailField(blank=True, max_length=255, null=True)),
                ("consumption_limit", models.FloatField(blank=True, null=True)),
                ("is_primary_insured", models.BooleanField(default=False)),
                ("is_child", models.BooleanField(default=False)),
                ("is_spouse", models.BooleanField(default=False)),
                (
                    "file",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="insureds",
                        to="file_handling.file",
                    ),
                ),
                (
                    "import_session",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="imported_insureds",
                        to="file_handling.importsession",
                    ),
                ),
                (
                    "primary_insured",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="dependents",
                        to="core.insured",
                    ),
                ),
            ],
        ),
        migrations.CreateModel(
            name="Partner",
            fields=[
                ("id", models.AutoField(primary_key=True, serialize=False)),
                ("name", models.CharField(max_length=255)),
                ("contact", models.CharField(blank=True, max_length=255, null=True)),
                ("modification_date", models.DateTimeField(auto_now=True)),
                ("creation_date", models.DateTimeField(auto_now_add=True)),
                (
                    "main_responsible_name",
                    models.CharField(blank=True, max_length=255, null=True),
                ),
                (
                    "country",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="partners",
                        to="countries.country",
                    ),
                ),
            ],
        ),
        migrations.CreateModel(
            name="Invoice",
            fields=[
                ("id", models.AutoField(primary_key=True, serialize=False)),
                ("creation_date", models.DateTimeField(auto_now_add=True)),
                ("modification_date", models.DateTimeField(auto_now=True)),
                ("invoice_number", models.CharField(max_length=255)),
                ("claimed_amount", models.FloatField()),
                ("reimbursed_amount", models.FloatField()),
                (
                    "file",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="invoices",
                        to="file_handling.file",
                    ),
                ),
                (
                    "import_session",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="imported_invoices",
                        to="file_handling.importsession",
                    ),
                ),
                (
                    "insured",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="invoices",
                        to="core.insured",
                    ),
                ),
                (
                    "provider",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="invoices",
                        to="core.partner",
                    ),
                ),
            ],
        ),
        migrations.CreateModel(
            name="PaymentMethod",
            fields=[
                ("id", models.AutoField(primary_key=True, serialize=False)),
                ("creation_date", models.DateTimeField(auto_now_add=True)),
                ("modification_date", models.DateTimeField(auto_now=True)),
                ("payment_number", models.CharField(max_length=255)),
                ("emission_date", models.DateTimeField()),
                (
                    "provider",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="payment_methods",
                        to="core.partner",
                    ),
                ),
            ],
        ),
        migrations.CreateModel(
            name="Policy",
            fields=[
                ("id", models.AutoField(primary_key=True, serialize=False)),
                ("creation_date", models.DateTimeField(auto_now_add=True)),
                ("policy_number", models.CharField(max_length=255)),
                (
                    "client",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="policies",
                        to="core.client",
                    ),
                ),
                (
                    "file",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="policies",
                        to="file_handling.file",
                    ),
                ),
                (
                    "import_session",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="imported_policies",
                        to="file_handling.importsession",
                    ),
                ),
            ],
        ),
        migrations.CreateModel(
            name="Claim",
            fields=[
                (
                    "id",
                    models.CharField(max_length=255, primary_key=True, serialize=False),
                ),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("A", "Approved"),
                            ("R", "Rejected"),
                            ("C", "Canceled"),
                        ],
                        max_length=1,
                        null=True,
                    ),
                ),
                ("claim_date", models.DateTimeField()),
                ("settlement_date", models.DateTimeField()),
                (
                    "act",
                    models.ForeignKey(
                        null=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="claims",
                        to="core.act",
                    ),
                ),
                (
                    "file",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="claims",
                        to="file_handling.file",
                    ),
                ),
                (
                    "import_session",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="imported_claims",
                        to="file_handling.importsession",
                    ),
                ),
                (
                    "insured",
                    models.ForeignKey(
                        null=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="claims",
                        to="core.insured",
                    ),
                ),
                (
                    "invoice",
                    models.ForeignKey(
                        null=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="claims",
                        to="core.invoice",
                    ),
                ),
                (
                    "operator",
                    models.ForeignKey(
                        null=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="claims",
                        to="core.operator",
                    ),
                ),
                (
                    "partner",
                    models.ForeignKey(
                        null=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="claims",
                        to="core.partner",
                    ),
                ),
                (
                    "policy",
                    models.ForeignKey(
                        null=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="claims",
                        to="core.policy",
                    ),
                ),
            ],
        ),
        migrations.CreateModel(
            name="InsuredEmployer",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "role",
                    models.CharField(
                        choices=[
                            ("primary", "Assuré principal"),
                            ("spouse", "Conjoint(e)"),
                            ("child", "Enfant"),
                            ("other", "Autre"),
                        ],
                        default="primary",
                        max_length=20,
                    ),
                ),
                ("start_date", models.DateField(blank=True, null=True)),
                ("end_date", models.DateField(blank=True, null=True)),
                (
                    "employer",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="client_insureds",
                        to="core.client",
                    ),
                ),
                (
                    "file",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="insured_employers",
                        to="file_handling.file",
                    ),
                ),
                (
                    "import_session",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="imported_insured_employers",
                        to="file_handling.importsession",
                    ),
                ),
                (
                    "insured",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="insured_clients",
                        to="core.insured",
                    ),
                ),
                (
                    "primary_insured_ref",
                    models.ForeignKey(
                        blank=True,
                        help_text="Renseigner si l’assuré est conjoint ou enfant.",
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="dependents_in_clients",
                        to="core.insured",
                    ),
                ),
                (
                    "policy",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="insured_employers",
                        to="core.policy",
                    ),
                ),
            ],
            options={
                "unique_together": {("insured", "employer", "policy")},
            },
        ),
    ]
