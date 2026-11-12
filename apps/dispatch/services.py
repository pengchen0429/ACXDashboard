from collections import Counter

from django.conf import settings

from common.snowflake import (
	ACTIVE_DISPATCH_AREA_FILTER_SQL, ACTIVE_DISPATCH_TYPE_FILTER_SQL, fetch_all, get_active_areas,
)


def get_dispatch_filter_options():
	"""独立读取各站点筛选候选项，不计算看板统计。"""
	server_sites = {
		'china^' + str(getattr(settings, 'L2L_SITE_' + site)): site
		for site in ('ACX', 'CNX')
	}
	active_areas = get_active_areas()
	rows = fetch_all(f'''
WITH filter_values AS (
	SELECT "SERVER_SITE_NAME" AS site, TRIM("areacode") AS area,
		TRIM("createdby") AS submitter, TRIM("dispatchtypecode") AS dispatch_type
	FROM PRD_MANUFACTURING_DB.G_L2L_CONSUMPTION.VW_DISPATCHES AS dispatch_source
	WHERE "SERVER_SITE_NAME" IN (%s, %s)
		AND COALESCE(LOWER(TRIM("deleted")), '') NOT IN ('t', 'true', '1')
		AND {ACTIVE_DISPATCH_AREA_FILTER_SQL}
		AND {ACTIVE_DISPATCH_TYPE_FILTER_SQL}
)
SELECT DISTINCT site AS "site", 'areas' AS "dimension", area AS "value"
FROM filter_values WHERE NULLIF(area, '') IS NOT NULL
UNION ALL
SELECT DISTINCT site AS "site", 'technicians' AS "dimension", submitter AS "value"
FROM filter_values WHERE NULLIF(submitter, '') IS NOT NULL
UNION ALL
SELECT DISTINCT site AS "site", 'dispatchtypes' AS "dimension", dispatch_type AS "value"
FROM filter_values WHERE NULLIF(dispatch_type, '') IS NOT NULL
''', list(server_sites))
	options = {site: {'areas': active_areas[site], 'technicians': [], 'dispatchtypes': []} for site in ('ACX', 'CNX')}
	for row in rows:
		if row['dimension'] != 'areas':
			options[server_sites[row['site']]][row['dimension']].append(row['value'])
	for values in options.values():
		for dimension in values:
			values[dimension].sort()
	return options


def fetch_dispatch_records(start, end, *, site):
	"""在 Snowflake 按报告月份、筛选维度和当前状态聚合。"""
	sites = (site,) if isinstance(site, str) else tuple(dict.fromkeys(site))
	if not sites or any(value not in ('ACX', 'CNX') for value in sites):
		raise ValueError('select at least one valid site: ACX or CNX')
	server_sites = ['china^' + str(getattr(settings, 'L2L_SITE_' + value)) for value in sites]
	site_placeholders = ', '.join(['%s'] * len(server_sites))
	return fetch_all(f'''
WITH dispatches AS (
	SELECT
		CONVERT_TIMEZONE(%s, 'Asia/Shanghai', TRY_TO_TIMESTAMP_NTZ("reported")) AS reported_at,
		COALESCE(TRIM("areacode"), '') AS area,
		COALESCE(TRIM("createdby"), '') AS submitter,
		COALESCE(TRIM("dispatchtypecode"), '') AS dispatch_type,
		CASE
			WHEN NULLIF(TRIM("closed"), '') IS NOT NULL THEN 'CLOSED'
			WHEN NULLIF(TRIM("dispatched"), '') IS NOT NULL
				OR NULLIF(TRIM("completed"), '') IS NOT NULL THEN 'IN WORK'
			ELSE 'OPEN'
		END AS status
	FROM PRD_MANUFACTURING_DB.G_L2L_CONSUMPTION.VW_DISPATCHES AS dispatch_source
	WHERE "SERVER_SITE_NAME" IN ({site_placeholders})
		AND COALESCE(LOWER(TRIM("deleted")), '') NOT IN ('t', 'true', '1')
		AND {ACTIVE_DISPATCH_AREA_FILTER_SQL}
		AND {ACTIVE_DISPATCH_TYPE_FILTER_SQL}
)
SELECT TO_CHAR(reported_at, 'YYYY-MM') AS "month", area AS "area",
	submitter AS "submitter", dispatch_type AS "type", status AS "status", COUNT(*) AS "count"
FROM dispatches
WHERE reported_at >= %s AND reported_at < %s
GROUP BY TO_CHAR(reported_at, 'YYYY-MM'), area, submitter, dispatch_type, status
''', [settings.SNOWFLAKE_DISPATCH_TIME_ZONE, *server_sites,
		start.replace(tzinfo=None), end.replace(tzinfo=None)])


