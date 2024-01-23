from django.urls import path, include
from .views import StoreAPIView


urlpatterns = [
	path('store', StoreAPIView.as_view(), name='user-registration'),
]