from django.test import TestCase
from agents.models import Agent

class AgentModelTests(TestCase):
    def test_str(self):
        agent = Agent.objects.create(name='Test', phone_number='123', email='test@example.com')
        self.assertEqual(str(agent), 'Test')
