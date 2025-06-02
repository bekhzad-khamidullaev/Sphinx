# qrfikr/services/review_task_service.py
from django.conf import settings
from django.utils.translation import gettext_lazy as _
from django.urls import reverse
import logging

# Conditional imports based on app availability
try:
    from tasks.models import Task, Project, TaskCategory, TaskAssignment
    from user_profiles.models import User
except ImportError:
    Task, Project, TaskCategory, User, TaskAssignment = None, None, None, None, None
    logging.warning("qrfikr.services: tasks or user_profiles models not fully available.")

from qrfikr.models import Review

logger = logging.getLogger(__name__)

# Define these templates at the module level or make them configurable via settings
DEFAULT_TASK_TITLE_TEMPLATE = _("Low Rating Feedback: {location_name} - {rating}/5")
DEFAULT_TASK_DESCRIPTION_TEMPLATE = _(
    "A review with a rating of {rating}/5 was submitted for location '{location_name}'.\n\n"
    "Review Details:\n"
    "Text: {review_text}\n"
    "Contact: {contact_info}\n"
    "Submitted: {submitted_at}\n"
    "Link to Review Admin: {review_admin_url}\n"
    "QR Code Link ID: {qr_code_link_id}\n"
    "IP Address: {ip_address}\n"
    "User Agent: {user_agent}\n"
)
REVIEW_ADMIN_URL_NAME = "admin:qrfikr_review_change"

