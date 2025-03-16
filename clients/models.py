from django.db import models

class Client(models.Model):
    name = models.CharField(max_length=200)
    contact_person = models.CharField(max_length=200, blank=True)
    email = models.EmailField(blank=True)
    phone = models.CharField(max_length=20, blank=True)

    def __str__(self):
        return self.name

class Interaction(models.Model):
    client = models.ForeignKey(Client, on_delete=models.CASCADE, related_name='interactions')
    date = models.DateTimeField(auto_now_add=True)
    type = models.CharField(max_length=100)  # e.g., "Call", "Email", "Meeting"
    notes = models.TextField()

    def __str__(self):
        return f"{self.type} with {self.client.name} on {self.date}"