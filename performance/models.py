from django.db import models
from django.conf import settings
from django.utils.translation import gettext_lazy as _

class ReviewCycle(models.Model):
    name = models.CharField(_('Цикл аттестации'), max_length=100, unique=True)
    start = models.DateField()
    end = models.DateField()

    def __str__(self):
        return self.name

class PerformanceReview(models.Model):
    employee = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='reviews')
    manager = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name='managed_reviews')
    cycle = models.ForeignKey(ReviewCycle, on_delete=models.CASCADE)
    score = models.IntegerField(null=True, blank=True)
    comments = models.TextField(blank=True)
    status = models.CharField(max_length=20, default='draft')

    def __str__(self):
        return f"{self.employee.display_name} - {self.cycle.name}"
