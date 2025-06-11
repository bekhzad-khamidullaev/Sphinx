# checklists/serializers.py
# Used for API views (requires Django REST framework)
from rest_framework import serializers
from .models import (
    Location, ChecklistPoint, ChecklistTemplate, ChecklistTemplateItem,
    Checklist, ChecklistResult, AnswerType, ChecklistItemStatus, ChecklistRunStatus,
    ChecklistSection # Added ChecklistSection import
)

# Serializers for Location and ChecklistPoint
class LocationSerializer(serializers.ModelSerializer):
    # Include child locations if needed
    # child_locations = serializers.PrimaryKeyRelatedField(many=True, read_only=True)
    class Meta:
        model = Location
        fields = ['id', 'name', 'description', 'parent']

class ChecklistPointSerializer(serializers.ModelSerializer):
    location_name = serializers.CharField(source='location.name', read_only=True)

    class Meta:
        model = ChecklistPoint
        fields = ['id', 'name', 'location', 'location_name', 'description']

# Serializer for ChecklistTemplateItem (nested or standalone)
class ChecklistTemplateItemSerializer(serializers.ModelSerializer):
    target_point_name = serializers.CharField(source='target_point.name', read_only=True, allow_null=True)
    answer_type_display = serializers.CharField(source='get_answer_type_display', read_only=True)
    section_title = serializers.CharField(source='section.title', read_only=True, allow_null=True)
    # Optionally serialize parent item ID or serializer for nested structure
    # parent_item = serializers.PrimaryKeyRelatedField(read_only=True) # Or nested serializer
    # sub_items = ChecklistTemplateItemSerializer(many=True, read_only=True) # Recursive, be careful

    class Meta:
        model = ChecklistTemplateItem
        fields = [
            'id', 'item_text', 'order', 'answer_type', 'answer_type_display',
            'section', 'section_title', # Include section info
            'target_point', 'target_point_name', 'help_text', 'default_value',
            'parent_item', # Include parent ID
            # 'sub_items', # Include sub-items if recursive
        ]

# Serializer for ChecklistSection (nested within Template)
class ChecklistSectionSerializer(serializers.ModelSerializer):
     # Serialize items related to this section, ordered correctly
     items = ChecklistTemplateItemSerializer(many=True, read_only=True) # items are pre-fetched and ordered in view

     class Meta:
         model = ChecklistSection # This was the missing import
         fields = ['id', 'title', 'order', 'items']

# Serializer for ChecklistTemplate (with nested sections/items)
class ChecklistTemplateSerializer(serializers.ModelSerializer):
    category_name = serializers.CharField(source='category.name', read_only=True, allow_null=True)
    target_location_name = serializers.CharField(source='target_location.name', read_only=True, allow_null=True)
    target_point_name = serializers.CharField(source='target_point.name', read_only=True, allow_null=True)
    # Serialize sections, which include items
    sections = ChecklistSectionSerializer(many=True, read_only=True)
    # Optionally include unsectioned items directly
    unsectioned_items = serializers.SerializerMethodField() # Method to get items with section=None
    tags = serializers.StringRelatedField(many=True, read_only=True) # Simple tag representation

    class Meta:
        model = ChecklistTemplate
        fields = [
            'uuid', 'name', 'description', 'version', 'is_active',
            'category', 'category_name',
            'target_location', 'target_location_name',
            'target_point', 'target_point_name',
            'frequency', 'next_due_date', 'tags',
            'sections', 'unsectioned_items', # Include nested sections and unsectioned items
            'created_at', 'updated_at'
        ]

    def get_unsectioned_items(self, obj):
         """Custom method to serialize template items not belonging to any section."""
         # Assuming template.items relation is available (prefetched in view)
         unsectioned_items = obj.items.filter(section__isnull=True)
         # Use the item serializer to serialize these items
         return ChecklistTemplateItemSerializer(unsectioned_items, many=True, context=self.context).data # Pass context

# Serializer for ChecklistResult (nested within ChecklistRun)
class ChecklistResultSerializer(serializers.ModelSerializer):
    template_item = ChecklistTemplateItemSerializer(read_only=True) # Nested item serializer
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    # Use SerializerMethodField to display the correct value based on type
    display_value = serializers.SerializerMethodField()
    created_by_username = serializers.CharField(source='created_by.username', read_only=True, allow_null=True)
    updated_by_username = serializers.CharField(source='updated_by.username', read_only=True, allow_null=True)

    class Meta:
        model = ChecklistResult
        fields = [
            'id', 'template_item', 'status', 'status_display', 'comments', 'is_corrected',
            'recorded_at', 'created_by', 'created_by_username', 'updated_by', 'updated_by_username',
            'display_value', # Use the property for display
            'value', 'numeric_value', 'boolean_value', 'date_value', 'datetime_value', # Include raw values if needed
            'time_value', 'file_attachment', 'media_url'
        ]

    def get_display_value(self, obj):
        """Serialize the display_value property."""
        # Handle FileField URL separately as it's a Django field property
        if obj.template_item.answer_type == AnswerType.FILE and obj.file_attachment:
             # Ensure the URL is absolute if needed (pass request context)
             request = self.context.get('request')
             try:
                 # Attempt to build absolute URI
                 return request.build_absolute_uri(obj.file_attachment.url) if request else obj.file_attachment.url
             except ValueError:
                 # Handle cases where the file path might be invalid or inaccessible
                 return obj.file_attachment.url # Fallback to relative URL
             except Exception: # Catch any other potential errors during URL building
                  return obj.file_attachment.url # Fallback
        # For other types, use the display_value property directly
        return obj.display_value


