from django.shortcuts import render

from apps.accounts.decorators import page_permission_required


@page_permission_required('view_equipment')
def equipment(request):
	return render(request, 'equipment/equipment.html')
