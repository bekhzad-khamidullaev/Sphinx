# clients/views.py
from rest_framework import viewsets, permissions
from .models import Client, Interaction
from .serializers import ClientSerializer, InteractionSerializer
from django.db.models import Q

class ClientViewSet(viewsets.ModelViewSet):
    queryset = Client.objects.all()
    serializer_class = ClientSerializer
    permission_classes = [permissions.IsAuthenticated]


class InteractionViewSet(viewsets.ModelViewSet):
    serializer_class = InteractionSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
      clientId = self.kwargs['client_pk']
      return Interaction.objects.filter(client__id = clientId)

    def perform_create(self, serializer):
        client = Client.objects.get(pk=self.kwargs['client_pk'])
        serializer.save(client=client)