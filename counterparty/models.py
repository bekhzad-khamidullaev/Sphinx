from django.db import models
from contacts.models import Contact
from datetime import datetime
from config import settings
from phonenumber_field.modelfields import PhoneNumberField


class Counterparty(models.Model):
    name = models.CharField(max_length=200)
    contact = models.ForeignKey(Contact, on_delete=models.CASCADE, related_name='counterparty')
    phone = PhoneNumberField(null=True, blank=True, unique=True)
    mobile = PhoneNumberField(null=True, blank=True, unique=True)
    address_line = models.CharField(max_length=40, blank=True, null=True)
    addr_state = models.CharField(max_length=40, blank=True, null=True)
    addr_city = models.CharField(max_length=40, blank=True, null=True)
    post_code = models.CharField(max_length=20, blank=True, null=True)
    country = models.CharField(max_length=40, blank=True, null=True)
    notes = models.CharField(max_length=200, blank=True, null=True)
    # responsible = models.ForeignKey(Contact.responsible, on_delete=models.SET_NULL, null=True, blank=True, related_name='responsible_counterparties')
    date_created = models.DateTimeField(default=datetime.utcnow)

    def get_counterparty_name(self):
        return f"{self.name}"

    @staticmethod
    def counterparty_list_query(pk=None, user=None):
        if user.is_superuser:
            counterpartys = Counterparty.objects.all()
            if pk:
                counterpartys = counterpartys.filter(pk=pk)
        else:
            counterpartys = Contact.objects.filter(owner=user)
            if pk:
                counterpartys = counterpartys.filter(pk=pk)
        return counterpartys

    @staticmethod
    def get_label(counterparty):
        return f"{counterparty.name}"

    @staticmethod
    def get_contact(pk):
        return Counterparty.objects.filter(pk=pk).first()

    def __str__(self):
        return f'{self.name}'