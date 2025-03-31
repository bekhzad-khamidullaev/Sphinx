# user_profiles/models.py
from django.contrib.auth.models import AbstractUser, Group, Permission
from django.db import models
from django.conf import settings
from django.utils.translation import gettext_lazy as _
from django.db.models.signals import post_save
from django.dispatch import receiver

# Use django-mptt for efficient hierarchical structures (optional but recommended)
# from mptt.models import MPTTModel, TreeForeignKey

# ------------------------ Base Model ------------------------
class BaseModel(models.Model):
    created_at = models.DateTimeField(auto_now_add=True, verbose_name=_("Дата создания"))
    updated_at = models.DateTimeField(auto_now=True, verbose_name=_("Дата обновления"))

    class Meta:
        abstract = True
        ordering = ['-created_at']

# ------------------------ Department (Company Structure) ------------------------
# Simple parent/child structure. Consider django-mptt for complex hierarchies.
class Department(BaseModel):
    """Represents a department or unit within the company structure."""
    name = models.CharField(max_length=150, verbose_name=_("Название отдела"))
    parent = models.ForeignKey(
        'self',
        on_delete=models.SET_NULL, # Or PROTECT if departments shouldn't be deleted if they have children
        null=True,
        blank=True,
        related_name='children',
        verbose_name=_("Вышестоящий отдел")
    )
    head = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='headed_departments',
        verbose_name=_("Руководитель отдела")
    )
    description = models.TextField(blank=True, verbose_name=_("Описание"))

    class Meta:
        verbose_name = _("Отдел")
        verbose_name_plural = _("Отделы")
        ordering = ['name']
        indexes = [
            models.Index(fields=["name"]),
            models.Index(fields=["parent"]),
        ]
        # If using mptt:
        # ordering = ['tree_id', 'lft']

    def __str__(self):
        # Basic string representation, could show hierarchy if using MPTT
        return self.name

    # Add methods for getting ancestors/descendants if not using MPTT


# ------------------------ Custom User Model ------------------------
class User(AbstractUser):
    """Extended user model."""
    # Remove username constraints if using email as username
    # USERNAME_FIELD = 'email'
    # REQUIRED_FIELDS = ['username'] # Keep username required if not using email

    # Add fields like phone number, job title, etc.
    email = models.EmailField(_('email address'), unique=True) # Ensure email is unique
    phone_number = models.CharField(_("Номер телефона"), max_length=20, blank=True, null=True)
    job_title = models.CharField(_("Должность"), max_length=100, blank=True, null=True)
    image = models.ImageField(
        _("Аватар"),
        default='profile_pics/user.svg', # Use a default SVG or image
        upload_to='profile_pics/',
        blank=True
    )
    department = models.ForeignKey(
        Department,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='employees',
        verbose_name=_("Отдел")
    )

    # Override groups and user_permissions for custom related names if desired
    # groups = models.ManyToManyField(
    #     Group,
    #     verbose_name=_('groups'),
    #     blank=True,
    #     help_text=_(
    #         'The groups this user belongs to. A user will get all permissions '
    #         'granted to each of their groups.'
    #     ),
    #     related_name="custom_user_set", # Custom related name
    #     related_query_name="user",
    # )
    # user_permissions = models.ManyToManyField(
    #     Permission,
    #     verbose_name=_('user permissions'),
    #     blank=True,
    #     help_text=_('Specific permissions for this user.'),
    #     related_name="custom_user_set", # Custom related name
    #     related_query_name="user",
    # )

    class Meta:
        verbose_name = _("Пользователь")
        verbose_name_plural = _("Пользователи")
        ordering = ['last_name', 'first_name', 'username']

    def __str__(self):
        return self.get_full_name() or self.username

    @property
    def display_name(self):
         """Returns full name or username."""
         return self.get_full_name() or self.username

# Remove UserProfile if department and other fields are directly on User model
# class UserProfile(models.Model):
#     user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='user_profile')
#     # Move department here if UserProfile is kept
#     # department = models.ForeignKey(Department, on_delete=models.SET_NULL, null=True, blank=True)
#     team = models.ForeignKey('user_profiles.Team', on_delete=models.SET_NULL, null=True, blank=True, related_name="member_profiles") # Keep if team membership is managed via profile

#     def __str__(self):
#         return self.user.username

# @receiver(post_save, sender=settings.AUTH_USER_MODEL)
# def create_or_update_user_profile(sender, instance, created, **kwargs):
#     """Ensure UserProfile exists for every User."""
#     if created:
#         UserProfile.objects.create(user=instance)
#     instance.user_profile.save()


