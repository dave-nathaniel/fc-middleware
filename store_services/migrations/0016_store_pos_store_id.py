from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('store_services', '0015_delete_sales'),
    ]

    operations = [
        migrations.AddField(
            model_name='store',
            name='pos_store_id',
            field=models.CharField(blank=True, max_length=50, null=True, unique=True),
        ),
    ]
