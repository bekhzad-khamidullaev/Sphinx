from django.db import migrations, models
import taggit.managers

class Migration(migrations.Migration):
    dependencies = [
        ('checklists', '0005_add_confirm_permission'),
        ('taggit', '0006_rename_taggeditem_content_type_object_id_taggit_tagg_content_8fc721_idx'),
    ]

    operations = [
        migrations.CreateModel(
            name='ChecklistTemplateTag',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(unique=True, max_length=100, verbose_name='name')),
                ('slug', models.SlugField(unique=True, max_length=100, allow_unicode=True, verbose_name='slug')),
            ],
            options={
                'verbose_name': 'Тег шаблона чеклиста',
                'verbose_name_plural': 'Теги шаблонов чеклиста',
            },
        ),
        migrations.CreateModel(
            name='ChecklistTemplateTaggedItem',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('object_id', models.UUIDField(db_index=True, verbose_name='object ID')),
                ('content_type', models.ForeignKey(on_delete=models.CASCADE, related_name='checklists_checklisttemplatetaggeditem_tagged_items', to='contenttypes.contenttype')),
                ('tag', models.ForeignKey(on_delete=models.CASCADE, related_name='tagged_items', to='checklists.checklisttemplatetag')),
            ],
            options={
                'verbose_name': 'Связь шаблона чеклиста и тега',
                'verbose_name_plural': 'Связи шаблонов чеклиста и тегов',
            },
        ),
        migrations.AlterField(
            model_name='checklisttemplate',
            name='tags',
            field=taggit.managers.TaggableManager(blank=True, help_text='Разделяйте теги запятыми.', through='checklists.ChecklistTemplateTaggedItem', to='checklists.ChecklistTemplateTag', verbose_name='Теги'),
        ),
    ]
