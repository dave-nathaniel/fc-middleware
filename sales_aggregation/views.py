from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from .models import Sale
from store_services.models import Store

from overrides.rest_framework import APIResponse

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def record_sales(request):
	# keys we NEED to create a sale
	required_keys = ["outstanding_amount", "reconciled_amount", "date", "icg_warehouse_code", "signature"]
	# A list of sales to be processed
	sales = request.data
	# Error list to store missing required keys and successful sales
	errors, successful = [], []
	for sale in sales:
		# Check that all the required keys are present in the sale data
		required_keys_present = [
			any(
				map(lambda x: r in x, list(sale.keys()))
			) for r in required_keys
		]
		# If required keys are not present, return an error
		if not all(required_keys_present):
			missing_required_keys = set(required_keys) - set(sale.keys())
			errors.append(f"Missing required keys: {', '.join(missing_required_keys)}")
			continue
		# Try to create a sale, handle exceptions if store not found or other error occurs
		try:
			create_sale(request.user, sale)
			successful.append(sale)
		except Store.DoesNotExist:
			errors.append(f"Store with icg_warehouse_code {sale.get('icg_warehouse_code')} not found.")
		except Exception as e:
			errors.append(f"Error sale for store {sale.get('icg_warehouse_code')} of amount {sale.get('reconciled_amount')}: {str(e)}")
	
	return APIResponse("Requests processed.", status=status.HTTP_200_OK, data={
		'successful': successful,
		'errors': errors
	})
	

def create_sale(user: object, data: dict) -> bool:
	'''
		Creates a sale record with the given data.
		Returns True if the sale is created successfully, False otherwise.
		Assumes that the store for the given icg_warehouse_code exists.
		Raises Store.DoesNotExist if the store is not found.
		Raises any other exceptions that may occur during the sale creation process.
		:param user: The user who posted the sale.
		:param data: The data containing the sale details.
		:return: True if the sale is created successfully, False otherwise.
		:rtype: bool
		:raises Store.DoesNotExist: If the store for the given icg_warehouse_code does not exist.
		:raises Exception: If any other error occurs during the sale creation process.
		:raises Sale.ValidationError: If the data does not pass validation.
		:raises Sale.IntegrityError: If there is a database integrity error during the sale creation process.
	'''
	sale = Sale()
	# Get the store for the given icg_warehouse_code and set it on the sale object.
	icg_warehouse_code = data.get('icg_warehouse_code')
	store = Store.objects.get(icg_warehouse_code=icg_warehouse_code)
	sale.store = store
	# Set the authenticated user as the posted_by on the sale object.
	sale.posted_by = user
	# Convert the reconciled and outstanding amounts to float and set them on the sale object.
	sale.reconciled_gross_total = float(data.get('reconciled_amount'))
	sale.outstanding_gross_total = float(data.get('outstanding_amount'))
	# Set the date the sale was made on the sale object.
	sale.sale_date = data.get('date')
	# Set the signature of the sale on the sale object.
	sale.signature = data.get('signature')
	# Try to, verify, calculate and save the sales data
	try:
		sale.save()
		return True
	except Exception as e:
		raise e
	
	