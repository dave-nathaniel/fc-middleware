from django.contrib import admin
from .models import KeyStore

class KeyStoreAdmin(admin.ModelAdmin):
	readonly_fields = ["created_at"]
	non_editable_fields = ["user", "public_key", "metadata"]
	
	def get_readonly_fields(self, request, obj=None):
		# If the object is being created (obj is None), return the usual readonly_fields
		if obj is None:
			return self.readonly_fields
		# If the object is being updated, add additional fields to readonly_fields
		return self.readonly_fields + self.non_editable_fields


admin.site.register(KeyStore, KeyStoreAdmin)
