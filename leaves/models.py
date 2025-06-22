from django.db import models
from django.conf import settings
from django.utils.translation import gettext_lazy as _

class LeaveType(models.Model):
    name = models.CharField(_('Тип отпуска'), max_length=100, unique=True)

    def __str__(self):
        return self.name

class LeaveRequest(models.Model):
    class Status(models.TextChoices):
        PENDING = 'pending', _('В ожидании')
        APPROVED = 'approved', _('Одобрено')
        REJECTED = 'rejected', _('Отклонено')

    employee = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='leave_requests')
    leave_type = models.ForeignKey(LeaveType, on_delete=models.CASCADE)
    start_date = models.DateField()
    end_date = models.DateField()
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    comment = models.TextField(blank=True)
    approved_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name='approved_leaves')

    def __str__(self):
        return f"{self.employee.display_name}: {self.leave_type.name}"