class ReviewTaskService:
    def __init__(self, review_instance: Review):
        if not isinstance(review_instance, Review):
            raise TypeError("review_instance must be an instance of Review model.")
        self.review = review_instance

    def _should_create_task(self) -> bool:
        low_rating_threshold = getattr(settings, 'QRFİKR_LOW_RATING_THRESHOLD', 3)
        return self.review.rating <= low_rating_threshold

    def _get_task_project(self):
        if not Project: return None
        location = self.review.qr_code_link.location
        
        # Check for the specific property on the Location instance
        if hasattr(location, 'default_project_for_issues') and location.default_project_for_issues:
            project_candidate = location.default_project_for_issues
            if isinstance(project_candidate, Project):
                return project_candidate
            elif isinstance(project_candidate, int): # If it returns a PK
                try:
                    return Project.objects.get(pk=project_candidate)
                except Project.DoesNotExist:
                    logger.warning(f"Project with PK {project_candidate} from location.default_project_for_issues not found.")

        default_project_name = getattr(settings, 'QRFİKR_DEFAULT_TASK_PROJECT_NAME', 'Feedback Issues')
        project, created = Project.objects.get_or_create(
            name=default_project_name,
            defaults={'description': _('Default project for feedback-generated tasks')}
        )
        if created:
            logger.info(f"Created default project '{default_project_name}' for feedback tasks.")
        return project

    def _get_responsible_user(self):
        if not User: return None
        location = self.review.qr_code_link.location

        if hasattr(location, 'responsible_user') and location.responsible_user:
            user_candidate = location.responsible_user
            if isinstance(user_candidate, User):
                return user_candidate
            elif isinstance(user_candidate, int): # If it returns a PK
                try:
                    return User.objects.get(pk=user_candidate, is_active=True)
                except User.DoesNotExist:
                     logger.warning(f"User with PK {user_candidate} from location.responsible_user not found or inactive.")

        default_responsible_username = getattr(settings, 'QRFİKR_DEFAULT_RESPONSIBLE_USERNAME', None)
        if default_responsible_username:
            try:
                return User.objects.get(username=default_responsible_username, is_active=True)
            except User.DoesNotExist:
                logger.warning(f"Default responsible user '{default_responsible_username}' not found or inactive.")
        
        # Fallback: try to find any superuser
        # superuser = User.objects.filter(is_superuser=True, is_active=True).first()
        # if superuser: return superuser
        return None


    def _get_task_category(self):
        if not TaskCategory: return None
        default_category_name = getattr(settings, 'QRFİKR_DEFAULT_TASK_CATEGORY_NAME', 'Customer Feedback')
        category, created = TaskCategory.objects.get_or_create(
            name=default_category_name,
            defaults={'description': _('Tasks related to customer feedback via QR codes')}
        )
        if created:
            logger.info(f"Created default task category '{default_category_name}' for feedback tasks.")
        return category

    def create_task_if_needed(self):
        if not Task:
            logger.error("Task model is not available (likely 'tasks' app is not installed or imported correctly). Cannot create task for review.")
            return None

        if not self._should_create_task():
            logger.info(f"Review {self.review.id} rating ({self.review.rating}) is above threshold. No task created.")
            return None

        if self.review.related_task_id: # Check by ID to avoid unnecessary DB hit if already linked
            logger.info(f"Task (ID: {self.review.related_task_id}) already exists for review {self.review.id}. Skipping task creation.")
            return self.review.related_task # Return existing task

        project = self._get_task_project()
        responsible_user = self._get_responsible_user()
        category = self._get_task_category()

        if not project:
            logger.error(f"Cannot create task for review {self.review.id}: Project could not be determined or created.")
            return None
            
        try:
            review_admin_url_path = reverse(REVIEW_ADMIN_URL_NAME, args=[self.review.id])
            base_url = getattr(settings, 'SITE_URL', 'http://localhost:8000').strip('/')
            review_admin_full_url = base_url + review_admin_url_path
        except Exception as e:
            logger.warning(f"Could not generate admin URL for review {self.review.id}: {e}")
            review_admin_full_url = _("Admin link unavailable")

        title = DEFAULT_TASK_TITLE_TEMPLATE.format(
            location_name=self.review.qr_code_link.location.name if self.review.qr_code_link.location else _("Unknown Location"),
            rating=self.review.rating
        )
        
        description = DEFAULT_TASK_DESCRIPTION_TEMPLATE.format(
            rating=self.review.rating,
            location_name=self.review.qr_code_link.location.name if self.review.qr_code_link.location else _("Unknown Location"),
            review_text=self.review.text or _("No text provided."),
            contact_info=self.review.contact_info or _("Not provided."),
            submitted_at=self.review.submitted_at.strftime('%Y-%m-%d %H:%M:%S %Z'),
            review_admin_url=review_admin_full_url,
            qr_code_link_id=str(self.review.qr_code_link_id),
            ip_address=self.review.ip_address or _("N/A"),
            user_agent=self.review.user_agent or _("N/A")
        )
        if self.review.photo and hasattr(self.review.photo, 'url'):
            photo_url = getattr(settings, 'SITE_URL', '').strip('/') + self.review.photo.url
            description += f"\n{_('Photo attached')}: {photo_url}"

        task_status_default = getattr(settings, 'QRFİKR_DEFAULT_TASK_STATUS', 'new')
        # Ensure the default status is valid, otherwise fallback to a known safe default
        if task_status_default not in [choice[0] for choice in Task.StatusChoices.choices]:
            logger.warning(f"Invalid QRFİKR_DEFAULT_TASK_STATUS '{task_status_default}'. Falling back to 'new'.")
            task_status_default = 'new'

        task_priority_default = getattr(settings, 'QRFİKR_DEFAULT_TASK_PRIORITY', 3) # Assuming 3 is Medium
        # Ensure the default priority is valid
        if task_priority_default not in [choice[0] for choice in Task.TaskPriority.choices]:
            logger.warning(f"Invalid QRFİKR_DEFAULT_TASK_PRIORITY '{task_priority_default}'. Falling back to Medium (3).")
            task_priority_default = 3


        task_data = {
            'title': title[:255],
            'description': description,
            'project': project,
            'status': task_status_default,
            'priority': task_priority_default,
            'category': category,
            # 'created_by': Set if you have a system user, or leave as None
        }
        
        try:
            # Use a system user if available, otherwise task created anonymously or by logic in Task.save()
            system_user_name = getattr(settings, 'QRFİKR_TASK_CREATOR_USERNAME', None)
            system_user = None
            if system_user_name and User:
                try:
                    system_user = User.objects.get(username=system_user_name)
                    task_data['created_by'] = system_user
                except User.DoesNotExist:
                    logger.warning(f"System user '{system_user_name}' for task creation not found.")
            
            task = Task.objects.create(**task_data)
            logger.info(f"Created task {task.id if task else 'N/A'} for review {self.review.id}.")

            if task and responsible_user and TaskAssignment:
                TaskAssignment.objects.create(
                    task=task,
                    user=responsible_user,
                    role=TaskAssignment.RoleChoices.RESPONSIBLE, 
                    assigned_by=system_user # Task creator can be the assigner
                )
                logger.info(f"Assigned {responsible_user.username} as responsible for task {task.id if task else 'N/A'}")
            
            if task:
                self.review.related_task = task
                self.review.save(update_fields=['related_task'])
            return task
        except Exception as e:
            logger.exception(f"Error creating task or assignment for review {self.review.id}: {e}")
            return None

def create_task_from_review_if_needed(review_instance: Review):
    service = ReviewTaskService(review_instance)
    return service.create_task_if_needed()