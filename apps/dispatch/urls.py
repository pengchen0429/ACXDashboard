from django.urls import path

from .views import dispatch, dispatch_data, dispatch_details, dispatch_export, dispatch_options


urlpatterns = [
    path('', dispatch, name='dispatch'),
    path('data/', dispatch_data, name='dispatch-data'),
    path('details/', dispatch_details, name='dispatch-details'),
    path('options/', dispatch_options, name='dispatch-options'),
    path('export/', dispatch_export, name='dispatch-export'),
]