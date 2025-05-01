from django.test import TestCase
from django.urls import reverse
from django.contrib.auth import get_user_model
from .models import Location, ChecklistPoint, ChecklistTemplate, ChecklistTemplateItem, Checklist, ChecklistResult, AnswerType, ChecklistItemStatus, ChecklistRunStatus

User = get_user_model()

class ChecklistModelTests(TestCase):

    def setUp(self):
        self.user = User.objects.create_user(username='testuser', password='password')
        self.location = Location.objects.create(name='Building A')
        self.point = ChecklistPoint.objects.create(location=self.location, name='Room 101')
        self.template = ChecklistTemplate.objects.create(name='Daily Check', target_location=self.location)
        self.item1 = ChecklistTemplateItem.objects.create(template=self.template, item_text='Check Light', order=1, answer_type=AnswerType.YES_NO)
        self.item2 = ChecklistTemplateItem.objects.create(template=self.template, item_text='Temperature', order=2, answer_type=AnswerType.NUMBER)

    def test_location_creation(self):
        self.assertEqual(Location.objects.count(), 1)
        self.assertEqual(self.location.name, 'Building A')

    def test_checklist_point_creation(self):
        self.assertEqual(ChecklistPoint.objects.count(), 1)
        self.assertEqual(self.point.name, 'Room 101')
        self.assertEqual(self.point.location, self.location)

    def test_checklist_template_creation(self):
        self.assertEqual(ChecklistTemplate.objects.count(), 1)
        self.assertEqual(self.template.name, 'Daily Check')
        self.assertEqual(self.template.target_location, self.location)

    def test_checklist_template_item_creation(self):
        self.assertEqual(ChecklistTemplateItem.objects.count(), 2)
        self.assertEqual(self.item1.item_text, 'Check Light')
        self.assertEqual(self.item1.answer_type, AnswerType.YES_NO)
        self.assertEqual(self.item2.item_text, 'Temperature')
        self.assertEqual(self.item2.answer_type, AnswerType.NUMBER)
        self.assertEqual(self.item1.template, self.template)
        self.assertEqual(self.item2.template, self.template)

    def test_checklist_run_creation_creates_results(self):
        # Creating a checklist run should automatically create results via signal
        checklist_run = Checklist.objects.create(
            template=self.template,
            performed_by=self.user,
            location=self.location,
            point=self.point
        )
        self.assertEqual(Checklist.objects.count(), 1)
        self.assertEqual(ChecklistResult.objects.filter(checklist_run=checklist_run).count(), 2) # Should create results for item1 and item2

        result1 = ChecklistResult.objects.get(checklist_run=checklist_run, template_item=self.item1)
        self.assertEqual(result1.status, ChecklistItemStatus.PENDING) # Default status

    def test_checklist_run_mark_complete(self):
        checklist_run = Checklist.objects.create(template=self.template, performed_by=self.user)
        self.assertFalse(checklist_run.is_complete)
        self.assertEqual(checklist_run.status, ChecklistRunStatus.IN_PROGRESS)

        checklist_run.mark_complete()
        checklist_run.refresh_from_db()

        self.assertTrue(checklist_run.is_complete)
        self.assertEqual(checklist_run.status, ChecklistRunStatus.SUBMITTED)
        self.assertIsNotNone(checklist_run.completion_time)

    def test_checklist_result_display_value(self):
        checklist_run = Checklist.objects.create(template=self.template, performed_by=self.user)
        result1 = ChecklistResult.objects.get(checklist_run=checklist_run, template_item=self.item1) # YES_NO
        result2 = ChecklistResult.objects.get(checklist_run=checklist_run, template_item=self.item2) # NUMBER

        # Test display value for YES_NO
        result1.value = 'yes'
        self.assertEqual(result1.display_value, _('Да'))
        result1.value = 'no'
        self.assertEqual(result1.display_value, _('Нет'))
        result1.value = 'some_other_value' # Should fall back to raw value
        self.assertEqual(result1.display_value, 'some_other_value')
        result1.value = None
        self.assertEqual(result1.display_value, '-') # Default if None/blank

        # Test display value for NUMBER
        result2.numeric_value = 25.5
        self.assertEqual(result2.display_value, 25.5)
        result2.numeric_value = None
        result2.value = 'abc' # Should ignore value if numeric_value is None
        self.assertEqual(result2.display_value, '-')

        # Add tests for other answer types and value fields

# Add tests for views, forms, and signals

# class ChecklistViewTests(TestCase):
#     def setUp(self):
#         self.user = User.objects.create_user(username='testuser', password='password')
#         self.template = ChecklistTemplate.objects.create(name='Test Template')
#         self.client.login(username='testuser', password='password')
#
#     def test_template_list_view(self):
#         response = self.client.get(reverse('checklists:template_list'))
#         self.assertEqual(response.status_code, 200)
#         self.assertContains(response, 'Test Template')

# And so on for other views, forms, and specific logic like filtering and reporting.