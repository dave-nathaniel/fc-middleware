# serializers.py
from rest_framework import serializers
from store_services.models import Store

class StoreSerializer(serializers.ModelSerializer):
	class Meta:
		model = Store
		fields = '__all__'