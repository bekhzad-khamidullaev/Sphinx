from rest_framework import serializers
from .models import QRCodeLink, Review

class QRCodeLinkSerializer(serializers.ModelSerializer):
    class Meta:
        model = QRCodeLink
        fields = '__all__'

class ReviewSerializer(serializers.ModelSerializer):
    class Meta:
        model = Review
        fields = '__all__'
        read_only_fields = ('ip_address', 'user_agent', 'submitted_at')
