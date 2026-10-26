from django.db import models


class PageAccess(models.Model):
	id = models.BigAutoField(primary_key=True)

	class Meta:
		managed = False
		default_permissions = ()
		permissions = (
			('view_equipment', 'Can view equipment page'),
			('view_dpmu', 'Can view DPMU page'),
		)
		verbose_name = 'Page access'
