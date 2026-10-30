import logging
from datetime import datetime, time, timedelta
from decimal import Decimal

from django.conf import settings
from django.db import DatabaseError, connections
from django.http import JsonResponse
from django.shortcuts import render
from django.utils import timezone
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET


logger = logging.getLogger(__name__)

BRIEFING_SNOWFLAKE_START = datetime(2026, 1, 1)

SAFETY_SERVER_SITE_NAMES = (
	'china^907371',
)

# 区域统计
SAFETY_AREA_CODES = (
	'Weaving Process',
	'Dyeing Process',
	'Finishing Process',
)

SAFETY_AREA_LABELS = {
	'Weaving Process': 'Weaving',
	'Dyeing Process': 'Dyeing',
	'Finishing Process': 'Finishing',
}

# 安全Dispatch统计
SAFETY_DISPATCH_TYPE_CODES = (
	'Safety Jidoka - Unsafe Behaviors',
	'Safety Jidoka - Unsafe Conditions',
	
)

IMPROVEMENT_DISPATCH_TYPE_CODES = (
	'Electrical down 电气故障停机',
	'Electrical issue without breakdown 电气故障不停机',
	'Machine Breakdown 设备停机',
	'Machine issue without breakdown 设备故障不停机',
)


def get_safety_context(now=None, *, start=None, end=None, dispatch_types=None):
	local_now = timezone.localtime(now or timezone.now())
	today = local_now.date()
	start = start if start is not None else datetime.combine(today - timedelta(days=1), time(8, 31))
	end = end if end is not None else datetime.combine(today, time(8, 30))
	return {
		'start': start,
		'end': end,
		'reported': None,
		'completed': None,
		'unclosed': None,
		'unclosed_as_of': local_now.replace(tzinfo=None),
		'available': False,
		'loading': True,
		'server_site_names': SAFETY_SERVER_SITE_NAMES,
		'area_codes': SAFETY_AREA_CODES,
		'areas': [
			{'code': code, 'label': SAFETY_AREA_LABELS.get(code, code),
			 'reported': None, 'completed': None, 'unclosed': None}
			for code in SAFETY_AREA_CODES
		],
		'dispatch_types': SAFETY_DISPATCH_TYPE_CODES if dispatch_types is None else dispatch_types,
	}


def get_safety_counts(now=None, *, start=None, end=None, dispatch_types=None):
	result = get_safety_context(now, start=start, end=end, dispatch_types=dispatch_types)
	dispatch_types = result['dispatch_types']
	result['loading'] = False
	start = result['start']
	end = result['end'] + timedelta(minutes=1)
	if not SAFETY_SERVER_SITE_NAMES or not SAFETY_AREA_CODES or not dispatch_types:
		for area in result['areas']:
			area.update(reported=0, completed=0, unclosed=0)
		result.update(reported=0, completed=0, unclosed=0, available=True)
		return result
	area_placeholders = ', '.join(['%s'] * len(SAFETY_AREA_CODES))
	type_placeholders = ', '.join(['%s'] * len(dispatch_types))
	site_placeholders = ', '.join(['%s'] * len(SAFETY_SERVER_SITE_NAMES))
	query = f'''
WITH dispatches AS (
    SELECT
		"areacode" AS area_code,
        CONVERT_TIMEZONE(%s, 'Asia/Shanghai', TRY_TO_TIMESTAMP_NTZ("reported")) AS reported_at,
		CONVERT_TIMEZONE(%s, 'Asia/Shanghai', TRY_TO_TIMESTAMP_NTZ("completed")) AS completed_at,
		CONVERT_TIMEZONE(%s, 'Asia/Shanghai', TRY_TO_TIMESTAMP_NTZ("closed")) AS closed_at,
		NULLIF(TRIM("closed"), '') AS closed_value
    FROM PRD_MANUFACTURING_DB.G_L2L_CONSUMPTION.VW_DISPATCHES
	WHERE "areacode" IN ({area_placeholders}) AND "dispatchtypecode" IN ({type_placeholders})
      AND "SERVER_SITE_NAME" IN ({site_placeholders})
)
SELECT
	area_code,
    COUNT(CASE WHEN reported_at >= %s AND reported_at < %s THEN 1 END),
	COUNT(CASE WHEN reported_at >= %s AND reported_at < %s
		AND completed_at >= %s AND completed_at < %s THEN 1 END),
	COUNT(CASE WHEN reported_at <= %s
		AND (closed_value IS NULL OR closed_at > %s) THEN 1 END)
FROM dispatches
WHERE reported_at >= %s
GROUP BY area_code
'''
	source_timezone = settings.SNOWFLAKE_DISPATCH_TIME_ZONE
	try:
		with connections['snowflake'].cursor() as cursor:
			cursor.execute(query, [
				source_timezone, source_timezone, source_timezone,
				*SAFETY_AREA_CODES, *dispatch_types,
				*SAFETY_SERVER_SITE_NAMES,
				start, end, start, end, start, end,
				result['unclosed_as_of'], result['unclosed_as_of'],
				BRIEFING_SNOWFLAKE_START,
			])
			counts = {
				code: (int(reported), int(completed), int(unclosed))
				for code, reported, completed, unclosed in cursor.fetchall()
			}
	except DatabaseError:
		logger.exception('Unable to load briefing dispatch counts from Snowflake')
		return result
	for area in result['areas']:
		reported, completed, unclosed = counts.get(area['code'], (0, 0, 0))
		area.update(reported=reported, completed=completed, unclosed=unclosed)
	result.update(
		reported=sum(area['reported'] for area in result['areas']),
		completed=sum(area['completed'] for area in result['areas']),
		unclosed=sum(area['unclosed'] for area in result['areas']),
		available=True,
	)
	return result


