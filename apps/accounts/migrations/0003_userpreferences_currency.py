# Generated manually

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0002_emailverificationtoken_userpreferences'),
    ]

    operations = [
        migrations.AddField(
            model_name='userpreferences',
            name='currency',
            field=models.CharField(
                choices=[
                    ('USD', 'Dollar américain ($)'),
                    ('EUR', 'Euro (€)'),
                    ('CDF', 'Franc congolais (FC)'),
                    ('XAF', 'Franc CFA (FCFA)'),
                    ('GBP', 'Livre sterling (£)'),
                ],
                default='USD',
                max_length=10,
                verbose_name='Devise'
            ),
        ),
    ]
