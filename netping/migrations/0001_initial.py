# Generated by Django 5.1 on 2024-08-17 20:47

import django.db.models.deletion
import encrypted_model_fields.fields
import simple_history.models
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='Branch',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(blank=True, max_length=200, null=True)),
            ],
            options={
                'db_table': 'branch',
                'managed': True,
            },
        ),
        migrations.CreateModel(
            name='NetPingDevice',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('ip_address', models.GenericIPAddressField(blank=True, null=True)),
                ('location', models.CharField(blank=True, max_length=255, null=True)),
                ('hostname', models.CharField(blank=True, max_length=200, null=True)),
                ('snmp_community_ro', encrypted_model_fields.fields.EncryptedCharField(blank=True, default='SWITCH', null=True)),
                ('snmp_community_rw', encrypted_model_fields.fields.EncryptedCharField(blank=True, default='SWITCH', null=True)),
                ('last_updated', models.DateTimeField(auto_now=True)),
                ('status', models.BooleanField(blank=True, default=False, null=True)),
                ('uptime', models.CharField(blank=True, max_length=200, null=True)),
                ('created', models.DateTimeField(auto_now_add=True, null=True)),
            ],
            options={
                'db_table': 'netping',
                'managed': True,
                'indexes': [models.Index(fields=['status', 'hostname', 'ip_address'], name='netping_status_a73493_idx')],
                'unique_together': {('hostname', 'ip_address')},
            },
        ),
        migrations.CreateModel(
            name='HistoricalSensor',
            fields=[
                ('id', models.BigIntegerField(auto_created=True, blank=True, db_index=True, verbose_name='ID')),
                ('sensor_id', models.CharField(blank=True, max_length=255, null=True)),
                ('sensor_type', models.IntegerField(choices=[(1, 'Temperature'), (2, 'Humidity'), (3, 'Voltage sensor'), (4, 'Door contact'), (5, 'Movement detector')])),
                ('sensor_name', models.CharField(blank=True, max_length=255, null=True)),
                ('status', models.IntegerField(blank=True, choices=[(0, 'Sensor failure or disconnection'), (1, 'Below normal'), (2, 'Normal'), (3, 'Above normal')], default=0, null=True)),
                ('value_high_trshld', models.IntegerField(blank=True, default=0, null=True)),
                ('value_current', models.FloatField(blank=True, null=True)),
                ('value_low_trshld', models.IntegerField(blank=True, default=0, null=True)),
                ('last_updated', models.DateTimeField(blank=True, editable=False, null=True)),
                ('history_id', models.AutoField(primary_key=True, serialize=False)),
                ('history_date', models.DateTimeField(db_index=True)),
                ('history_change_reason', models.CharField(max_length=100, null=True)),
                ('history_type', models.CharField(choices=[('+', 'Created'), ('~', 'Changed'), ('-', 'Deleted')], max_length=1)),
                ('history_user', models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='+', to=settings.AUTH_USER_MODEL)),
                ('device', models.ForeignKey(blank=True, db_constraint=False, null=True, on_delete=django.db.models.deletion.DO_NOTHING, related_name='+', to='netping.netpingdevice')),
            ],
            options={
                'verbose_name': 'historical sensor',
                'verbose_name_plural': 'historical sensors',
                'ordering': ('-history_date', '-history_id'),
                'get_latest_by': ('history_date', 'history_id'),
            },
            bases=(simple_history.models.HistoricalChanges, models.Model),
        ),
        migrations.CreateModel(
            name='Problems',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('problem_name', models.CharField(max_length=100)),
                ('problem_severity', models.IntegerField(choices=[(0, 'Not classified'), (1, 'Information'), (2, 'Warning'), (3, 'Average'), (4, 'High'), (5, 'Disaster')])),
                ('status', models.BooleanField(blank=True, default=True, null=True)),
                ('created', models.DateTimeField(auto_now_add=True, null=True)),
                ('last_updated', models.DateTimeField(auto_now=True, null=True)),
                ('host', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='problem_set', to='netping.netpingdevice')),
            ],
            options={
                'db_table': 'problems',
                'managed': True,
            },
        ),
        migrations.CreateModel(
            name='Comments',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('comment', models.CharField(blank=True, max_length=300, null=True)),
                ('last_update', models.DateTimeField(auto_now=True, null=True)),
                ('user', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to=settings.AUTH_USER_MODEL)),
                ('problem', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='comment', to='netping.problems')),
            ],
            options={
                'db_table': 'comments',
                'managed': True,
            },
        ),
        migrations.CreateModel(
            name='Sensor',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('sensor_id', models.CharField(blank=True, max_length=255, null=True)),
                ('sensor_type', models.IntegerField(choices=[(1, 'Temperature'), (2, 'Humidity'), (3, 'Voltage sensor'), (4, 'Door contact'), (5, 'Movement detector')])),
                ('sensor_name', models.CharField(blank=True, max_length=255, null=True)),
                ('status', models.IntegerField(blank=True, choices=[(0, 'Sensor failure or disconnection'), (1, 'Below normal'), (2, 'Normal'), (3, 'Above normal')], default=0, null=True)),
                ('value_high_trshld', models.IntegerField(blank=True, default=0, null=True)),
                ('value_current', models.FloatField(blank=True, null=True)),
                ('value_low_trshld', models.IntegerField(blank=True, default=0, null=True)),
                ('last_updated', models.DateTimeField(auto_now=True, null=True)),
                ('device', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='sensor_set', to='netping.netpingdevice')),
            ],
        ),
        migrations.AddField(
            model_name='problems',
            name='sensor',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='problem_set', to='netping.sensor'),
        ),
        migrations.CreateModel(
            name='HistoricalProblems',
            fields=[
                ('id', models.BigIntegerField(auto_created=True, blank=True, db_index=True, verbose_name='ID')),
                ('problem_name', models.CharField(max_length=100)),
                ('problem_severity', models.IntegerField(choices=[(0, 'Not classified'), (1, 'Information'), (2, 'Warning'), (3, 'Average'), (4, 'High'), (5, 'Disaster')])),
                ('status', models.BooleanField(blank=True, default=True, null=True)),
                ('created', models.DateTimeField(blank=True, editable=False, null=True)),
                ('last_updated', models.DateTimeField(blank=True, editable=False, null=True)),
                ('history_id', models.AutoField(primary_key=True, serialize=False)),
                ('history_date', models.DateTimeField(db_index=True)),
                ('history_change_reason', models.CharField(max_length=100, null=True)),
                ('history_type', models.CharField(choices=[('+', 'Created'), ('~', 'Changed'), ('-', 'Deleted')], max_length=1)),
                ('history_user', models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='+', to=settings.AUTH_USER_MODEL)),
                ('host', models.ForeignKey(blank=True, db_constraint=False, null=True, on_delete=django.db.models.deletion.DO_NOTHING, related_name='+', to='netping.netpingdevice')),
                ('sensor', models.ForeignKey(blank=True, db_constraint=False, null=True, on_delete=django.db.models.deletion.DO_NOTHING, related_name='+', to='netping.sensor')),
            ],
            options={
                'verbose_name': 'historical problems',
                'verbose_name_plural': 'historical problemss',
                'ordering': ('-history_date', '-history_id'),
                'get_latest_by': ('history_date', 'history_id'),
            },
            bases=(simple_history.models.HistoricalChanges, models.Model),
        ),
        migrations.AddIndex(
            model_name='problems',
            index=models.Index(fields=['status', 'host'], name='problems_status_80a81f_idx'),
        ),
    ]