def get_improvement_counts(now=None, *, start=None, end=None):
	return get_safety_counts(now, start=start, end=end, dispatch_types=IMPROVEMENT_DISPATCH_TYPE_CODES)


def get_safety_trend(start, end, *, dispatch_types=None):
	dispatch_types = SAFETY_DISPATCH_TYPE_CODES if dispatch_types is None else dispatch_types
	days = (end.date() - start.date()).days + 1
	granularity = 'day' if days <= 90 else 'month' if days <= 1096 else 'year'
	result = {'available': False, 'granularity': granularity, 'points': []}
	result['areas'] = [
		{'code': code, 'label': SAFETY_AREA_LABELS.get(code, code), 'points': []}
		for code in SAFETY_AREA_CODES
	]
	counts = {}
	if SAFETY_SERVER_SITE_NAMES and SAFETY_AREA_CODES and dispatch_types:
		area_placeholders = ', '.join(['%s'] * len(SAFETY_AREA_CODES))
		type_placeholders = ', '.join(['%s'] * len(dispatch_types))
		site_placeholders = ', '.join(['%s'] * len(SAFETY_SERVER_SITE_NAMES))
		query = f'''
WITH dispatches AS (
	SELECT "areacode" AS area_code,
		CONVERT_TIMEZONE(%s, 'Asia/Shanghai', TRY_TO_TIMESTAMP_NTZ("reported")) AS reported_at
    FROM PRD_MANUFACTURING_DB.G_L2L_CONSUMPTION.VW_DISPATCHES
    WHERE "areacode" IN ({area_placeholders})
      AND "dispatchtypecode" IN ({type_placeholders})
      AND "SERVER_SITE_NAME" IN ({site_placeholders})
)
SELECT TO_CHAR(DATE_TRUNC(%s, reported_at), 'YYYY-MM-DD') AS period, area_code, COUNT(*)
FROM dispatches
WHERE reported_at >= %s AND reported_at < %s
	AND reported_at >= %s
GROUP BY period, area_code
ORDER BY period, area_code
'''
		try:
			with connections['snowflake'].cursor() as cursor:
				cursor.execute(query, [
					settings.SNOWFLAKE_DISPATCH_TIME_ZONE,
					*SAFETY_AREA_CODES, *dispatch_types, *SAFETY_SERVER_SITE_NAMES,
					granularity, start, end + timedelta(minutes=1),
					BRIEFING_SNOWFLAKE_START,
				])
				counts = {(period, code): int(reported) for period, code, reported in cursor.fetchall()}
		except DatabaseError:
			logger.exception('Unable to load briefing safety trend from Snowflake')
			return result
	period, last = start.date(), end.date()
	if granularity in ('month', 'year'):
		period, last = period.replace(day=1), last.replace(day=1)
	if granularity == 'year':
		period, last = period.replace(month=1), last.replace(month=1)
	while True:
		key = period.isoformat()
		for area in result['areas']:
			area['points'].append({'date': key, 'reported': counts.get((key, area['code']), 0)})
		result['points'].append({
			'date': key, 'reported': sum(area['points'][-1]['reported'] for area in result['areas']),
		})
		if period == last:
			break
		if granularity == 'day':
			period += timedelta(days=1)
		elif granularity == 'month':
			period = period.replace(year=period.year + 1, month=1) if period.month == 12 else period.replace(month=period.month + 1)
		else:
			period = period.replace(year=period.year + 1)
	result['available'] = True
	return result


