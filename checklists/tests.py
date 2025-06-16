# checklists/tests.py
import os

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
import django

django.setup()
from django.test import TestCase
from django.urls import reverse
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _
from .filters import ChecklistTemplateFilter
from .models import (
    Location,
    LocationLevel,
    ChecklistPoint,
    ChecklistTemplate,
    ChecklistTemplateItem,
    Checklist,
    ChecklistResult,
    AnswerType,
    ChecklistItemStatus,
    ChecklistRunStatus,
)

User = get_user_model()


class ChecklistModelTests(TestCase):

    def setUp(self):
        self.user = User.objects.create_user(username="testuser", password="password")
        self.location = Location.objects.create(name="Building A")
        self.point = ChecklistPoint.objects.create(
            location=self.location, name="Room 101"
        )
        self.template = ChecklistTemplate.objects.create(
            name="Daily Check", target_location=self.location
        )
        self.item1 = ChecklistTemplateItem.objects.create(
            template=self.template,
            item_text="Check Light",
            order=1,
            answer_type=AnswerType.YES_NO,
        )
        self.item2 = ChecklistTemplateItem.objects.create(
            template=self.template,
            item_text="Temperature",
            order=2,
            answer_type=AnswerType.NUMBER,
        )

    def test_location_creation(self):
        self.assertEqual(Location.objects.count(), 1)
        self.assertEqual(self.location.name, "Building A")

    def test_location_hierarchy_full_name(self):
        room = Location.objects.create(
            name="Hall", parent=self.location, level=LocationLevel.ROOM
        )
        corner = Location.objects.create(
            name="Corner", parent=room, level=LocationLevel.AREA
        )
        self.assertEqual(room.full_name, "Building A / Hall")
        self.assertEqual(corner.full_name, "Building A / Hall / Corner")

    def test_parent_level_validation(self):
        room = Location.objects.create(
            name="Hall", parent=self.location, level=LocationLevel.ROOM
        )
        with self.assertRaises(ValidationError):
            invalid = Location(name="Invalid", parent=room, level=LocationLevel.VENUE)
            invalid.full_clean()


    def test_checklist_point_creation(self):
        self.assertEqual(ChecklistPoint.objects.count(), 1)
        self.assertEqual(self.point.name, "Room 101")
        self.assertEqual(self.point.location, self.location)

    def test_checklist_template_creation(self):
        self.assertEqual(ChecklistTemplate.objects.count(), 1)
        self.assertEqual(self.template.name, "Daily Check")
        self.assertEqual(self.template.target_location, self.location)

    def test_checklist_template_item_creation(self):
        self.assertEqual(ChecklistTemplateItem.objects.count(), 2)
        self.assertEqual(self.item1.item_text, "Check Light")
        self.assertEqual(self.item1.answer_type, AnswerType.YES_NO)
        self.assertEqual(self.item2.item_text, "Temperature")
        self.assertEqual(self.item2.answer_type, AnswerType.NUMBER)
        self.assertEqual(self.item1.template, self.template)
        self.assertEqual(self.item2.template, self.template)

    def test_checklist_run_creation_creates_results(self):
        checklist_run = Checklist.objects.create(
            template=self.template,
            performed_by=self.user,
            location=self.location,
            point=self.point,
        )
        self.assertEqual(Checklist.objects.count(), 1)
        self.assertEqual(
            ChecklistResult.objects.filter(checklist_run=checklist_run).count(), 2
        )

        result1 = ChecklistResult.objects.get(
            checklist_run=checklist_run, template_item=self.item1
        )
        self.assertEqual(result1.status, ChecklistItemStatus.PENDING)

    def test_checklist_run_mark_complete(self):
        checklist_run = Checklist.objects.create(
            template=self.template,
            performed_by=self.user,
            status=ChecklistRunStatus.IN_PROGRESS,
        )
        self.assertFalse(checklist_run.is_complete)
        self.assertEqual(checklist_run.status, ChecklistRunStatus.IN_PROGRESS)

        checklist_run.mark_complete()
        checklist_run.refresh_from_db()

        self.assertTrue(checklist_run.is_complete)
        self.assertEqual(checklist_run.status, ChecklistRunStatus.SUBMITTED)
        self.assertIsNotNone(checklist_run.completion_time)

    def test_checklist_result_display_value(self):
        checklist_run = Checklist.objects.create(
            template=self.template, performed_by=self.user
        )
        result1 = ChecklistResult.objects.get(
            checklist_run=checklist_run, template_item=self.item1
        )
        result2 = ChecklistResult.objects.get(
            checklist_run=checklist_run, template_item=self.item2
        )

        result1.value = "yes"
        # Очищаем кэш свойства, если он есть (в реальном коде этого не нужно)
        if hasattr(result1, "_display_value_cache"):
            delattr(result1, "_display_value_cache")
        self.assertEqual(result1.display_value, _("Да"))

        result1.value = "no"
        if hasattr(result1, "_display_value_cache"):
            delattr(result1, "_display_value_cache")
        self.assertEqual(result1.display_value, _("Нет"))

        result1.value = "some_other_value"
        if hasattr(result1, "_display_value_cache"):
            delattr(result1, "_display_value_cache")
        self.assertEqual(result1.display_value, "some_other_value")

        result1.value = None
        if hasattr(result1, "_display_value_cache"):
            delattr(result1, "_display_value_cache")
        self.assertEqual(result1.display_value, "-")

        result2.numeric_value = 25.5
        if hasattr(result2, "_display_value_cache"):
            delattr(result2, "_display_value_cache")
        self.assertEqual(result2.display_value, 25.5)

        result2.numeric_value = None
        result2.value = "abc"  # Должен показать '-', так как numeric_value приоритетнее для NUMBER типа
        if hasattr(result2, "_display_value_cache"):
            delattr(result2, "_display_value_cache")
        self.assertEqual(result2.display_value, "abc")


