from rest_framework import viewsets, permissions
from .models import QRCodeLink, Review
from .serializers import QRCodeLinkSerializer, ReviewSerializer

class QRCodeLinkViewSet(viewsets.ModelViewSet):
    queryset = QRCodeLink.objects.all()
    serializer_class = QRCodeLinkSerializer
    permission_classes = [permissions.IsAuthenticated]

class ReviewViewSet(viewsets.ModelViewSet):
    queryset = Review.objects.select_related('qr_code_link').all()
    serializer_class = ReviewSerializer
    permission_classes = [permissions.IsAuthenticated]

    def perform_create(self, serializer):
        request = self.request
        serializer.save(
            ip_address=request.META.get('REMOTE_ADDR'),
            user_agent=request.META.get('HTTP_USER_AGENT', '')
        )
