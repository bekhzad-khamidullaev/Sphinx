from rest_framework import viewsets, permissions
from .models import QRCodeLink, Review
from .serializers import QRCodeLinkSerializer, ReviewSerializer

class QRCodeLinkViewSet(viewsets.ModelViewSet):
    queryset = QRCodeLink.objects.all()
    serializer_class = QRCodeLinkSerializer
    permission_classes = [permissions.IsAuthenticated]

class ReviewViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Review.objects.select_related('qr_code_link').all()
    serializer_class = ReviewSerializer
    permission_classes = [permissions.IsAdminUser]
