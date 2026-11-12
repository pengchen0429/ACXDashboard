from django.urls import path

from .views import dispatch, dispatch_data, dispatch_export, dispatch_options


urlpatterns = [
    path('', dispatch, name='dispatch'),
    path('data/', dispatch_data, name='dispatch-data'),
    path('options/', dispatch_options, name='dispatch-options'),
    path('export/', dispatch_export, name='dispatch-export'),
]