"""
Endpoints for the Restroworks POS integration.

POS -> middleware (Restroworks webhooks, HTTP Basic auth, user in group "restroworks"):
	POST /api/v1/pos/purchase-orders
	POST /api/v1/pos/grns
	POST /api/v1/pos/vendor-returns
	POST /api/v1/pos/wastage
	POST /api/v1/pos/sales
	Every reply is HTTP 200 with {"Status": "Success"} or {"Status": "Fail", "Reason": "..."},
	as the Restroworks specification requires.

SRP -> middleware (user in group "store_requisition"):
	POST /api/v1/pos/purchase-orders/link          (Basic or JWT) ByD document created for POS POs
	POST /srp-feed/token                            ICG-compatible token endpoint
	GET  /srp-feed/api/FoodConcept/StoreRequest/<date>  ICG-compatible store requests feed

Blue Prism -> middleware (user in group "blue_prism"):
	POST /sales-feed/token                          ICG-compatible token endpoint
	GET  /sales-feed/api/FoodConcept/Sales/<date>   ICG-compatible sales feed
"""
import logging
from datetime import date, timedelta

from django.contrib.auth import authenticate
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes, authentication_classes, throttle_classes
from rest_framework.permissions import AllowAny, BasePermission
from rest_framework.response import Response
from rest_framework.throttling import AnonRateThrottle
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework_simplejwt.exceptions import InvalidToken, TokenError
from rest_framework_simplejwt.tokens import AccessToken

from overrides.rest_framework import APIResponse
from . import services
from .serializers import (
	PurchaseOrderSerializer, GRNSerializer, VendorReturnSerializer, WastageSerializer, SalesSerializer, LinkSerializer,
	first_error,
)

logger = logging.getLogger(__name__)

# SRP caches its ICG token for 13 days; issue feed tokens that outlive that cache.
FEED_TOKEN_LIFETIME = timedelta(days=14)

# Django groups that may call each side of the integration (superusers always may).
RESTROWORKS_GROUP = "restroworks"
SRP_GROUP = "store_requisition"
BLUE_PRISM_GROUP = "blue_prism"


def _in_group(user, group):
	return bool(user and user.is_authenticated and (user.is_superuser or user.groups.filter(name=group).exists()))


class IsRestroworks(BasePermission):
	def has_permission(self, request, view):
		return _in_group(request.user, RESTROWORKS_GROUP)


class IsStoreRequisitionPortal(BasePermission):
	def has_permission(self, request, view):
		return _in_group(request.user, SRP_GROUP)


class IsBluePrism(BasePermission):
	def has_permission(self, request, view):
		return _in_group(request.user, BLUE_PRISM_GROUP)


class FeedToken(AccessToken):
	"""
		A token that only opens the ICG-compatible feeds (SRP and sales). Its own token type
		means the default JWT authentication (which accepts access tokens only) rejects it
		everywhere else. Each feed also checks the caller's group.
	"""
	token_type = "srp_feed"
	lifetime = FEED_TOKEN_LIFETIME


class FeedTokenAuthentication(JWTAuthentication):
	def get_validated_token(self, raw_token):
		try:
			return FeedToken(raw_token)
		except TokenError as e:
			raise InvalidToken({"detail": str(e)})


class FeedTokenThrottle(AnonRateThrottle):
	rate = "30/hour"


def pos_reply(ok, reason=None, **extra):
	body = {"Status": "Success" if ok else "Fail"}
	if not ok:
		body["Reason"] = reason
	body.update(extra)
	return Response(body, status=status.HTTP_200_OK)


def _pos_webhook(serializer_class, handler, request):
	if not isinstance(request.data, dict):
		return pos_reply(False, "The request body must be a JSON object.")
	serializer = serializer_class(data=request.data)
	if not serializer.is_valid():
		return pos_reply(False, first_error(serializer.errors))
	try:
		ok, reason, extra = handler(serializer.validated_data, request.data, serializer.data)
	except Exception:
		logger.exception(f"POS webhook {request.path} failed")
		return pos_reply(False, "Middleware error while storing the document. It has not been accepted; please retry.")
	if not ok:
		logger.warning(f"POS webhook {request.path} rejected: {reason}")
	return pos_reply(ok, reason, **extra)


@api_view(["POST"])
@permission_classes([IsRestroworks])
def purchase_order(request):
	return _pos_webhook(PurchaseOrderSerializer, services.receive_purchase_order, request)


@api_view(["POST"])
@permission_classes([IsRestroworks])
def grn(request):
	return _pos_webhook(GRNSerializer, services.receive_grn, request)


@api_view(["POST"])
@permission_classes([IsRestroworks])
def vendor_return(request):
	return _pos_webhook(VendorReturnSerializer, services.receive_vendor_return, request)


@api_view(["POST"])
@permission_classes([IsRestroworks])
def wastage(request):
	return _pos_webhook(WastageSerializer, services.receive_wastage, request)


@api_view(["POST"])
@permission_classes([IsRestroworks])
def sales(request):
	return _pos_webhook(SalesSerializer, services.receive_sales, request)


@api_view(["POST"])
@permission_classes([IsStoreRequisitionPortal])
def link_purchase_orders(request):
	serializer = LinkSerializer(data=request.data)
	if not serializer.is_valid():
		return APIResponse(first_error(serializer.errors), status.HTTP_400_BAD_REQUEST)
	linked, unmatched = services.link_byd_document(serializer.validated_data)
	return APIResponse(
		f"Linked {len(linked)} POS purchase order(s) to ByD {serializer.validated_data['document_id']}.",
		status.HTTP_200_OK,
		data={"linked": linked, "unmatched": unmatched},
	)


# ----------------------------------------------------------------------------
# ICG-compatible feeds: store requests for the SRP, sales for Blue Prism
# ----------------------------------------------------------------------------
def _issue_feed_token(request, group):
	"""OAuth2 password-grant style token endpoint, matching what callers send to ICG's /token."""
	user = authenticate(username=request.data.get("username"), password=request.data.get("password"))
	if request.data.get("grant_type") != "password" or user is None or not user.is_active or not _in_group(user, group):
		return Response({"error": "invalid_grant", "error_description": "The user name or password is incorrect."}, status=status.HTTP_400_BAD_REQUEST)
	token = FeedToken.for_user(user)
	return Response({
		"access_token": str(token),
		"token_type": "bearer",
		"expires_in": int(FEED_TOKEN_LIFETIME.total_seconds()),
	})


def _feed_for_day(day, build):
	try:
		requested = date.fromisoformat(day)
	except ValueError:
		return Response({"message": "The date must be YYYY-MM-DD."}, status=status.HTTP_400_BAD_REQUEST)
	return Response(build(requested))


@api_view(["POST"])
@authentication_classes([])
@permission_classes([AllowAny])
@throttle_classes([FeedTokenThrottle])
def feed_token(request):
	return _issue_feed_token(request, SRP_GROUP)


@api_view(["GET"])
@authentication_classes([FeedTokenAuthentication])
@permission_classes([IsStoreRequisitionPortal])
def store_requests(request, day):
	return _feed_for_day(day, services.store_requests_for)


@api_view(["POST"])
@authentication_classes([])
@permission_classes([AllowAny])
@throttle_classes([FeedTokenThrottle])
def sales_feed_token(request):
	return _issue_feed_token(request, BLUE_PRISM_GROUP)


@api_view(["GET"])
@authentication_classes([FeedTokenAuthentication])
@permission_classes([IsBluePrism])
def sales_feed(request, day):
	return _feed_for_day(day, services.sales_for)
