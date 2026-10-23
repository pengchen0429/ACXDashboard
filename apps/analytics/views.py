import logging
from collections import Counter, defaultdict
from datetime import date, datetime, time, timedelta

from django.db import DatabaseError, connections
from django.http import JsonResponse
from django.utils import timezone
from django.views.decorators.http import require_GET


logger = logging.getLogger(__name__)


QUALITY_FROM_SQL = """
FROM tabDefaultRec a
INNER JOIN tabProduct c ON a.DuctID = c.ID
INNER JOIN tabCodeType d ON a.iflag = d.ID
INNER JOIN tabGramCode e ON a.DefCode = e.BarCode
LEFT OUTER JOIN tabEquipment f ON f.EquipNo = a.cDefine1
WHERE a.BegDate >= %s AND a.BegDate < %s
"""

QUALITY_SELECT_SQL = """
SELECT
	a.ID,
	CONVERT(varchar(10), a.BegDate, 21) AS RecordDate,
	a.BegDate,
	d.CodeType,
	a.cDefine4,
	a.TmpCode,
	c.ProductNO,
	c.ProductName,
	c.specs,
	a.cDefine1,
	f.equipName,
	(SELECT OrgName FROM tabOrg WHERE OrgID = a.cDefine2) AS OrgName,
	e.MyCode,
	(SELECT SUM(DayQty) FROM tabWorkDayRpt WHERE crtcode = a.TmpCode) AS SumNum,
	a.intVal1,
	UPPER(a.ChkManNo) AS ManName,
	a.cDefine5,
	a.cDefine6,
	e.Remark,
	a.cDefine7,
	LEFT(RIGHT(a.TmpCode, 5), 3) AS EqName,
	a.DefCode,
	a.BillNo,
	a.cDefine3,
	CASE e.xFlag WHEN 1 THEN NCHAR(8730) END AS ErrFlag,
	a.Remark AS BatRemark,
	a.cDefine10
"""


def quality_time_bounds(start_date, end_date):
	start_time = start_date if isinstance(start_date, datetime) else datetime.combine(start_date, time.min)
	end_minute = end_date if isinstance(end_date, datetime) else datetime.combine(end_date, time.min)
	if end_minute.date() == date.max:
		raise ValueError("end_date must be before 9999-12-31")

	end_time = end_minute + (timedelta(minutes=1) if isinstance(end_date, datetime) else timedelta(days=1))
	if start_time >= end_time:
		raise ValueError("start_date must not be after end_date")
	return start_time, end_time


def fetch_quality_records(start_date, end_date, page=1, page_size=100):
	start_time, end_time = quality_time_bounds(start_date, end_date)
	if page < 1 or not 1 <= page_size <= 1000:
		raise ValueError("page must be positive and page_size must be 1 to 1000")
	date_params = [start_time, end_time]
	offset = (page - 1) * page_size

	with connections['mesaq'].cursor() as cursor:
		cursor.execute("SELECT COUNT_BIG(*) " + QUALITY_FROM_SQL, date_params)
		total = cursor.fetchone()[0]
		cursor.execute(
			QUALITY_SELECT_SQL + QUALITY_FROM_SQL + """
ORDER BY a.BegDate DESC, a.ID DESC
OFFSET %s ROWS FETCH NEXT %s ROWS ONLY
""",
			date_params + [offset, page_size],
		)
		columns = [column[0] for column in cursor.description]
		records = [dict(zip(columns, row)) for row in cursor.fetchall()]

	return {
		'records': records,
		'total': total,
		'page': page,
		'page_size': page_size,
		'pages': (total + page_size - 1) // page_size,
		'start_date': start_date.isoformat(),
		'end_date': end_date.isoformat(),
	}


def fetch_daily_trend(start_date, end_date):
	start_time, end_time = quality_time_bounds(start_date, end_date)
	last_day = (end_time - timedelta(microseconds=1)).date()
	day_count = (last_day - start_time.date()).days + 1
	if day_count > 3660:
		raise ValueError("trend range must not exceed 3660 days")
	with connections['mesaq'].cursor() as cursor:
		cursor.execute("""
SELECT CAST(a.BegDate AS date) AS RecordDate,
       COALESCE(SUM(a.intVal1), 0) AS ScrapQuantity
""" + QUALITY_FROM_SQL + """
GROUP BY CAST(a.BegDate AS date)
ORDER BY RecordDate
""", [start_time, end_time])
		rows = {row[0]: row[1] for row in cursor.fetchall()}
	days = []
	for offset in range(day_count):
		day = start_time.date() + timedelta(days=offset)
		scrap_quantity = rows.get(day, 0)
		days.append({'date': day.isoformat(), 'scrap': scrap_quantity})
	return {'days': days, 'start_date': start_date.isoformat(), 'end_date': end_date.isoformat()}


