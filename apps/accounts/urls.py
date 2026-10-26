from django.contrib.auth.views import LogoutView
from django.urls import path
from django.views.decorators.http import require_POST

from .views import AccountsLoginView


urlpatterns = [
	path('login/', AccountsLoginView.as_view(template_name='login/login.html'), name='login'),
	path('logout/', require_POST(LogoutView.as_view(next_page='dashboard')), name='logout'),
]
