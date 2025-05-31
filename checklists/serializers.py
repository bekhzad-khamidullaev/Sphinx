# checklists/serializers.py
from rest_framework import serializers
from django.utils.translation import gettext_lazy as _
from .models import (
    Location, ChecklistPoint, ChecklistTemplate, ChecklistTemplateItem,
    Checklist, ChecklistResult, AnswerType, ChecklistItemStatus, ChecklistRunStatus,
    ChecklistSection
)
try:
    from tasks.models import TaskCategory # Попытка импорта
except ImportError:
    TaskCategory = None # Если не удается, устанавливаем в None


class LocationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Location
        fields = ['id', 'name', 'description', 'parent']

class ChecklistPointSerializer(serializers.ModelSerializer):
    location_name = serializers.CharField(source='location.name', read_only=True)

    class Meta:
        model = ChecklistPoint
        fields = ['id', 'name', 'location', 'location_name', 'description']

class ChecklistTemplateItemSerializer(serializers.ModelSerializer):
    target_point_name = serializers.CharField(source='target_point.name', read_only=True, allow_null=True)
    answer_type_display = serializers.CharField(source='get_answer_type_display', read_only=True)
    section_title = serializers.CharField(source='section.title', read_only=True, allow_null=True)

    class Meta:
        model = ChecklistTemplateItem
        fields = [
            'id', 'item_text', 'order', 'answer_type', 'answer_type_display',
            'section', 'section_title',
            'target_point', 'target_point_name', 'help_text', 'default_value',
            'parent_item',
        ]

class ChecklistSectionSerializer(serializers.ModelSerializer):
     items = ChecklistTemplateItemSerializer(many=True, read_only=True)

     class Meta:
         model = ChecklistSection
         fields = ['id', 'title', 'order', 'items']

class ChecklistTemplateSerializer(serializers.ModelSerializer):
    category_name = serializers.SerializerMethodField() # Используем SerializerMethodField
    target_location_name = serializers.CharField(source='target_location.name', read_only=True, allow_null=True)       
    target_point_name = serializers.CharField(source='target_point.name', read_only=True, allow_null=True)
    sections = ChecklistSectionSerializer(many=True, read_only=True)
    unsectioned_items = serializers.SerializerMethodField()
    tags = serializers.StringRelatedField(many=True, read_only=True)

    class Meta:
        model = ChecklistTemplate
        fields = [
            'uuid', 'name', 'description', 'version', 'is_active', 'is_archived', # Добавил is_archived
            'category', 'category_name',
            'target_location', 'target_location_name',
            'target_point', 'target_point_name',
            'frequency', 'next_due_date', 'tags',
            'sections', 'unsectioned_items',
            'created_at', 'updated_at'
        ]

    def get_category_name(self, obj):
        # Проверяем, что obj.category существует и имеет атрибут name
        if obj.category and hasattr(obj.category, 'name'):
            return obj.category.name
        return None # Возвращаем None или '-', если категории нет

    def get_unsectioned_items(self, obj):
         unsectioned_items = obj.items.filter(section__isnull=True)
         return ChecklistTemplateItemSerializer(unsectioned_items, many=True, context=self.context).data

