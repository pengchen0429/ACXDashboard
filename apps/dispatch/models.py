from django.db import models

# Create your models here.
class DispatchPermission(models.Model):

    class Meta:
        managed = False
        default_permissions = ()
        permissions = [
            ("dispatch_view", "Dispatch View"),
            ("dispatch_export", "Dispatch Export"),
        ]