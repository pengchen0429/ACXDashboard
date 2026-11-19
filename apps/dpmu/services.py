from collections import defaultdict
from datetime import datetime, time, timedelta
from decimal import Decimal

from django.db import connections


PRODUCTION_FROM = '''
FROM tabWorkDayRpt a
LEFT JOIN tabEquipment b ON a.EquipNo = b.equipNo
LEFT JOIN tabEquipType c ON b.xflag = c.id
LEFT JOIN tabProduct p ON a.DuctID = p.ID
'''
SCRAP_FROM = '''
FROM tabDefaultRec a
LEFT JOIN tabEquipment b ON a.cDefine1 = b.equipNo
LEFT JOIN tabEquipType c ON b.xflag = c.id
LEFT JOIN tabProduct p ON a.DuctID = p.ID
LEFT JOIN tabGramCode g ON a.DefCode = g.BarCode
'''
AREA = "COALESCE(NULLIF(LTRIM(RTRIM(c.LineName)), ''), N'未分类')"
LINE = "COALESCE(NULLIF(LTRIM(RTRIM(b.equipName)), ''), N'未分类')"
PRODUCT = "COALESCE(NULLIF(LTRIM(RTRIM(p.ProductName)), ''), N'未分类')"
CATEGORY = "COALESCE(NULLIF(LTRIM(RTRIM(g.Remark)), ''), N'未分类')"
DEFECT = "COALESCE(NULLIF(LTRIM(RTRIM(g.MyCode)), ''), N'未分类')"
CATEGORIES = ('织造不合格', '染色不合格', '染色报废', '过程不合格')
TAB_AREAS = {'weaving': 'WEAV', 'dyeing': 'DYE'}


def allocate_scrap(rows, tab='overview'):
    allocated = []
    for month, source_area, line, product, category, defect, quantity in rows:
        if category not in CATEGORIES:
            continue
        areas = ('WEAV', 'DYE') if category == '过程不合格' else (
            ('WEAV',) if category == '织造不合格' else ('DYE',))
        share = Decimal(quantity or 0) / len(areas)
        for area in areas:
            if tab != 'overview' and area != TAB_AREAS[tab]:
                continue
            allocated_line = line if source_area == area else '未分配产线'
            allocated.append((month, area, allocated_line, product, category, defect, share))
    return allocated


def get_options(start, end, filters):
    categories = CATEGORIES
    if filters['tab'] == 'weaving':
        categories = ('织造不合格', '过程不合格')
    elif filters['tab'] == 'dyeing':
        categories = ('染色不合格', '染色报废', '过程不合格')
    query = ('SELECT DISTINCT ' + CATEGORY + ', ' + DEFECT
             + ' FROM tabDefaultRec a LEFT JOIN tabGramCode g ON a.DefCode = g.BarCode'
             + ' WHERE a.BegDate >= %s AND a.BegDate < %s AND ' + CATEGORY
             + ' IN (' + ', '.join(['%s'] * len(categories)) + ') ORDER BY 1, 2')
    with connections['mesaq'].cursor() as cursor:
        cursor.execute(query, [start, end + timedelta(minutes=1), *categories])
        rows = cursor.fetchall()
    available = [category for category in categories if any(row[0] == category for row in rows)]
    selected = set(filters.get('category', [])) & set(available)
    return {'categories': available, 'defects': [
        {'category': category, 'name': name} for category, name in rows
        if not selected or category in selected]}


