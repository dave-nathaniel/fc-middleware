from rest_framework.decorators import api_view, permission_classes
from rest_framework import status
from django.db.models import Q
from rest_framework.permissions import IsAuthenticated

from store_services.models import Store
from .serializers.store_serializer import StoreSerializer

from overrides.rest_framework import APIResponse


# function based view to get all stores
@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_all_stores(request, *args, **kwargs):
	queryset = Store.objects.all()
	serializer = StoreSerializer(queryset, many=True)
	
	if len(serializer.data) > 0:
		return APIResponse(f'{len(serializer.data)} stores retrieved.', status.HTTP_200_OK, data=serializer.data)
	
	return APIResponse("No stores found.", status.HTTP_404_NOT_FOUND)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def search_store(request, *args, **kwargs):
	criteria = list(request.query_params.keys())[0]
	value = request.query_params.get(criteria)
	
	criteria_mapping = {
		'icg_warehouse_code': 'icg_warehouse_code',
		'byd_cost_center_code': 'byd_cost_center_code',
		'store_type': 'store_name__icontains',
		'store_name': 'store_name__icontains',
		'icg_warehouse_name': 'icg_warehouse_name__icontains',
		# Add more criteria as needed
	}
	
	# Use Q objects for OR conditions
	query_filters = Q()
	if criteria in criteria_mapping:
		query_filters |= Q(**{criteria_mapping[criteria]: value})
	
	# Apply filters to the queryset
	queryset = Store.objects.filter(query_filters)
	serializer = StoreSerializer(queryset, many=True)
	
	if len(serializer.data) > 0:
		return APIResponse('Store retrieved.', status.HTTP_200_OK, data=serializer.data)
	
	return APIResponse("No store found for the given criteria.", status.HTTP_404_NOT_FOUND)
