from django.urls import path, include
from .views import search_store, get_all_stores


urlpatterns = [
	path('store', search_store, name='search-store'),
	path('stores', get_all_stores, name='get-all-stores'),
]