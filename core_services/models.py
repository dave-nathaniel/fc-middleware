from django.db import models
from django.contrib.auth import get_user_model

User = get_user_model()
	

class KeyStore(models.Model):
	user = models.OneToOneField(User, on_delete=models.CASCADE, null=True, related_name='user_key_store')
	public_key = models.TextField(null=True, blank=True)
	created_at = models.DateTimeField(auto_now_add=True)
	metadata = models.JSONField(null=True, blank=True)
	
	def __str__(self):
		return f"KeyStore for user '{self.user.username}'"