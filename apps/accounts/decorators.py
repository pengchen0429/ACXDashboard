from functools import wraps

from django.contrib.auth.views import redirect_to_login
from django.core.exceptions import PermissionDenied
from django.urls import reverse


def page_permission_required(codename):
    def decorate(view):
        @wraps(view)
        def protected_view(request, *args, **kwargs):
            if request.user.has_perm('accounts.' + codename):
                return view(request, *args, **kwargs)
            if request.user.is_authenticated:
                raise PermissionDenied
            return redirect_to_login(request.get_full_path(), login_url=reverse('login'))
        return protected_view
    return decorate