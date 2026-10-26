from django.contrib.auth.decorators import login_required, permission_required
from django.shortcuts import render


@login_required(login_url='login')
@permission_required('dashboard.view_dpmu', raise_exception=True)
def dpmu(request):
	return render(request, 'dpmu/dpmu.html')
