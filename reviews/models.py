from django.db import models
from django.utils.translation import gettext_lazy as _

class Review(models.Model):
    restaurant_name = models.CharField(max_length=255, verbose_name=_('Restaurant name'))
    user_name = models.CharField(max_length=255, verbose_name=_('User name'))
    rating = models.PositiveSmallIntegerField(verbose_name=_('Rating'))
    comment = models.TextField(blank=True, verbose_name=_('Comment'))
    created_at = models.DateTimeField(auto_now_add=True, verbose_name=_('Created at'))

    class Meta:
        verbose_name = _('Review')
        verbose_name_plural = _('Reviews')
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.restaurant_name} - {self.user_name}'
