from django.contrib.auth.backends import BaseBackend
from django.contrib.auth.models import Permission


class VisitorPermissionBackend(BaseBackend):
    def get_group_permissions(self, user_obj, obj=None):
        if user_obj.is_authenticated or obj is not None:
            return set()
        if not hasattr(user_obj, '_visitor_perm_cache'):
            permissions = Permission.objects.filter(
                group__name='visitor',
                content_type__app_label='accounts',
                content_type__model='pageaccess',
            ).values_list('content_type__app_label', 'codename')
            user_obj._visitor_perm_cache = {
                app_label + '.' + codename for app_label, codename in permissions
            }
        return user_obj._visitor_perm_cache

    def has_module_perms(self, user_obj, app_label):
        return any(
            permission.split('.', 1)[0] == app_label
            for permission in self.get_group_permissions(user_obj)
        )