# Serializer for ChecklistRun
class ChecklistRunSerializer(serializers.ModelSerializer):
    template = ChecklistTemplateSerializer(read_only=True) # Nested template serializer
    performed_by_username = serializers.CharField(source='performed_by.username', read_only=True, allow_null=True)
    location_name = serializers.CharField(source='location.name', read_only=True, allow_null=True)
    point_name = serializers.CharField(source='point.name', read_only=True, allow_null=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    approved_by_username = serializers.CharField(source='approved_by.username', read_only=True, allow_null=True)
    # Include nested results
    results = ChecklistResultSerializer(many=True, read_only=True) # Results are pre-fetched and ordered in view

    class Meta:
        model = Checklist
        fields = [
            'id', 'template', 'performed_by', 'performed_by_username', 'performed_at',
            'related_task', # Maybe serialize related_task details later
            'location', 'location_name',
            'point', 'point_name',
            'notes', 'status', 'status_display', 'is_complete', 'completion_time',
            'approved_by', 'approved_by_username', # Include username
            'approved_at', 'score',
            'created_at', 'updated_at', 'external_reference',
            'results' # Include nested results
        ]

# Serializer for creating/updating ChecklistRun (simpler version without nested results for input)
class ChecklistRunCreateUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Checklist
        # Fields allowed for input
        fields = ['template', 'performed_by', 'performed_at', 'location', 'point', 'related_task', 'notes', 'external_reference']
        # template should probably be read-only or set by view based on URL
        read_only_fields = ['template', 'performed_by', 'status', 'is_complete', 'completion_time', 'approved_by', 'approved_at', 'score'] # Status handled by separate endpoint/logic

    # You would typically handle creating/updating related ChecklistResult objects
    # in the view or by overriding create/update methods in the serializer.
    # This is complex and often handled better by separate endpoints for results or a custom view.


# Serializer for updating a single ChecklistResult via API
class ChecklistResultUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = ChecklistResult
        # Fields allowed for updating a specific result
        fields = ['status', 'comments', 'is_corrected', 'value', 'numeric_value', 'boolean_value',
                  'date_value', 'datetime_value', 'time_value', 'file_attachment', 'media_url']
        # template_item and checklist_run are read-only
        read_only_fields = ['template_item', 'checklist_run']

    def validate(self, data):
        """
        Add validation mirroring forms.py's clean() logic.
        Ensure comments for NOT_OK, value presence for OK/NOT_OK.
        """
        instance = self.instance # Existing instance being updated
        if not instance: # Should not happen in update view
             return data

        status = data.get('status', instance.status) # Get status from data or instance
        comments = data.get('comments', instance.comments) # Get comments from data or instance
        comments = comments.strip() if comments else "" # Ensure comments is a string

        # Validate comments for NOT_OK status
        if status == ChecklistItemStatus.NOT_OK and not comments:
             raise serializers.ValidationError({'comments': _('Комментарий обязателен, если статус "%(status)s".') % {'status': ChecklistItemStatus.NOT_OK.label}})

        # Validate value presence for OK/NOT_OK status
        if status in [ChecklistItemStatus.OK, ChecklistItemStatus.NOT_OK]:
            item = instance.template_item # Get related item
            value_provided = False
            correct_value_field = item.primary_value_field_name # Use model property

            # Determine if a value is present in the validated data or already exists on the instance
            submitted_value = data.get(correct_value_field)
            existing_value = getattr(instance, correct_value_field)

            # Special check for FileField:
            if correct_value_field == 'file_attachment':
                 # New file uploaded or existing file kept and not cleared
                 if submitted_value is not None and submitted_value is not False:
                      value_provided = True
                 # No new file, but existing file is present
                 elif submitted_value is None and existing_value:
                      value_provided = True
                 # File explicitly cleared
                 elif submitted_value is False:
                      value_provided = True # Action was taken (clearing)
            elif isinstance(submitted_value, str):
                 value_provided = bool(submitted_value.strip())
            elif submitted_value is not None:
                 value_provided = True
            # Check instance if value not in submitted data (for partial updates)
            elif submitted_value is None and existing_value is not None:
                  # Check for non-empty string for existing value
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
        """
        Custom update to ensure only the relevant value field is saved and others cleared.
        Also handles created_by/updated_by logic.
        """
        item = instance.template_item
        correct_value_field = item.primary_value_field_name # Use model property

        # Clear other value fields on the *instance* before saving validated_data
        all_value_fields = ['value', 'numeric_value', 'boolean_value', 'date_value', 'datetime_value', 'time_value', 'file_attachment', 'media_url']
        for field in all_value_fields:
            if field != correct_value_field:
                 # FileField clearing is handled by DRF if 'None' is passed in data or field is omitted in partial update
                 if field == 'file_attachment':
                     # Only clear if the field is *explicitly* set to None in validated_data
                     # Otherwise, omitting it means "keep existing"
                     if field in validated_data and validated_data[field] is None:
                          setattr(instance, field, None)
                 else:
                      setattr(instance, field, None)

        # Handle numeric_value mapping for text/bool choices if value is updated
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

        # Explicitly add numeric_value to validated_data if it needs updating
        if numeric_value_to_update is not None:
             validated_data['numeric_value'] = numeric_value_to_update


        # Set updated_by user (assuming user is in serializer context)
        request = self.context.get('request')
        if request and request.user and request.user.is_authenticated:
             validated_data['updated_by'] = request.user
             # Set created_by if not already set (should be set on initial creation via signal/view)
             if not instance.created_by:
                  validated_data['created_by'] = request.user # Fallback

        return super().update(instance, validated_data)