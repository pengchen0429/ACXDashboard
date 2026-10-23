from django.shortcuts import render


def equipment(request):
	return render(request, 'equipment/equipment.html')
