import uuid
from django.db import models
from django.urls import reverse
from django.utils.translation import gettext_lazy as _


class QRCodeLink(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    location = models.ForeignKey('checklists.Location', on_delete=models.CASCADE, related_name='qr_codes', verbose_name=_('Location'))
    description = models.CharField(max_length=255, blank=True, verbose_name=_('Description'))
    is_active = models.BooleanField(default=True, verbose_name=_('Active'))
    qr_image = models.ImageField(upload_to='qr_codes/', blank=True, verbose_name=_('QR Image'))
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = _('QR Link')
        verbose_name_plural = _('QR Links')
        ordering = ['location__name']

    def __str__(self):
        return self.location.name

    def get_feedback_url(self):
        return reverse('qrfikr:submit', kwargs={'qr_uuid': self.id})


class Review(models.Model):
    RATING_CHOICES = [(i, str(i)) for i in range(1, 6)]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    qr_code_link = models.ForeignKey(QRCodeLink, on_delete=models.CASCADE, related_name='reviews')
    rating = models.PositiveSmallIntegerField(choices=RATING_CHOICES)
    text = models.TextField(blank=True)
    contact_info = models.CharField(max_length=255, blank=True)
    photo = models.ImageField(upload_to='review_photos/', blank=True)
    submitted_at = models.DateTimeField(auto_now_add=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.CharField(max_length=255, blank=True)

    class Meta:
        verbose_name = _('Review')
        verbose_name_plural = _('Reviews')
        ordering = ['-submitted_at']

    def __str__(self):
        return f"{self.qr_code_link} ({self.rating})"