def get_improvement_trend(start, end):
	return get_safety_trend(start, end, dispatch_types=IMPROVEMENT_DISPATCH_TYPE_CODES)


def get_production_bounds(start, end):
	shift_offset = timedelta(hours=8, minutes=30)
	production_start = datetime.combine((start - shift_offset).date(), time.min)
	shift_end = end - shift_offset
	production_end = datetime.combine(shift_end.date(), time.min)
	if shift_end.time() != time.min or start == end:
		production_end += timedelta(days=1)
	return production_start, production_end


def get_dpmu_counts(start, end):
	result = {'start': start, 'end': end, 'available': False,
		'production': None, 'scrap': None, 'dpmu': None}
	production_start, production_end = get_production_bounds(start, end)
	query = '''
SELECT
    (SELECT COALESCE(SUM(CAST(a.DayQty AS DECIMAL(28, 6))), 0)
     FROM tabWorkDayRpt a
     INNER JOIN tabEquipment b ON a.EquipNo = b.equipNo
     INNER JOIN tabEquipType c ON b.xflag = c.id
     WHERE a.RecDate >= %s AND a.RecDate < %s AND c.EquipType = %s),
    (SELECT COALESCE(SUM(CAST(a.intVal1 AS DECIMAL(28, 6))), 0)
     FROM tabDefaultRec a
     INNER JOIN tabGramCode e ON a.DefCode = e.BarCode
     WHERE a.BegDate >= %s AND a.BegDate < %s AND e.Remark = %s
       AND (e.MyCode IS NULL OR e.MyCode NOT IN (%s, %s))
       AND a.cDefine10 IN (%s, %s, %s, %s, %s))
'''
	exclusive_end = end + timedelta(minutes=1)
	try:
		with connections['mesaq'].cursor() as cursor:
			cursor.execute(query, [
				production_start, production_end, '织造', start, exclusive_end, '织造不合格',
				'新接筒子架 Creels Change', 'PM脏 PM Dirty',
				'织造白坯', '10米以下', '10 米以上', '1米以下', '织造批量',
			])
			production, scrap = cursor.fetchone()
	except DatabaseError:
		logger.exception('Unable to load briefing DPMU counts from MESAQ')
		return result
	production, scrap = Decimal(production), Decimal(scrap)
	result.update(available=True, production=production, scrap=scrap,
		dpmu=scrap / production if production > 0 else None)
	return result


