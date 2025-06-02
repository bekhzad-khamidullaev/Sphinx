from rest_framework import serializers
from django.core.files.base import ContentFile
import base64
import uuid
import logging

from .models import QRCodeLink, Review

logger = logging.getLogger(__name__)

# Conditional import for LocationSerializer
try:
    from checklists.serializers import LocationSerializer
    # A basic LocationSerializer might look like this if it doesn't exist:
    # from checklists.models import Location as ChecklistsLocation
    # class LocationSerializer(serializers.ModelSerializer):
    #     class Meta:
    #         model = ChecklistsLocation
    #         fields = ['id', 'name', 'description'] # Adjust as needed
except ImportError:
    logger.warning("qrfikr.serializers: checklists.serializers.LocationSerializer not found. Using a fallback basic serializer.")
    try:
        from checklists.models import Location as ChecklistsLocation
        class LocationSerializer(serializers.ModelSerializer):
            class Meta:
                model = ChecklistsLocation
                fields = ['id', 'name']
    except ImportError:
        logger.error("qrfikr.serializers: checklists.models.Location also not found. QR Code API will lack location details.")
        class LocationSerializer(serializers.Serializer): # Dummy serializer
            id = serializers.IntegerField()
            name = serializers.CharField()


class QRCodeLinkSerializer(serializers.ModelSerializer):
    location = LocationSerializer(read_only=True) # Use the imported or dummy LocationSerializer
    feedback_url = serializers.CharField(source='get_feedback_url', read_only=True)
    qr_image_url = serializers.ImageField(source='qr_image', read_only=True, use_url=True)

    class Meta:
        model = QRCodeLink
        fields = [
            'id', 'location', 'short_description', # location_details removed, location is now nested
            'qr_image_url', 'feedback_url', # qr_image removed, using qr_image_url
            'is_active', 'created_at', 'updated_at'
        ]
        read_only_fields = ('created_at', 'updated_at', 'qr_image_url', 'feedback_url')
        # 'location' field itself is writeable by its PK if needed, but usually set by admin.

class Base64ImageField(serializers.ImageField):
    def to_internal_value(self, data):
        if isinstance(data, str) and data.startswith('data:image'):
            try:
                format, imgstr = data.split(';base64,')
                ext = format.split('/')[-1]
                # Use a more robust way to generate a unique name
                file_name = f"{uuid.uuid4().hex}.{ext}"
                decoded_file = ContentFile(base64.b64decode(imgstr), name=file_name)
                return super().to_internal_value(decoded_file)
            except Exception as e:
                logger.error(f"Error decoding base64 image: {e}")
                raise serializers.ValidationError(f"Error decoding image: {e}")
        
        # If it's not a base64 string, let the parent class handle it (e.g. actual file upload)
        return super().to_internal_value(data)

class ReviewCreateSerializer(serializers.ModelSerializer):
    photo = Base64ImageField(required=False, allow_null=True, max_length=None, use_url=True)

    class Meta:
        model = Review
        fields = ['qr_code_link', 'rating', 'text', 'photo', 'contact_info']
        extra_kwargs = {
            'qr_code_link': {'required': True, 'write_only': True}, # Usually write_only for create
            'rating': {'required': True},
            'text': {'required': False, 'allow_blank': True},
            'contact_info': {'required': False, 'allow_blank': True},
        }

    def validate_qr_code_link(self, value):
        if not isinstance(value, QRCodeLink): # Ensure 'value' is an instance, not just PK
            try:
                value = QRCodeLink.objects.get(pk=value.pk if hasattr(value, 'pk') else value)
            except QRCodeLink.DoesNotExist:
                 raise serializers.ValidationError("Invalid QR Code Link reference.")
        if not value.is_active:
            raise serializers.ValidationError("This QR code link is not active.")
        return value

class ReviewDisplaySerializer(serializers.ModelSerializer):
    qr_code_link_id = serializers.UUIDField(source='qr_code_link.id', read_only=True)
    location_name = serializers.CharField(source='qr_code_link.location.name', read_only=True, allow_null=True)
    rating_display = serializers.CharField(source='get_rating_display', read_only=True)
    photo_url = serializers.ImageField(source='photo', read_only=True, use_url=True) # Use use_url=True
    related_task_id = serializers.IntegerField(source='related_task.id', read_only=True, allow_null=True)
    related_task_number = serializers.CharField(source='related_task.task_number', read_only=True, allow_null=True)


    class Meta:
        model = Review
        fields = [
            'id', 'qr_code_link_id', 'location_name', 'rating', 'rating_display',
            'text', 'photo_url', 'contact_info', 'submitted_at', # photo removed, using photo_url
            'related_task_id', 'related_task_number', 'user_agent', 'ip_address'
        ]