def fetch_dashboard_statistics(start_date, end_date):
	start_time, end_time = quality_time_bounds(start_date, end_date)
	day_count = ((end_time - timedelta(microseconds=1)).date() - start_time.date()).days + 1
	if day_count > 3660:
		raise ValueError("dashboard range must not exceed 3660 days")
	with connections['mesaq'].cursor() as cursor:
		cursor.execute("""
SELECT RecordDate, Category, Defect, Team, Device, Inspector, Barcode, ScrapCategory, Product,
	COALESCE(SUM(ScrapQuantity), 0) AS ScrapQuantity
FROM (
    SELECT CAST(a.BegDate AS date) AS RecordDate, e.Remark AS Category, e.MyCode AS Defect,
           (SELECT OrgName FROM tabOrg WHERE OrgID = a.cDefine2) AS Team,
           f.equipName AS Device, UPPER(a.ChkManNo) AS Inspector,
           d.CodeType AS Barcode, a.cDefine10 AS ScrapCategory, c.ProductNO AS Product,
           a.intVal1 AS ScrapQuantity
""" + QUALITY_FROM_SQL + """
) AS QualitySource
GROUP BY RecordDate, Category, Defect, Team, Device, Inspector, Barcode, ScrapCategory, Product
ORDER BY RecordDate
""", [start_time, end_time])
		rows = cursor.fetchall()
	dimensions = ('categories', 'defects', 'teams', 'devices', 'inspectors', 'barcodes', 'scrap_categories', 'products')
	counts = {name: Counter() for name in dimensions}
	daily_scrap = defaultdict(int)
	category_daily = defaultdict(Counter)
	for row in rows:
		day, scrap_quantity = row[0], row[9]
		daily_scrap[day] += scrap_quantity
		labels = [str(value).strip() if value is not None and str(value).strip() else 'Unspecified' for value in row[1:9]]
		for name, label in zip(dimensions, labels):
			counts[name][label] += scrap_quantity
		category_daily[labels[0]][day] += scrap_quantity
	dates = [start_time.date() + timedelta(days=offset) for offset in range(day_count)]
	result = {
		'start_date': start_date.isoformat(), 'end_date': end_date.isoformat(),
		'total': sum(daily_scrap.values()),
		'days': [{'date': day.isoformat(), 'scrap': daily_scrap[day]} for day in dates],
	}
	for name in dimensions:
		items = sorted(counts[name].items(), key=lambda item: (-item[1], item[0]))
		if name in ('defects', 'devices', 'inspectors', 'products'):
			items = items[:10]
		result[name] = [{'name': label, 'value': count} for label, count in items]
	result['category_trend'] = [
		{'name': item['name'], 'data': [category_daily[item['name']][day] for day in dates]}
		for item in result['categories']
	]
	return result


def parse_query_date(value):
	if 'T' in value:
		parsed = datetime.fromisoformat(value)
		if parsed.tzinfo is not None or parsed.isoformat(timespec='minutes') != value or parsed.second or parsed.microsecond:
			raise ValueError("times must use YYYY-MM-DDTHH:mm format")
		return parsed
	parsed = date.fromisoformat(value)
	if parsed.isoformat() != value:
		raise ValueError("dates must use YYYY-MM-DD format")
	return parsed


@require_GET
def quality_records_data(request):
	try:
		end_date = parse_query_date(request.GET.get('end_date', timezone.localdate().isoformat()))
		start_date = parse_query_date(request.GET.get('start_date', (end_date - timedelta(days=29)).isoformat()))
		page = int(request.GET.get('page', '1'))
		page_size = int(request.GET.get('page_size', '100'))
		result = fetch_quality_records(start_date, end_date, page, page_size)
	except (ValueError, OverflowError):
		return JsonResponse({
			'error': 'Invalid parameters: use YYYY-MM-DD or YYYY-MM-DDTHH:mm with start_date <= end_date, '
					 'end_date before 9999-12-31, page >= 1 and page_size between 1 and 1000.',
		}, status=400)
	except DatabaseError:
		logger.exception('Failed to read quality records from MESAQ')
		return JsonResponse({'error': 'MESAQ data is currently unavailable.'}, status=503)

	return JsonResponse(result, json_dumps_params={'ensure_ascii': False})


@require_GET
def dashboard_statistics_data(request):
	try:
		end_date = parse_query_date(request.GET.get('end_date', timezone.localdate().isoformat()))
		start_date = parse_query_date(request.GET.get('start_date', (end_date - timedelta(days=29)).isoformat()))
		result = fetch_dashboard_statistics(start_date, end_date)
	except (ValueError, OverflowError):
		return JsonResponse({'error': 'Invalid time range: use YYYY-MM-DD or YYYY-MM-DDTHH:mm, start <= end, maximum 3660 days.'}, status=400)
	except DatabaseError:
		logger.exception('Failed to read quality dashboard statistics from MESAQ')
		return JsonResponse({'error': 'MESAQ data is currently unavailable.'}, status=503)
	return JsonResponse(result, json_dumps_params={'ensure_ascii': False})


@require_GET
def daily_trend_data(request):
	try:
		end_date = parse_query_date(request.GET.get('end_date', timezone.localdate().isoformat()))
		start_date = parse_query_date(request.GET.get('start_date', (end_date - timedelta(days=29)).isoformat()))
		result = fetch_daily_trend(start_date, end_date)
	except (ValueError, OverflowError):
		return JsonResponse({'error': 'Invalid time range: use YYYY-MM-DD or YYYY-MM-DDTHH:mm, start <= end, maximum 3660 days.'}, status=400)
	except DatabaseError:
		logger.exception('Failed to read daily quality trend from MESAQ')
		return JsonResponse({'error': 'MESAQ data is currently unavailable.'}, status=503)
	return JsonResponse(result, json_dumps_params={'ensure_ascii': False})
