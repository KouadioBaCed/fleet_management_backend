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
                    ('XOF', 'Franc CFA (FCFA)'),
                ],
                default='XOF',
                max_length=10,
                verbose_name='Devise'
            ),
        ),
    ]
