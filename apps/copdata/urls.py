from django.urls import path

from . import views


urlpatterns = [
	path('', views.copdata, name='copdata'),
	path('data/', views.copdata_data, name='copdata-data'),
]
