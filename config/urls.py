"""
URL configuration for config project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/6.1/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.urls import include, path
from django.views.generic import RedirectView, TemplateView
from django.conf import settings
from django.conf.urls.static import static
from django.contrib.auth import views as auth_views
from apps.dashboard.views import DashboardLoginView

urlpatterns = [
    path('admin/', admin.site.urls),
    path('favicon.ico', RedirectView.as_view(url=settings.STATIC_URL + 'favicon/autoliv.ico', permanent=False)),
    path('', TemplateView.as_view(template_name='dashboard/index.html'), name='dashboard'),
    path('briefing/', include('apps.briefing.urls')),
    path('equipment/', include('apps.equipment.urls')),
    path('analytics/', include('apps.analytics.urls')),
    path('dpmu/', include('apps.dpmu.urls')),
]

urlpatterns += static(
    settings.STATIC_URL,
    document_root=settings.STATICFILES_DIRS[0]
)

urlpatterns += [
    path(
        'login/',
        DashboardLoginView.as_view(
            template_name='login/login.html'
        ),
        name='login'
    ),

    path(
        'logout/',
        auth_views.LogoutView.as_view(),
        name='logout'
    ),
]