class ChecklistPermissionTests(TestCase):
    def setUp(self):

        self.performer = User.objects.create_user('performer', password='pw', email='performer@example.com')
        self.confirm_user = User.objects.create_user('confirmer', password='pw', email='confirmer@example.com')
        self.confirm_user.is_staff = True
        self.confirm_user.save()
        perm = Permission.objects.get(codename='confirm_checklist')

        self.confirm_user.user_permissions.add(perm)

        self.location = Location.objects.create(name="Loc")
        self.template = ChecklistTemplate.objects.create(
            name="Tmp", target_location=self.location
        )
        ChecklistTemplateItem.objects.create(
            template=self.template,
            item_text="Q1",
            order=1,
            answer_type=AnswerType.YES_NO,
        )
        self.checklist = Checklist.objects.create(
            template=self.template,
            performed_by=self.performer,
            location=self.location,
            status=ChecklistRunStatus.IN_PROGRESS,
        )
        self.result = self.checklist.results.first()

    def _post_data(self):
        return {
            "checklist_run_id": str(self.checklist.pk),
            "results-TOTAL_FORMS": "1",
            "results-INITIAL_FORMS": "1",
            "results-MIN_NUM_FORMS": "0",
            "results-MAX_NUM_FORMS": "1000",
            "results-0-id": str(self.result.pk),
            "results-0-status": ChecklistItemStatus.OK,
            "results-0-value": "yes",
            "results-0-comments": "",
            "results-0-is_corrected": "",
            "action": "submit_final",
        }

    def test_confirm_requires_permission(self):
        url = reverse(
            "checklists:checklist_perform", kwargs={"template_pk": self.template.pk}
        )

        self.client.login(username="performer", password="pw")
        self.client.post(url, self._post_data())
        self.checklist.refresh_from_db()
        self.assertNotEqual(self.checklist.status, ChecklistRunStatus.SUBMITTED)

        self.client.logout()
        self.client.login(username="confirmer", password="pw")
        self.client.post(url, self._post_data())
        self.checklist.refresh_from_db()
        self.assertEqual(self.checklist.status, ChecklistRunStatus.SUBMITTED)


class TemplateFilterTests(TestCase):

    def setUp(self):
        self.location = Location.objects.create(name="L1")
        self.t1 = ChecklistTemplate.objects.create(
            name="Alpha", target_location=self.location, is_active=True
        )
        self.t2 = ChecklistTemplate.objects.create(
            name="Beta", target_location=self.location, is_active=False
        )

    def test_filter_by_name(self):
        f = ChecklistTemplateFilter(
            {"name": "Alpha"}, queryset=ChecklistTemplate.objects.all()
        )
        self.assertEqual(list(f.qs), [self.t1])

    def test_filter_by_active(self):
        f = ChecklistTemplateFilter(
            {"is_active": "True"}, queryset=ChecklistTemplate.objects.all()
        )
        self.assertEqual(list(f.qs), [self.t1])
