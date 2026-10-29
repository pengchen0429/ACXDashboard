from django.urls import path

from . import views


urlpatterns = [
	path('', views.briefing, name='briefing'),
	path('safety-data/', views.safety_data, name='briefing_safety_data'),
]
