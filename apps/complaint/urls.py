from django.contrib.auth.decorators import login_required
from django.urls import path
from django.views.decorators.cache import never_cache
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.generic import TemplateView

from . import views

urlpatterns = [
	path('', never_cache(login_required(ensure_csrf_cookie(TemplateView.as_view(template_name='complaint/complaint.html')), login_url='login')), name='complaint'),
	path('records/', views.complaint_records, name='complaint-records'),
	path('records/<int:no>/', views.complaint_record, name='complaint-record'),
	path('images/', views.complaint_images, name='complaint-images'),
	path('images/<str:name>/', views.complaint_image, name='complaint-image'),
	path('export/', views.complaint_export, name='complaint-export'),
]
