from django.shortcuts import render


def briefing(request):
	return render(request, 'briefing/briefing.html')
