#clients/urls.py
from rest_framework_nested import routers
from .views import ClientViewSet, InteractionViewSet


router = routers.SimpleRouter()
router.register(r'clients', ClientViewSet)

app_name = 'clients'

clients_router = routers.NestedSimpleRouter(router, r'clients', lookup='client')
clients_router.register(r'interactions', InteractionViewSet, basename='client-interactions')


urlpatterns = router.urls + clients_router.urls