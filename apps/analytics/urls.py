from django.urls import path
from django.views.generic import TemplateView

from . import views


urlpatterns = [
	path('', TemplateView.as_view(template_name='analytics/analytics.html'), name='analytics'),
	path('data/', views.quality_records_data, name='analytics-data'),
	path('daily-trend/', views.daily_trend_data, name='analytics-daily-trend'),
	path('statistics/', views.dashboard_statistics_data, name='analytics-statistics'),
]
