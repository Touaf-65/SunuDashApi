# Generated by Django 5.1.6 on 2025-07-29 08:11

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("file_handling", "0006_importsession_log_file_path"),
    ]

    operations = [
        migrations.RenameField(
            model_name="file",
            old_name="file_name",
            new_name="name",
        ),
    ]
