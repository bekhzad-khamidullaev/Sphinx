from django.db import models
from user_profiles.models import User, Role

class TelegramUser(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='telegram_profile')
    telegram_id = models.CharField(max_length=20, unique=True)
    approved = models.BooleanField(default=False)

    def __str__(self):
        return f"{self.user.username} ({self.telegram_id})"

# class Role(models.Model):
#     name = models.CharField(max_length=50, unique=True)

#     def __str__(self):
#         return self.name

class Question(models.Model):
    role = models.ForeignKey(Role, on_delete=models.CASCADE, related_name='questions')
    text = models.CharField(max_length=255)
    order = models.PositiveIntegerField(default=1)

    class Meta:
        ordering = ['order']

    def __str__(self):
        return f"{self.role.name}: {self.text}"

class Evaluation(models.Model):
    evaluator = models.ForeignKey(TelegramUser, on_delete=models.CASCADE)
    employee_name = models.CharField(max_length=100)
    role = models.ForeignKey(Role, on_delete=models.CASCADE)
    responses = models.JSONField()
    timestamp = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-timestamp']
        verbose_name = "Оценка"
        verbose_name_plural = "Оценки"

    def __str__(self):
        return f"Оценка {self.employee_name} от {self.get_evaluator_name()}"

    # --- Удобные методы доступа ---
    def get_responses(self):
        return self.responses

    def get_timestamp(self):
        return self.timestamp

    def get_evaluator(self):
        return self.evaluator

    def get_employee_name(self):
        return self.employee_name

    def get_role(self):
        return self.role

    def get_evaluator_name(self):
        return self.evaluator.user.get_full_name() if self.evaluator and self.evaluator.user else None

    def get_evaluator_telegram_id(self):
        return self.evaluator.telegram_id if self.evaluator else None

    def get_evaluator_approved(self):
        return self.evaluator.approved if self.evaluator else None

    def get_role_name(self):
        return self.role.name if self.role else None

    def get_role_id(self):
        return self.role.id if self.role else None