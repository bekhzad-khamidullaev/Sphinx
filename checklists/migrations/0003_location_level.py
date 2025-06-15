from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("checklists", "0002_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="location",
            name="level",
            field=models.CharField(
                choices=[
                    ("venue", "Заведение/Ресторан"),
                    ("room", "Комната/Помещение"),
                    ("area", "Зона/Уголок"),
                    ("point", "Точка/Объект"),
                ],
                default="venue",
                max_length=20,
                verbose_name="Тип локации",
                db_index=True,
            ),
        ),
    ]
