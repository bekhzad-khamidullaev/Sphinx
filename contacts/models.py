from django.db import models
from django.contrib.auth.models import User
from django.conf import settings
from datetime import datetime

class Account(models.Model):
    name = models.CharField(max_length=100)

class Contact(models.Model):
    first_name = models.CharField(max_length=20)
    last_name = models.CharField(max_length=20)
    email = models.EmailField(unique=True)
    avatar = models.ImageField(default='', upload_to='static/images/profile_pics/')
    phone = models.CharField(max_length=20)
    mobile = models.CharField(max_length=20, blank=True, null=True)
    address_line = models.CharField(max_length=40, blank=True, null=True)
    addr_state = models.CharField(max_length=40, blank=True, null=True)
    addr_city = models.CharField(max_length=40, blank=True, null=True)
    post_code = models.CharField(max_length=20, blank=True, null=True)
    country = models.CharField(max_length=40, blank=True, null=True)
    notes = models.CharField(max_length=200, blank=True, null=True)
    account = models.ForeignKey(Account, on_delete=models.CASCADE)
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    date_created = models.DateTimeField(default=datetime.utcnow)

    def get_contact_name(self):
        return f"{self.first_name} {self.last_name}"

    def __str__(self):
        return f"Contact('{self.last_name}', '{self.email}', '{self.phone}')"

    @staticmethod
    def contact_list_query(account_id=None, user=None):
        if user.is_superuser:
            contacts = Contact.objects.all()
            if account_id:
                contacts = contacts.filter(account_id=account_id)
        else:
            contacts = Contact.objects.filter(owner=user)
            if account_id:
                contacts = contacts.filter(account_id=account_id)
        return contacts

    @staticmethod
    def get_label(contact):
        return f"{contact.first_name} {contact.last_name}"

    @staticmethod
    def get_contact(contact_id):
        return Contact.objects.filter(id=contact_id).first()

    def __str__(self):
        return f'{self.first_name} {self.last_name}'