import uuid
from django.db import models
from django.urls import reverse
from django.utils.translation import gettext_lazy as _

from checklists.models import ChecklistPoint
from tasks.models import TaskCategory, Project, Task


class QRCodeLink(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    location = models.ForeignKey('checklists.Location', on_delete=models.CASCADE, related_name='qr_codes', verbose_name=_('Location'))
    point = models.OneToOneField(
        ChecklistPoint,
        on_delete=models.CASCADE,
        related_name='qr_code',
        verbose_name=_('Point'),
        null=True,
        blank=True,
    )
    task_category = models.ForeignKey(
        TaskCategory,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='qr_codes',
        verbose_name=_('Task category'),
    )
    description = models.CharField(max_length=255, blank=True, verbose_name=_('Description'))
    is_active = models.BooleanField(default=True, verbose_name=_('Active'))
    qr_image = models.ImageField(upload_to='qr_codes/', blank=True, verbose_name=_('QR Image'))
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = _('QR Link')
        verbose_name_plural = _('QR Links')
        ordering = ['location__name', 'point__name']

    def __str__(self):
        point_name = self.point.name if self.point else '?' 
        return f"{self.location.name} / {point_name}"

    def save(self, *args, **kwargs):
        if self.point:
            self.location = self.point.location
        super().save(*args, **kwargs)

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

    def save(self, *args, **kwargs):
        is_new = self._state.adding
        super().save(*args, **kwargs)
        if is_new and self.rating < 3:
            project, _ = Project.objects.get_or_create(name='Customer Feedback')
            point_name = self.qr_code_link.point.name if self.qr_code_link.point else 'N/A'
            Task.objects.create(
                project=project,
                category=self.qr_code_link.task_category,
                title=f'Negative review at {point_name}',
                description=self.text,
            )
