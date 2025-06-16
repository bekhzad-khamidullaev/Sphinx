import uuid
from django.db import models
from django.urls import reverse
from django.utils.translation import gettext_lazy as _
from checklists.models import ChecklistPoint, Location
from tasks.models import TaskCategory, Project, Task
from django.db.models.signals import post_save
from django.dispatch import receiver


    """Link between a QR code and a specific checklist point."""

        Location,
        related_name="qr_codes",
        verbose_name=_("Location"),
        related_name="qr_code",
        verbose_name=_("Point"),
    description = models.CharField(_("Description"), max_length=255, blank=True)
    is_active = models.BooleanField(_("Active"), default=True)
    qr_image = models.ImageField(_("QR Image"), upload_to="qr_codes/", blank=True)
        verbose_name = _("QR Link")
        verbose_name_plural = _("QR Links")
        ordering = ["location__name"]

    def __str__(self) -> str:
        text = self.location.name
            text += f" / {self.point.name}"
        return text
    def get_feedback_url(self) -> str:
        return reverse("qrfikr:submit", kwargs={"qr_uuid": self.id})
    """User feedback left via a QR code."""

    qr_code_link = models.ForeignKey(
        QRCodeLink,
        on_delete=models.CASCADE,
        related_name="reviews",
    )
        verbose_name=_("Category"),
    photo = models.ImageField(upload_to="review_photos/", blank=True)
        verbose_name = _("Review")
        verbose_name_plural = _("Reviews")
        ordering = ["-submitted_at"]
    def __str__(self) -> str:
    def create_task(self) -> None:
        if self.rating >= 3 or not self.category:
            return
        project, _ = Project.objects.get_or_create(name="Guest Feedback")
        point = self.qr_code_link.point
        location_name = point.name if point else self.qr_code_link.location.name
        Task.objects.create(
            project=project,
            category=self.category,
            title=f"Feedback {self.rating}/5 at {location_name}",
            description=self.text,
        )
def review_post_save(sender, instance: Review, created: bool, **kwargs):
        instance.create_task()
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name=_('Category'),
    )
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



def _get_feedback_project():
    project, _ = Project.objects.get_or_create(name="Guest Feedback")
    return project


def create_task_from_review(review: 'Review') -> None:
    if review.rating >= 3 or not review.category:
        return
    project = _get_feedback_project()

    point = review.qr_code_link.point
    point_name = point.name if point else review.qr_code_link.location.name
    title = f"Feedback {review.rating}/5 at {point_name}"

    description = review.text
    Task.objects.create(
        project=project,
        category=review.category,
        title=title,
        description=description,
    )


from django.db.models.signals import post_save
from django.dispatch import receiver


@receiver(post_save, sender=Review)
def review_post_save(sender, instance, created, **kwargs):
    if created:
        create_task_from_review(instance)

