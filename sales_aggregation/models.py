from django.db import models

# Create your models here.
class LedgerAccount(models.Model):
	name = models.CharField(max_length=255)
	description = models.TextField()
	canonical_name = models.CharField(max_length=255, null=True, blank=True)
	byd_gl_code = models.CharField(max_length=20)

	def __str__(self,):
		return self.name