from django.contrib.auth.decorators import login_required, permission_required
from django.shortcuts import render


@login_required(login_url='login')
@permission_required('dashboard.view_equipment', raise_exception=True)
def equipment(request):
	return render(request, 'equipment/equipment.html')
