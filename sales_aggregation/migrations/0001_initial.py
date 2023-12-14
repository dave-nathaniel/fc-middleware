# Generated by Django 4.2.7 on 2023-12-13 03:42

from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
    ]

    operations = [
        migrations.CreateModel(
            name='LedgerAccount',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=255)),
                ('description', models.TextField()),
                ('canonical_name', models.CharField(blank=True, max_length=255, null=True)),
                ('byd_gl_code', models.CharField(max_length=20)),
                ('byd_cost_center_code', models.CharField(max_length=20)),
            ],
        ),
    ]
