from django.urls import path

from . import views


urlpatterns = [
	path('', views.briefing, name='briefing'),
	path('safety-data/', views.safety_data, name='briefing_safety_data'),
	path('dpmu-data/', views.dpmu_data, name='briefing_dpmu_data'),
	path('improvement-data/', views.improvement_data, name='briefing_improvement_data'),
]
