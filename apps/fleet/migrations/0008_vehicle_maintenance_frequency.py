from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('fleet', '0007_incident_repair_fields'),
    ]

    operations = [
        migrations.AddField(
            model_name='vehicle',
            name='maintenance_frequency_km',
            field=models.PositiveIntegerField(
                blank=True,
                help_text='Frequence de maintenance en km (ex: 10000)',
                null=True,
                verbose_name='Frequence maintenance (km)',
            ),
        ),
        migrations.AddField(
            model_name='vehicle',
            name='maintenance_frequency_months',
            field=models.PositiveIntegerField(
                blank=True,
                help_text='Frequence de maintenance en mois (ex: 6)',
                null=True,
                verbose_name='Frequence maintenance (mois)',
            ),
        ),
    ]
