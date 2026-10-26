from django.db import models


class PageAccess(models.Model):
    class Meta:
        managed = False
        default_permissions = ()
        verbose_name = "Page access"

        permissions = (
            ("view_dashboard", "Can view dashboard"),
            ("view_analytics", "Can view analytics"),
            ("view_briefing", "Can view briefing"),
            ("view_equipment", "Can view equipment"),
            ("view_dpmu", "Can view dpmu"),
            ("manage_settings", "Can manage settings"),
            ("manage_users", "Can manage users"),
        )