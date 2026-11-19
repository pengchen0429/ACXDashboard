import logging
from datetime import datetime, timedelta

from django.db import DatabaseError
from django.http import JsonResponse
from django.shortcuts import render
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET

from apps.accounts.decorators import page_permission_required
from .services import CATEGORIES, get_options, get_summary


logger = logging.getLogger(__name__)


@page_permission_required('view_dpmu')
def dpmu(request):
	return render(request, 'dpmu/dpmu.html')


@never_cache
@page_permission_required('view_dpmu')
@require_GET
def options(request):
	try:
		start, end, filters = _parameters(request)
	except (ValueError, OverflowError):
		return JsonResponse({'error': '请填写有效时间，并选择有效的疵点分类。'}, status=400)
	try:
		return JsonResponse(get_options(start, end, filters))
	except DatabaseError:
		logger.exception('Unable to load DPMU options from MESAQ')
		return JsonResponse({'error': 'MESAQ 筛选项暂不可用，请重试。'}, status=503)


def _parameters(request):
	start = datetime.strptime(request.GET.get('start_time', ''), '%Y-%m-%dT%H:%M')
	end = datetime.strptime(request.GET.get('end_time', ''), '%Y-%m-%dT%H:%M')
	if start > end or (end - start).days > 3660:
		raise ValueError
	start - timedelta(hours=8, minutes=30)
	end + timedelta(days=1)
	filters = {key: list(dict.fromkeys(value.strip() for value in request.GET.getlist(key)
		if value.strip())) for key in ('category', 'defect')}
	if any(len(values) > 500 or any(len(value) > 1000 for value in values)
		for values in filters.values()):
		raise ValueError
	if any(category not in CATEGORIES for category in filters['category']):
		raise ValueError
	filters['tab'] = request.GET.get('tab', 'overview')
	if filters['tab'] not in ('overview', 'weaving', 'dyeing'):
		raise ValueError
	return start, end, filters


@never_cache
@page_permission_required('view_dpmu')
@require_GET
def data(request):
	try:
		start, end, filters = _parameters(request)
	except (ValueError, OverflowError):
		return JsonResponse({'error': '请填写有效时间（跨度不超过十年），并选择有效的疵点分类。'}, status=400)
	try:
		result = get_summary(start, end, filters)
	except DatabaseError:
		logger.exception('Unable to load DPMU statistics from MESAQ')
		return JsonResponse({'error': 'MESAQ 数据暂不可用，请重试。'}, status=503)
	return JsonResponse({**result, 'start_time': start.isoformat(timespec='minutes'),
		'end_time': end.isoformat(timespec='minutes'), 'filters': filters})
