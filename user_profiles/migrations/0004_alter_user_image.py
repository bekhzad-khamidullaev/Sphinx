# Generated by Django 4.0 on 2024-06-23 13:41

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('user_profiles', '0003_remove_user_profile_remove_userprofile_image_and_more'),
    ]

    operations = [
        migrations.AlterField(
            model_name='user',
            name='image',
            field=models.ImageField(default='', upload_to='images/profile_pics/'),
        ),
    ]