def _query_rows(cursor, metric, start, end, filters):
    production = metric == 'production'
    if production:
        offset = timedelta(hours=8, minutes=30)
        lower = datetime.combine((start - offset).date(), time.min)
        shifted_end = end - offset
        upper = datetime.combine(shifted_end.date(), time.min)
        if shifted_end.time() != time.min or start == end:
            upper += timedelta(days=1)
        period = "CONVERT(char(7), a.RecDate, 120)"
        timestamp, quantity, source = 'a.RecDate', 'a.DayQty', PRODUCTION_FROM
    else:
        lower, upper = start, end + timedelta(minutes=1)
        first_day = (start - timedelta(hours=8, minutes=30)).date()
        shifted_end = end - timedelta(hours=8, minutes=30)
        last_day = shifted_end.date()
        if shifted_end.time() == time.min and start != end:
            last_day -= timedelta(days=1)
        day = 'CAST(DATEADD(minute, -510, a.BegDate) AS date)'
        period = ('CONVERT(char(7), CASE WHEN ' + day + ' < %s THEN %s WHEN '
                  + day + ' > %s THEN %s ELSE ' + day + ' END, 120)')
        timestamp, quantity, source = 'a.BegDate', 'a.intVal1', SCRAP_FROM
    dimensions = [period, AREA, LINE, PRODUCT]
    if not production:
        dimensions.extend([CATEGORY, DEFECT])
    conditions = [timestamp + ' >= %s', timestamp + ' < %s']
    params = [lower, upper]
    if production:
        areas = ('WEAV', 'DYE') if filters['tab'] == 'overview' else (TAB_AREAS[filters['tab']],)
        conditions.append(AREA + ' IN (' + ', '.join(['%s'] * len(areas)) + ')')
        params.extend(areas)
    if not production:
        conditions.append(CATEGORY + ' IN (' + ', '.join(['%s'] * len(CATEGORIES)) + ')')
        params.extend(CATEGORIES)
        for key, expression in (('category', CATEGORY), ('defect', DEFECT)):
            selected_values = filters.get(key, [])
            if isinstance(selected_values, str):
                selected_values = [selected_values]
            if selected_values:
                conditions.append(expression + ' IN (' + ', '.join(['%s'] * len(selected_values)) + ')')
                params.extend(selected_values)
    select_params = [] if production else [first_day, first_day, last_day, last_day]
    selected = ', '.join(dimensions)
    query = ('SELECT ' + selected + ', SUM(CAST(' + quantity + ' AS DECIMAL(28, 6))) '
             + source + ' WHERE ' + ' AND '.join(conditions))
    query += ' GROUP BY ' + selected
    if not production:
        params += select_params
    cursor.execute(query, select_params + params)
    return cursor.fetchall()


def summarize(production_rows, scrap_rows, months):
    dimensions = {name: defaultdict(lambda: [Decimal(0), Decimal(0)])
                  for name in ('months', 'areas', 'lines', 'products', 'categories', 'defects')}
    for month in months:
        dimensions['months'][month]
    production_total = scrap_total = Decimal(0)
    for metric, rows in enumerate((production_rows, scrap_rows)):
        for row in rows:
            quantity = Decimal(row[-1] or 0)
            if metric == 0:
                production_total += quantity
            else:
                scrap_total += quantity
            for name, value in zip(('months', 'areas', 'lines', 'products', 'categories', 'defects'), row[:-1]):
                dimensions[name][value][metric] += quantity

    def point(name, production, scrap):
        return {'name': name, 'production': float(production), 'scrap': float(scrap),
                'dpmu': float(scrap / production * 1000000) if production > 0 else None}

    result = {'total': point('TOTAL', production_total, scrap_total)}
    for name, groups in dimensions.items():
        points = []
        for label, (production, scrap) in groups.items():
            denominator = production_total if name in ('categories', 'defects') else production
            display_label = {'WEAV': '织造', 'DYE': '染色'}.get(label, label) if name == 'areas' else label
            points.append(point(display_label, denominator, scrap))
        result[name] = sorted(points, key=lambda item: item['name']) if name == 'months' else sorted(
            points, key=lambda item: (-item['scrap'], item['name']))
    return result


def get_summary(start, end, filters):
    first = (start - timedelta(hours=8, minutes=30)).replace(day=1)
    shifted_end = end - timedelta(hours=8, minutes=30)
    if shifted_end.time() == time.min and start != end:
        shifted_end -= timedelta(days=1)
    last = shifted_end.replace(day=1)
    months = []
    while (first.year, first.month) <= (last.year, last.month):
        months.append(first.strftime('%Y-%m'))
        first = first.replace(year=first.year + 1, month=1) if first.month == 12 else first.replace(month=first.month + 1)
    with connections['mesaq'].cursor() as cursor:
        production = _query_rows(cursor, 'production', start, end, filters)
        scrap = _query_rows(cursor, 'scrap', start, end, filters)
    return summarize(production, allocate_scrap(scrap, filters['tab']), months)