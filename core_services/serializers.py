import logging
from django.contrib.auth import get_user_model
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer

User = get_user_model()


class RelatedObjectDoesNotExist:
	pass


class CustomTokenObtainPairSerializer(TokenObtainPairSerializer):
	
	def get_user_data(self, user):
		user_data = {
			'id': user.id,
			'username': user.username,
			'first_name': user.first_name,
			'last_name': user.last_name,
			'email': user.email
		}
		
		return user_data
	
	@classmethod
	def get_token(cls, user):
		token = super().get_token(user)
		# Add custom claims to the token
		token['user'] = cls.get_user_data(cls, user)
		return token
	
	def validate(self, attrs):
		data = super().validate(attrs)
		user = self.user or self.context['request'].user
		# Include user information in the response
		data['user'] = self.get_user_data(user)
		return data
	
	class Meta:
		model = User
		fields = '__all__'
