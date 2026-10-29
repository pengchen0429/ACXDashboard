import logging
from datetime import datetime, time, timedelta
from hashlib import sha256

from django.conf import settings
from django.core.cache import cache
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


def get_safety_context(now=None):
	today = timezone.localtime(now or timezone.now()).date()
	start = datetime.combine(today - timedelta(days=1), time(8, 31))
	end = datetime.combine(today, time(8, 31))
	return {
		'start': start,
		'end': end - timedelta(minutes=1),
		'reported': None,
		'completed': None,
		'available': False,
		'loading': True,
		'server_site_names': SAFETY_SERVER_SITE_NAMES,
		'area_codes': SAFETY_AREA_CODES,
		'areas': [
			{'code': code, 'label': SAFETY_AREA_LABELS.get(code, code),
			 'reported': None, 'completed': None}
			for code in SAFETY_AREA_CODES
		],
		'dispatch_types': SAFETY_DISPATCH_TYPE_CODES,
	}


def get_safety_counts(now=None):
	result = get_safety_context(now)
	result['loading'] = False
	start = result['start']
	end = result['end'] + timedelta(minutes=1)
	if not SAFETY_SERVER_SITE_NAMES or not SAFETY_AREA_CODES or not SAFETY_DISPATCH_TYPE_CODES:
		for area in result['areas']:
			area.update(reported=0, completed=0)
		result.update(reported=0, completed=0, available=True)
		return result
	area_placeholders = ', '.join(['%s'] * len(SAFETY_AREA_CODES))
	type_placeholders = ', '.join(['%s'] * len(SAFETY_DISPATCH_TYPE_CODES))
	site_placeholders = ', '.join(['%s'] * len(SAFETY_SERVER_SITE_NAMES))
	query = f'''
WITH dispatches AS (
    SELECT
		"areacode" AS area_code,
        CONVERT_TIMEZONE(%s, 'Asia/Shanghai', TRY_TO_TIMESTAMP_NTZ("reported")) AS reported_at,
        CONVERT_TIMEZONE(%s, 'Asia/Shanghai', TRY_TO_TIMESTAMP_NTZ("completed")) AS completed_at
    FROM PRD_MANUFACTURING_DB.G_L2L_CONSUMPTION.VW_DISPATCHES
	WHERE "areacode" IN ({area_placeholders}) AND "dispatchtypecode" IN ({type_placeholders})
      AND "SERVER_SITE_NAME" IN ({site_placeholders})
)
SELECT
	area_code,
    COUNT(CASE WHEN reported_at >= %s AND reported_at < %s THEN 1 END),
    COUNT(CASE WHEN completed_at >= %s AND completed_at < %s THEN 1 END)
FROM dispatches
GROUP BY area_code
'''
	source_timezone = settings.SNOWFLAKE_DISPATCH_TIME_ZONE
	try:
		with connections['snowflake'].cursor() as cursor:
			cursor.execute(query, [
				source_timezone, source_timezone,
				*SAFETY_AREA_CODES, *SAFETY_DISPATCH_TYPE_CODES,
				*SAFETY_SERVER_SITE_NAMES,
				start, end, start, end,
			])
			counts = {
				code: (int(reported), int(completed))
				for code, reported, completed in cursor.fetchall()
			}
	except DatabaseError:
		logger.exception('Unable to load briefing safety counts from Snowflake')
		return result
	for area in result['areas']:
		reported, completed = counts.get(area['code'], (0, 0))
		area.update(reported=reported, completed=completed)
	result.update(
		reported=sum(area['reported'] for area in result['areas']),
		completed=sum(area['completed'] for area in result['areas']),
		available=True,
	)
	return result


def briefing(request):
	return render(request, 'briefing/briefing.html', {'safety': get_safety_context()})


@never_cache
@require_GET
def safety_data(request):
	now = timezone.now()
	context = get_safety_context(now)
	cache_identity = repr((
		context['start'], settings.SNOWFLAKE_DISPATCH_TIME_ZONE,
		SAFETY_AREA_CODES, SAFETY_AREA_LABELS, SAFETY_DISPATCH_TYPE_CODES,
		SAFETY_SERVER_SITE_NAMES,
	))
	cache_key = 'briefing:safety:v2:' + sha256(cache_identity.encode()).hexdigest()
	result = cache.get(cache_key)
	if result is None:
		result = get_safety_counts(now)
		if result['available']:
			cache.set(cache_key, result, timeout=60)
	return JsonResponse(result, status=200 if result['available'] else 503)
