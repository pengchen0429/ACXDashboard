from django.urls import path

from . import views


urlpatterns = [
	path('', views.dpmu, name='dpmu'),
	path('options/', views.options, name='dpmu-options'),
	path('data/', views.data, name='dpmu-data'),
]
