from django.urls import path, include
from .views import search_store, get_all_stores
from core_services.views import CustomTokenObtainPairView
from sales_aggregation.views import record_sales

urlpatterns = [
	# Token authentication endpoint
	path('authenticate', CustomTokenObtainPairView.as_view(), name='token_obtain_pair'),
	# Sales endpoints
	path('sales', record_sales, name='record-sale'),
	# Store endpoints
	path('store', search_store, name='search-store'),
	path('stores', get_all_stores, name='get-all-stores'),
]