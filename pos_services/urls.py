from django.urls import path

from . import views

# Mounted under /api/v1/pos/
urlpatterns = [
	path("purchase-orders", views.purchase_order, name="pos-purchase-order"),
	path("purchase-orders/link", views.link_purchase_orders, name="pos-purchase-order-link"),
	path("grns", views.grn, name="pos-grn"),
	path("vendor-returns", views.vendor_return, name="pos-vendor-return"),
	path("wastage", views.wastage, name="pos-wastage"),
]

# Mounted under /srp-feed/ : the same paths ICG exposes, so the SRP only changes its base URL.
feed_urlpatterns = [
	path("token", views.feed_token, name="srp-feed-token"),
	path("api/FoodConcept/StoreRequest/<str:day>", views.store_requests, name="srp-feed-store-requests"),
]
