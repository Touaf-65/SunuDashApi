from django.db import migrations, models


def link_existing_recaps(apps, schema_editor):
    """Les sessions existantes n'avaient qu'un récap : il devient le premier de recap_files."""
    ImportSession = apps.get_model('file_handling', 'ImportSession')
    Through = ImportSession.recap_files.through
    Through.objects.bulk_create(
        [Through(importsession_id=s.pk, file_id=s.recap_file_id) for s in ImportSession.objects.only('pk', 'recap_file_id')],
        ignore_conflicts=True,
    )


class Migration(migrations.Migration):

    dependencies = [
        ('file_handling', '0008_uploaded_by_role'),
    ]

    operations = [
        migrations.AddField(
            model_name='importsession',
            name='recap_files',
            field=models.ManyToManyField(blank=True, related_name='recap_set_sessions', to='file_handling.file'),
        ),
        migrations.AddField(
            model_name='importsession',
            name='stat_sheet',
            field=models.CharField(blank=True, default='', max_length=255),
        ),
        migrations.AddField(
            model_name='importsession',
            name='summary',
            field=models.JSONField(blank=True, null=True),
        ),
        migrations.AlterField(
            model_name='importsession',
            name='status',
            field=models.CharField(choices=[('PENDING', 'Pending'), ('AWAITING_SHEET', 'Awaiting sheet choice'), ('PROCESSING', 'Processing'), ('ANALYSED', 'Analysed'), ('DONE', 'Done'), ('ERROR', 'Error'), ('DONE_WITH_ERRORS', 'Done with Errors')], default='PENDING', max_length=20),
        ),
        migrations.RunPython(link_existing_recaps, migrations.RunPython.noop),
    ]
