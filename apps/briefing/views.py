import logging
from datetime import datetime, time, timedelta

from django.conf import settings
from django.db import DatabaseError, connections
from django.http import JsonResponse
from django.shortcuts import render
from django.utils import timezone
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET


logger = logging.getLogger(__name__)

SAFETY_SERVER_SITE_NAMES = (
	'china^907371',
)

# 区域统计
SAFETY_AREA_CODES = (
	'Weaving Process',
	'Dyeing Process',
	'ACX Finishing',
)

SAFETY_AREA_LABELS = {
	'Weaving Process': 'Weaving',
	'Dyeing Process': 'Dyeing',
	'ACX Finishing': 'Finishing',
}

# 安全Dispatch统计
SAFETY_DISPATCH_TYPE_CODES = (
	'Safety Jidoka - Unsafe Behaviors',
	'Safety Jidoka - Unsafe Conditions',
	
)


def get_safety_context(now=None, *, start=None, end=None):
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
		'dispatch_types': SAFETY_DISPATCH_TYPE_CODES,
	}


def get_safety_counts(now=None, *, start=None, end=None):
	result = get_safety_context(now, start=start, end=end)
	result['loading'] = False
	start = result['start']
	end = result['end'] + timedelta(minutes=1)
	if not SAFETY_SERVER_SITE_NAMES or not SAFETY_AREA_CODES or not SAFETY_DISPATCH_TYPE_CODES:
		for area in result['areas']:
			area.update(reported=0, completed=0, unclosed=0)
		result.update(reported=0, completed=0, unclosed=0, available=True)
		return result
	area_placeholders = ', '.join(['%s'] * len(SAFETY_AREA_CODES))
	type_placeholders = ', '.join(['%s'] * len(SAFETY_DISPATCH_TYPE_CODES))
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
GROUP BY area_code
'''
	source_timezone = settings.SNOWFLAKE_DISPATCH_TIME_ZONE
	try:
		with connections['snowflake'].cursor() as cursor:
			cursor.execute(query, [
				source_timezone, source_timezone, source_timezone,
				*SAFETY_AREA_CODES, *SAFETY_DISPATCH_TYPE_CODES,
				*SAFETY_SERVER_SITE_NAMES,
				start, end, start, end, start, end,
				result['unclosed_as_of'], result['unclosed_as_of'],
			])
			counts = {
				code: (int(reported), int(completed), int(unclosed))
				for code, reported, completed, unclosed in cursor.fetchall()
			}
	except DatabaseError:
		logger.exception('Unable to load briefing safety counts from Snowflake')
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


def briefing(request):
	return render(request, 'briefing/briefing.html', {'safety': get_safety_context()})


@never_cache
@require_GET
def safety_data(request):
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
	result = get_safety_counts(now, start=context['start'], end=context['end'])
	return JsonResponse(result, status=200 if result['available'] else 503)
