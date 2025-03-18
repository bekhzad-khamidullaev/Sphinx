# crm/asgi.py
import os

# Set the DJANGO_SETTINGS_MODULE *before* calling django.setup() or importing any Django components.
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')

import django
django.setup()

from django.core.asgi import get_asgi_application
from channels.routing import ProtocolTypeRouter, URLRouter
from channels.auth import AuthMiddlewareStack
import tasks.routing
import room.routing

application = ProtocolTypeRouter({
    "http": get_asgi_application(),
    "websocket": AuthMiddlewareStack(
        URLRouter(
            tasks.routing.websocket_urlpatterns +
            room.routing.websocket_urlpatterns
        )
    ),
})