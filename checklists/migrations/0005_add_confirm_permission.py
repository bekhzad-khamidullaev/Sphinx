from django.db import migrations

class Migration(migrations.Migration):
    dependencies = [
        ('checklists', '0004_alter_location_logo_image'),
    ]

    operations = [
        migrations.AlterModelOptions(
            name='checklist',
            options={
                'verbose_name': 'Выполненный чеклист (Прогон)',
                'verbose_name_plural': 'Выполненные чеклисты (Прогоны)',
                'ordering': ['-performed_at', '-created_at'],
                'permissions': [('confirm_checklist', 'Can confirm checklist')],
            },
        ),
    ]