# ------------------------ Teams ------------------------
class Team(BaseModel):
    """Represents a working team, potentially linked to a department."""
    name = models.CharField(max_length=100, verbose_name=_("Название команды"), unique=True) # Ensure team names are unique
    team_leader = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="led_teams", # Changed related_name
        verbose_name=_("Лидер команды")
    )
    # Use direct M2M on User model for team membership if UserProfile is removed
    members = models.ManyToManyField(
        settings.AUTH_USER_MODEL,
        blank=True,
        related_name="teams", # Changed related_name for clarity
        verbose_name=_("Участники")
    )
    department = models.ForeignKey(
        Department,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='teams',
        verbose_name=_("Отдел") # Optional: Link team to a department
    )
    description = models.TextField(blank=True, verbose_name=_("Описание команды"))

    class Meta:
        verbose_name = _("Команда")
        verbose_name_plural = _("Команды")
        ordering = ["name"]
        indexes = [
             models.Index(fields=["name"]),
             models.Index(fields=["department"]),
        ]

    def __str__(self):
        return self.name

    def add_member(self, user):
        """Adds a user to the team's members."""
        self.members.add(user)
        # Optionally update UserProfile if it manages team membership
        # profile, _ = UserProfile.objects.get_or_create(user=user)
        # profile.team = self
        # profile.save()

    def remove_member(self, user):
        """Removes a user from the team's members."""
        self.members.remove(user)
        # Optionally update UserProfile
        # profile = getattr(user, 'user_profile', None)
        # if profile and profile.team == self:
        #     profile.team = None
        #     profile.save()


# ------------------------ Roles (Simplified/Removed) ------------------------
# The standalone Role model might be unnecessary if roles are context-specific (like TaskUserRole).
# If you need system-wide roles (e.g., 'Manager', 'Agent'), keep it or use Django's Group model.
# For this refactor, assuming TaskUserRole is sufficient for task context.
# class Role(models.Model):
#     name = models.CharField(max_length=50, unique=True, verbose_name=_("Название роли"), db_index=True)
#     # Consider adding permissions here if using custom role system
#     # permissions = models.ManyToManyField(Permission, blank=True)
#     class Meta:
#         verbose_name = _("Системная Роль")
#         verbose_name_plural = _("Системные Роли")
#         ordering = ["name"]
#     def __str__(self):
#         return self.name


# ------------------------ User Roles within Tasks ------------------------
class TaskUserRole(BaseModel):
    """Defines a user's specific role within a particular task."""
    class RoleChoices(models.TextChoices):
        # Renamed for clarity and added Responsible
        RESPONSIBLE = "responsible", _("Ответственный") # The main person accountable
        EXECUTOR = "executor", _("Исполнитель") # Those doing the work
        WATCHER = "watcher", _("Наблюдатель") # Those observing progress
        # CREATOR = "creator", _("Создатель") # Can be implicit via Task.created_by
        # Add other roles like REVIEWER, etc. if needed

    task = models.ForeignKey(
        "tasks.Task", # Use string notation to avoid circular imports
        on_delete=models.CASCADE,
        related_name="user_roles", # Changed related_name
        verbose_name=_("Задача"),
        db_index=True
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="task_roles", # Keep related_name on User model
        verbose_name=_("Пользователь"),
        db_index=True
    )
    role = models.CharField(
        max_length=20,
        choices=RoleChoices.choices,
        verbose_name=_("Роль"),
        db_index=True
    )
    # created_at/updated_at inherited from BaseModel

    class Meta:
        verbose_name = _("Роль пользователя в задаче")
        verbose_name_plural = _("Роли пользователей в задачах")
        # A user should have only one specific role per task.
        # If multiple roles are allowed (e.g., someone is both Executor and Watcher), remove this constraint.
        unique_together = ("task", "user")
        ordering = ['task__id', 'user__username'] # Sensible default ordering
        indexes = [
            models.Index(fields=["task", "user"], name="taskuserrole_task_user_idx", ),
            models.Index(fields=["task", "role"], name="taskuserrole_task_role_idx"),
            models.Index(fields=["user", "role"], name="taskuserrole_user_role_idx"),
        ]

    def __str__(self):
        task_display = self.task.task_number or f"Task {self.task_id}"
        user_display = self.user.display_name
        return f"{user_display} - {self.get_role_display()} в {task_display}"