def get_dpmu_trend(start, end):
	production_start, production_end = get_production_bounds(start, end)
	first_day = production_start.date()
	last_day = (production_end - timedelta(days=1)).date()
	days = (last_day - first_day).days + 1
	granularity = 'day' if days <= 90 else 'month' if days <= 1096 else 'year'
	result = {'available': False, 'granularity': granularity, 'points': []}
	query = '''
SELECT 'production' AS metric, CAST(a.RecDate AS date) AS production_date,
       SUM(CAST(a.DayQty AS DECIMAL(28, 6))) AS quantity
FROM tabWorkDayRpt a
INNER JOIN tabEquipment b ON a.EquipNo = b.equipNo
INNER JOIN tabEquipType c ON b.xflag = c.id
WHERE a.RecDate >= %s AND a.RecDate < %s AND c.EquipType = %s
GROUP BY CAST(a.RecDate AS date)
UNION ALL
SELECT 'scrap' AS metric, CAST(DATEADD(minute, -510, a.BegDate) AS date) AS production_date,
       SUM(CAST(a.intVal1 AS DECIMAL(28, 6))) AS quantity
FROM tabDefaultRec a
INNER JOIN tabGramCode e ON a.DefCode = e.BarCode
WHERE a.BegDate >= %s AND a.BegDate < %s AND e.Remark = %s
  AND (e.MyCode IS NULL OR e.MyCode NOT IN (%s, %s))
  AND a.cDefine10 IN (%s, %s, %s, %s, %s)
GROUP BY CAST(DATEADD(minute, -510, a.BegDate) AS date)
'''
	try:
		with connections['mesaq'].cursor() as cursor:
			cursor.execute(query, [
				production_start, production_end, '织造', start, end + timedelta(minutes=1), '织造不合格',
				'新接筒子架 Creels Change', 'PM脏 PM Dirty',
				'织造白坯', '10米以下', '10 米以上', '1米以下', '织造批量',
			])
			rows = cursor.fetchall()
	except DatabaseError:
		logger.exception('Unable to load briefing DPMU trend from MESAQ')
		return result
	def period_start(day):
		if granularity == 'year':
			return day.replace(month=1, day=1)
		return day.replace(day=1) if granularity == 'month' else day
	totals = {}
	for metric, day, quantity in rows:
		day = min(max(day, first_day), last_day)
		key = period_start(day)
		values = totals.setdefault(key, {'production': Decimal(0), 'scrap': Decimal(0)})
		values[metric] += Decimal(quantity or 0)
	period, last = period_start(first_day), period_start(last_day)
	while True:
		values = totals.get(period, {'production': Decimal(0), 'scrap': Decimal(0)})
		result['points'].append({'date': period.isoformat(), **values,
			'dpmu': values['scrap'] / values['production'] if values['production'] > 0 else None})
		if period == last:
			break
		if granularity == 'day':
			period += timedelta(days=1)
		elif granularity == 'month':
			period = period.replace(year=period.year + 1, month=1) if period.month == 12 else period.replace(month=period.month + 1)
		else:
			period = period.replace(year=period.year + 1)
	result['available'] = True
	return result


@never_cache
@require_GET
def dpmu_data(request):
	start_value = request.GET.get('start_time', '')
	end_value = request.GET.get('end_time', '')
	start = end = None
	if start_value or end_value:
		try:
			start = datetime.strptime(start_value, '%Y-%m-%dT%H:%M')
			end = datetime.strptime(end_value, '%Y-%m-%dT%H:%M')
			if start > end:
				raise ValueError('Start must not be after end')
			start - timedelta(hours=8, minutes=30)
			end + timedelta(minutes=1)
		except (ValueError, OverflowError):
			return JsonResponse({
				'error': 'Provide both times as YYYY-MM-DDTHH:MM, with start not after end.',
			}, status=400)
	context = get_safety_context(start=start, end=end)
	try:
		result = get_dpmu_counts(context['start'], context['end'])
		if request.GET.get('include_trend') == '1' and result['available']:
			result['trend'] = get_dpmu_trend(context['start'], context['end'])
	except OverflowError:
		return JsonResponse({'error': 'Time range exceeds supported production dates.'}, status=400)
	return JsonResponse(result, status=200 if result['available'] else 503)


def briefing(request):
	return render(request, 'briefing/briefing.html', {'safety': get_safety_context()})


@never_cache
@require_GET
def safety_data(request):
	return dispatch_data(request, get_safety_counts, trend_loader=get_safety_trend)


@never_cache
@require_GET
def improvement_data(request):
	return dispatch_data(request, get_improvement_counts, trend_loader=get_improvement_trend)


def dispatch_data(request, counts_loader, *, trend_loader=None):
	now = timezone.now()
	start_value = request.GET.get('start_time', '')
	end_value = request.GET.get('end_time', '')
	start = end = None
	if start_value or end_value:
		try:
			start = datetime.strptime(start_value, '%Y-%m-%dT%H:%M')
			end = datetime.strptime(end_value, '%Y-%m-%dT%H:%M')
			if start > end:
				raise ValueError('Start must not be after end')
			end + timedelta(minutes=1)
		except (ValueError, OverflowError):
			return JsonResponse({
				'error': 'Provide both times as YYYY-MM-DDTHH:MM, with start not after end.',
			}, status=400)
	context = get_safety_context(now, start=start, end=end)
	result = counts_loader(now, start=context['start'], end=context['end'])
	if trend_loader and request.GET.get('include_trend') == '1' and result['available']:
		result['trend'] = trend_loader(context['start'], context['end'])
	return JsonResponse(result, status=200 if result['available'] else 503)
