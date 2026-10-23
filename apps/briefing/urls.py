from django.urls import path

from . import views


urlpatterns = [
	path('', views.briefing, name='briefing'),
]
