# clients/admin.py
from django.contrib import admin
from .models import Client, Interaction

@admin.register(Client)
class ClientAdmin(admin.ModelAdmin):
    list_display = ('name', 'contact_person', 'email', 'phone')
    search_fields = ('name', 'contact_person', 'email', 'phone')

@admin.register(Interaction)
class InteractionAdmin(admin.ModelAdmin):
    list_display = ('client', 'date', 'type', 'notes')
    list_filter = ('client', 'date', 'type')
    search_fields = ('client__name', 'notes')
    autocomplete_fields = ('client',) # Use autocomplete