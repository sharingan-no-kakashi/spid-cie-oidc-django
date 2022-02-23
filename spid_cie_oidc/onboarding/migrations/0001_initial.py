# Generated by Django 4.0.2 on 2022-02-22 08:39

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
import spid_cie_oidc.entity.validators


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='OnBoardingRegistration',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('organization_name', models.CharField(help_text='Organization Name. ', max_length=254)),
                ('url_entity', models.URLField(help_text='URL of the Entity.', max_length=254, unique=True)),
                ('authn_buttons_page_url', models.URLField(help_text='URL of the page where the SPID/CIE button is available.', max_length=254)),
                ('public_jwks', models.JSONField(default=dict, help_text='Public jwks of the Entities', validators=[spid_cie_oidc.entity.validators.validate_public_jwks])),
                ('status', models.CharField(choices=[('onboarded', 'onboarded'), ('failed', 'failed'), ('processing', 'processing'), ('aquired', 'aquired')], default='aquired', max_length=33)),
                ('created_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'verbose_name': 'OnBoarding Registration',
                'verbose_name_plural': 'OnBoarding Registrations',
            },
        ),
    ]