def get_dispatch_details(start, end, *, site, areas=(), technicians=(), dispatchtypes=()):
	"""按看板筛选条件读取逐条明细，不合并相同字段的记录。"""
	sites = (site,) if isinstance(site, str) else tuple(dict.fromkeys(site))
	if not sites or any(value not in ('ACX', 'CNX') for value in sites):
		raise ValueError('select at least one valid site: ACX or CNX')
	server_sites = {'china^' + str(getattr(settings, 'L2L_SITE_' + value)): value for value in sites}
	site_placeholders = ', '.join(['%s'] * len(server_sites))
	conditions = ['reported_at >= %s', 'reported_at < %s']
	params = [settings.SNOWFLAKE_DISPATCH_TIME_ZONE, *server_sites,
		start.replace(tzinfo=None), end.replace(tzinfo=None)]
	for column, values in (('area', areas), ('submitter', technicians), ('dispatch_type', dispatchtypes)):
		if values:
			conditions.append(column + ' IN (' + ', '.join(['%s'] * len(values)) + ')')
			params.extend(values)
	rows = fetch_all(f'''
WITH dispatch_details AS (
	SELECT "SERVER_SITE_NAME" AS factory,
		CONVERT_TIMEZONE(%s, 'Asia/Shanghai', TRY_TO_TIMESTAMP_NTZ("reported")) AS reported_at,
		COALESCE(TRIM("areacode"), '') AS area,
		COALESCE(TRIM("createdby"), '') AS submitter,
		COALESCE(TRIM("dispatchtypecode"), '') AS dispatch_type
	FROM PRD_MANUFACTURING_DB.G_L2L_CONSUMPTION.VW_DISPATCHES AS dispatch_source
	WHERE "SERVER_SITE_NAME" IN ({site_placeholders})
		AND COALESCE(LOWER(TRIM("deleted")), '') NOT IN ('t', 'true', '1')
		AND {ACTIVE_DISPATCH_AREA_FILTER_SQL}
		AND {ACTIVE_DISPATCH_TYPE_FILTER_SQL}
)
SELECT factory AS "factory", reported_at AS "reported", area AS "area", dispatch_type AS "type"
FROM dispatch_details
WHERE {' AND '.join(conditions)}
ORDER BY reported_at, factory, area, dispatch_type
''', params)
	for row in rows:
		row['factory'] = server_sites[row['factory']]
	return rows


def get_dispatch_summary(start, end, *, site, areas=(), technicians=(), dispatchtypes=()):
	"""按上海本地 reported 区间汇总；technicians 参数兼容原接口，实际筛选 createdby。"""
	rows = fetch_dispatch_records(start, end, site=site)
	options = {
		'areas': sorted({row['area'] for row in rows if row['area']}),
		'technicians': sorted({row['submitter'] for row in rows if row['submitter']}),
		'dispatchtypes': sorted({row['type'] for row in rows if row['type']}),
	}
	selected = [row for row in rows if
		(not areas or row['area'] in areas)
		and (not technicians or row['submitter'] in technicians)
		and (not dispatchtypes or row['type'] in dispatchtypes)]
	counts = Counter()
	months = {}
	month = start.date().replace(day=1)
	while month < end.date():
		months[month.strftime('%Y-%m')] = {'total': 0, 'closed': 0}
		month = month.replace(year=month.year + 1, month=1) if month.month == 12 else month.replace(month=month.month + 1)
	types = Counter()
	area_counts = {}
	for row in selected:
		count = int(row['count'])
		counts[row['status']] += count
		months[row['month']]['total'] += count
		months[row['month']]['closed'] += count if row['status'] == 'CLOSED' else 0
		types[row['type'] or '未指定'] += count
		area = area_counts.setdefault(row['area'] or '未指定', {'OPEN': 0, 'IN WORK': 0, 'CLOSED': 0})
		area[row['status']] += count
	total = sum(counts.values())
	return {
		'options': options,
		'stats': {'total': total, 'open': counts['OPEN'], 'inwork': counts['IN WORK'],
			'closed': counts['CLOSED'], 'rate': round(counts['CLOSED'] / total * 100, 1) if total else 0},
		'trend': [{'month': month, **values} for month, values in months.items()],
		'types': [{'name': name, 'value': count} for name, count in sorted(types.items())],
		'areas': [{'name': name, **values} for name, values in sorted(area_counts.items())],
	}