from rest_framework.decorators import api_view, permission_classes
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from django.db.models import Q
from django.core.exceptions import FieldError

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
	# store_type is a derived @property of store_name, so it maps to the same lookup.
	criteria_mapping = {
		'store_type': 'store_name__icontains',
		'store_name': 'store_name__icontains',
		'icg_warehouse_name': 'icg_warehouse_name__icontains',
	}

	# Build conditions as Q objects so multiple params that resolve to the
	# same ORM lookup (e.g. store_name + store_type) are ANDed together
	# instead of overwriting each other in a kwargs dict.
	q_filter = Q()
	provided_params = []
	for param, value in request.query_params.items():
		if value in (None, ''):
			continue
		provided_params.append(param)
		lookup = criteria_mapping.get(param, param)
		q_filter &= Q(**{lookup: value})

	if not provided_params:
		return APIResponse("No search criteria provided.", status.HTTP_400_BAD_REQUEST)

	# A single non-mapped param is treated as an exact lookup for one store.
	if len(provided_params) == 1 and provided_params[0] not in criteria_mapping:
		try:
			store = Store.objects.get(q_filter)
		except Store.DoesNotExist:
			return APIResponse("No store found for the given criteria.", status.HTTP_404_NOT_FOUND)
		except Store.MultipleObjectsReturned:
			return APIResponse("Multiple stores match the given criteria.", status.HTTP_400_BAD_REQUEST)
		except FieldError:
			return APIResponse(
				f"Unknown search field: '{provided_params[0]}'.",
				status.HTTP_400_BAD_REQUEST,
			)
		return APIResponse('Store retrieved.', status.HTTP_200_OK, data=[StoreSerializer(store).data])
		
	# .filter() is lazy, so FieldError surfaces when the queryset is materialized.
	try:
		queryset = Store.objects.filter(q_filter)
		data = StoreSerializer(queryset, many=True).data
	except FieldError:
		unknown = [p for p in provided_params if p not in criteria_mapping]
		return APIResponse(
			f"Unknown search field(s): {', '.join(unknown) or 'unknown'}.",
			status.HTTP_400_BAD_REQUEST,
		)

	if len(data) > 0:
		return APIResponse('Store retrieved.', status.HTTP_200_OK, data=data)

	return APIResponse("No store found for the given criteria.", status.HTTP_404_NOT_FOUND)
