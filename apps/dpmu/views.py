from django.shortcuts import render

from apps.accounts.decorators import page_permission_required


@page_permission_required('view_dpmu')
def dpmu(request):
	return render(request, 'dpmu/dpmu.html')
