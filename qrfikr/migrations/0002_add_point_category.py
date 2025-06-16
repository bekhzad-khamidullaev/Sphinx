from django.db import migrations, models
import django.db.models.deletion

class Migration(migrations.Migration):

    dependencies = [
        ('tasks', '0001_initial'),
        ('checklists', '0001_initial'),
        ('qrfikr', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='qrcodelink',
            name='point',
            field=models.OneToOneField(null=True, on_delete=django.db.models.deletion.CASCADE, related_name='qr_code', to='checklists.checklistpoint', verbose_name='Point'),
        ),
        migrations.AddField(
            model_name='qrcodelink',
            name='task_category',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='qr_codes', to='tasks.taskcategory', verbose_name='Task category'),
        ),
    ]
