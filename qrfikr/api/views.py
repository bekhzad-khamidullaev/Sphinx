from rest_framework import viewsets, permissions, status, mixins
from rest_framework.response import Response
from rest_framework.decorators import action
from django_filters.rest_framework import DjangoFilterBackend
from django.shortcuts import get_object_or_404
import logging

from qrfikr.models import QRCodeLink, Review
from qrfikr.serializers import (
    QRCodeLinkSerializer, ReviewCreateSerializer, ReviewDisplaySerializer
)
from qrfikr.tasks import generate_qr_image_task

logger = logging.getLogger(__name__)

class QRCodeLinkViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = QRCodeLink.objects.filter(is_active=True).select_related('location')
    serializer_class = QRCodeLinkSerializer
    permission_classes = [permissions.AllowAny]
    lookup_field = 'id'

    @action(detail=True, methods=['post'], permission_classes=[permissions.IsAdminUser])
    def regenerate_qr(self, request, id=None):
        qr_link = self.get_object()
        try:
            generate_qr_image_task.delay(str(qr_link.id))
            logger.info(f"QR regeneration task scheduled for QRCodeLink {qr_link.id}")
            return Response({'status': 'QR regeneration task scheduled'}, status=status.HTTP_202_ACCEPTED)
        except Exception as e:
            logger.error(f"Failed to schedule Celery task for QR regeneration of {qr_link.id}: {e}. Attempting synchronous.")
            try:
                qr_link.generate_and_save_qr_image(force_regeneration=True)
                qr_link.save(update_fields=['qr_image', 'updated_at'])
                serializer = self.get_serializer(qr_link)
                logger.info(f"Synchronously regenerated QR for {qr_link.id}")
                return Response(serializer.data, status=status.HTTP_200_OK)
            except Exception as sync_e:
                logger.error(f"Synchronous QR regeneration failed for {qr_link.id}: {sync_e}")
                return Response({'error': f'Failed to regenerate QR code: {sync_e}'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class ReviewViewSet(mixins.CreateModelMixin,
                    mixins.RetrieveModelMixin,
                    mixins.ListModelMixin,
                    viewsets.GenericViewSet):
    queryset = Review.objects.all().select_related('qr_code_link__location', 'related_task').order_by('-submitted_at')
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['qr_code_link__location', 'rating']

    def get_serializer_class(self):
        if self.action == 'create':
            return ReviewCreateSerializer
        return ReviewDisplaySerializer

    def get_permissions(self):
        if self.action == 'create':
            return [permissions.AllowAny()]
        return [permissions.IsAdminUser()]

    def perform_create(self, serializer):
        ip_address = self.request.META.get('REMOTE_ADDR')
        user_agent = self.request.META.get('HTTP_USER_AGENT', '')
        
        x_forwarded_for = self.request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            ip_address = x_forwarded_for.split(',')[0].strip()
        
        serializer.save(ip_address=ip_address, user_agent=user_agent)
        logger.info(f"Review created via API. QR Link: {serializer.instance.qr_code_link_id}, Rating: {serializer.instance.rating}, IP: {ip_address}")