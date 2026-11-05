import logging
import math
from datetime import datetime, timedelta

from django.db import DatabaseError
from django.http import JsonResponse
from django.shortcuts import render
from django.utils import timezone
from django.views.decorators.http import require_GET

from common.db import get_cop_data


logger = logging.getLogger(__name__)


@require_GET
def copdata(request):
	today = timezone.localdate()
	return render(request, 'copdata/copdata.html', {
		'date_from': today.replace(day=1).isoformat(),
		'date_to': today.isoformat(),
	})


@require_GET
def copdata_data(request):
	factories = list(dict.fromkeys(request.GET.getlist('factory') or ['ACX', 'CNX']))
	if any(factory not in ('ACX', 'CNX') for factory in factories):
		return JsonResponse({'error': '工厂必须是 ACX 或 CNX'}, status=400)
	try:
		start = datetime.strptime(request.GET.get('date_from', ''), '%Y-%m-%d').date()
		end = datetime.strptime(request.GET.get('date_to', ''), '%Y-%m-%d').date()
		end_exclusive = end + timedelta(days=1)
	except (ValueError, OverflowError):
		return JsonResponse({'error': '请选择有效的开始和结束日期'}, status=400)
	if start > end:
		return JsonResponse({'error': '开始日期不能晚于结束日期'}, status=400)
	try:
		records = []
		for factory in factories:
			records.extend(get_cop_data(
				factory, start_time=start.isoformat(), end_time=end_exclusive.isoformat(),
			))
	except DatabaseError:
		logger.exception('COP database query failed')
		return JsonResponse({'error': '数据库查询失败，请稍后重试'}, status=503)
	for record in records:
		beg_date = record['BegDate']
		if isinstance(beg_date, datetime):
			if timezone.is_aware(beg_date):
				beg_date = timezone.localtime(beg_date)
			record['BegDate'] = beg_date.isoformat(sep=' ', timespec='seconds')
		else:
			record['BegDate'] = str(beg_date or '')
		for field in ('ProductNO', 'BatchCode'):
			record[field] = str(record[field] or '')
		for field in record:
			if field.startswith('decVal'):
				value = record[field]
				value = float(value) if value is not None else None
				record[field] = value if value is not None and math.isfinite(value) else None
	records.sort(key=lambda record: record['BegDate'], reverse=True)
	return JsonResponse({
		'records': records,
		'products': sorted({record['ProductNO'] for record in records if record['ProductNO']}),
		'batches': sorted({record['BatchCode'] for record in records if record['BatchCode']}),
	})
