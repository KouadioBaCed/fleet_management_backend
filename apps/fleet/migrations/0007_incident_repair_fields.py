from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('fleet', '0006_change_driver_rating_default'),
    ]

    operations = [
        migrations.AddField(
            model_name='incident',
            name='repair_invoice',
            field=models.FileField(
                blank=True,
                null=True,
                upload_to='incidents/invoices/',
                verbose_name='Facture de réparation',
            ),
        ),
        migrations.AddField(
            model_name='incident',
            name='repair_cost',
            field=models.DecimalField(
                blank=True,
                decimal_places=2,
                max_digits=10,
                null=True,
                verbose_name='Coût de réparation',
            ),
        ),
    ]