class ChecklistResultSerializer(serializers.ModelSerializer):
    template_item = ChecklistTemplateItemSerializer(read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    display_value = serializers.SerializerMethodField()
    created_by_username = serializers.CharField(source='created_by.username', read_only=True, allow_null=True)
    updated_by_username = serializers.CharField(source='updated_by.username', read_only=True, allow_null=True)

    class Meta:
        model = ChecklistResult
        fields = [
            'id', 'template_item', 'status', 'status_display', 'comments', 'is_corrected',
            'recorded_at', 'created_by', 'created_by_username', 'updated_by', 'updated_by_username',
            'display_value',
            'value', 'numeric_value', 'boolean_value', 'date_value', 'datetime_value',
            'time_value', 'file_attachment', 'media_url'
        ]

    def get_display_value(self, obj):
        if obj.template_item.answer_type == AnswerType.FILE and obj.file_attachment:
             request = self.context.get('request')
             try:
                 return request.build_absolute_uri(obj.file_attachment.url) if request else obj.file_attachment.url    
             except ValueError:
                 return obj.file_attachment.url
             except Exception:
                  return obj.file_attachment.url
        return obj.display_value


class ChecklistRunSerializer(serializers.ModelSerializer):
    template = ChecklistTemplateSerializer(read_only=True)
    performed_by_username = serializers.CharField(source='performed_by.username', read_only=True, allow_null=True)     
    location_name = serializers.CharField(source='location.name', read_only=True, allow_null=True)
    point_name = serializers.CharField(source='point.name', read_only=True, allow_null=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    approved_by_username = serializers.CharField(source='approved_by.username', read_only=True, allow_null=True)       
    results = ChecklistResultSerializer(many=True, read_only=True)

    class Meta:
        model = Checklist
        fields = [
            'id', 'template', 'performed_by', 'performed_by_username', 'performed_at',
            'related_task',
            'location', 'location_name',
            'point', 'point_name',
            'notes', 'status', 'status_display', 'is_complete', 'completion_time',
            'approved_by', 'approved_by_username',
            'approved_at', 'score',
            'created_at', 'updated_at', 'external_reference',
            'results'
        ]

class ChecklistRunCreateUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Checklist
        fields = ['template', 'performed_by', 'performed_at', 'location', 'point', 'related_task', 'notes', 'external_reference']
        read_only_fields = ['status', 'is_complete', 'completion_time', 'approved_by', 'approved_at', 'score']
        extra_kwargs = {
            'template': {'required': True},
            'performed_by': {'required': False, 'allow_null': True},
        }

class ChecklistResultUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = ChecklistResult
        fields = ['status', 'comments', 'is_corrected', 'value', 'numeric_value', 'boolean_value',
                  'date_value', 'datetime_value', 'time_value', 'file_attachment', 'media_url']
        read_only_fields = ['template_item', 'checklist_run']

    def validate(self, data):
        instance = self.instance
        if not instance:
             return data

        status = data.get('status', instance.status)
        comments = data.get('comments', instance.comments)
        comments = comments.strip() if comments else ""

        if status == ChecklistItemStatus.NOT_OK and not comments:
             raise serializers.ValidationError({'comments': _('Комментарий обязателен, если статус "%(status)s".') % {'status': ChecklistItemStatus.NOT_OK.label}})

        if status in [ChecklistItemStatus.OK, ChecklistItemStatus.NOT_OK]:
            item = instance.template_item
            value_provided = False
            correct_value_field = item.primary_value_field_name

            submitted_value = data.get(correct_value_field, None)
            existing_value = getattr(instance, correct_value_field, None)


            if correct_value_field == 'file_attachment':
                 if submitted_value is not None and submitted_value is not False:
                      value_provided = True
                 elif submitted_value is None and existing_value:
                      value_provided = True
                 elif submitted_value is False :
                      value_provided = True
            elif submitted_value is not None:
                if isinstance(submitted_value, str):
                    value_provided = bool(submitted_value.strip())
                else:
                    value_provided = True
            elif existing_value is not None:
                if isinstance(existing_value, str):
                    value_provided = bool(existing_value.strip())
                else:
                    value_provided = True


            value_types_requiring_input = [
                 AnswerType.TEXT, AnswerType.SCALE_1_4, AnswerType.SCALE_1_5,
                 AnswerType.YES_NO, AnswerType.YES_NO_MEH, AnswerType.NUMBER,
                 AnswerType.DATE, AnswerType.DATETIME, AnswerType.TIME,
                 AnswerType.BOOLEAN, AnswerType.FILE, AnswerType.URL
            ]

            if item.answer_type in value_types_requiring_input and not value_provided:
                 if correct_value_field in self.fields.keys():
                      raise serializers.ValidationError({correct_value_field: _('Пожалуйста, предоставьте ответ для этого пункта.')})
                 else:
                       raise serializers.ValidationError({'non_field_errors': [_('Пункт "%(item)s" требует ответа.') % {'item': item.item_text}]})


        return data

    def update(self, instance, validated_data):
        item = instance.template_item
        correct_value_field = item.primary_value_field_name

        all_value_fields = ['value', 'numeric_value', 'boolean_value', 'date_value', 'datetime_value', 'time_value', 'file_attachment', 'media_url']
        for field in all_value_fields:
            if field != correct_value_field:
                 if field == 'file_attachment':
                     if field in validated_data and validated_data[field] is None:
                          setattr(instance, field, None)
                 else:
                      if field in validated_data and validated_data[field] is None:
                          setattr(instance, field, None)
                      elif field not in validated_data:
                          setattr(instance, field, None)


        numeric_value_to_update = None
        if item.answer_type in [AnswerType.YES_NO, AnswerType.YES_NO_MEH] and 'value' in validated_data:
             text_value = validated_data['value']
             if text_value == 'yes': numeric_value_to_update = 1.0
             elif text_value == 'no': numeric_value_to_update = 0.0
             elif text_value == 'yes_no_meh': numeric_value_to_update = 0.5
             else: numeric_value_to_update = None
        elif item.answer_type == AnswerType.BOOLEAN and 'boolean_value' in validated_data:
             bool_value = validated_data['boolean_value']
             if bool_value is True: numeric_value_to_update = 1.0
             elif bool_value is False: numeric_value_to_update = 0.0
             else: numeric_value_to_update = None

        if numeric_value_to_update is not None:
             validated_data['numeric_value'] = numeric_value_to_update
        elif correct_value_field != 'numeric_value':
            validated_data['numeric_value'] = None


        request = self.context.get('request')
        if request and request.user and request.user.is_authenticated:
             validated_data['updated_by'] = request.user
             if not instance.created_by:
                  validated_data['created_by'] = request.user

        return super().update(instance, validated_data)