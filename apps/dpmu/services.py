from collections import defaultdict
from calendar import monthrange
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
PRODUCT_CODE = "COALESCE(LTRIM(RTRIM(p.ProductNO)), '')"
CATEGORY = "COALESCE(NULLIF(LTRIM(RTRIM(g.Remark)), ''), N'未分类')"
DEFECT = "COALESCE(NULLIF(LTRIM(RTRIM(g.MyCode)), ''), N'未分类')"
CATEGORIES = ('织造不合格', '染色不合格', '染色报废')
TAB_AREAS = {'weaving': 'WEAV', 'dyeing': 'DYE'}
WEAVING_SCRAP_CLASSES = ('10 米以上', '10米以下', '1米以下', '织造白坯', '织造批量')
WEAVING_EXCLUDED_DEFECTS = ('新接筒子架 Creels Change', 'PM脏 PM Dirty')
WEAVING_EXCLUDED_PRODUCTS = (
    'P1000YYYY000M', 'P1001YYYY000M', 'P1650YYYY000M',
    'P1200YYYY000M', 'P0900YYYY000M', 'P2500YYYY000M',
)


def allocate_scrap(rows, tab='overview'):
    allocated = []
    for month, source_area, line, product, category, defect, quantity in rows:
        if category not in CATEGORIES:
            continue
        areas = ('WEAV',) if category == '织造不合格' else ('DYE',)
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
        categories = ('织造不合格',)
    elif filters['tab'] == 'dyeing':
        categories = ('染色不合格', '染色报废')
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


def _query_rows(cursor, metric, start, end, filters, daily=False):
    production = metric == 'production'
    period_length = '10' if daily else '7'
    if production:
        offset = timedelta(hours=8, minutes=30)
        lower = datetime.combine((start - offset).date(), time.min)
        shifted_end = end - offset
        upper = datetime.combine(shifted_end.date(), time.min)
        if shifted_end.time() != time.min or start == end:
            upper += timedelta(days=1)
        period = 'CONVERT(char(' + period_length + '), a.RecDate, 120)'
        timestamp, quantity, source = 'a.RecDate', 'a.DayQty', PRODUCTION_FROM
    else:
        lower, upper = start, end + timedelta(minutes=1)
        first_day = (start - timedelta(hours=8, minutes=30)).date()
        shifted_end = end - timedelta(hours=8, minutes=30)
        last_day = shifted_end.date()
        if shifted_end.time() == time.min and start != end:
            last_day -= timedelta(days=1)
        day = 'CAST(DATEADD(minute, -510, a.BegDate) AS date)'
        period = ('CONVERT(char(' + period_length + '), CASE WHEN ' + day + ' < %s THEN %s WHEN '
                  + day + ' > %s THEN %s ELSE ' + day + ' END, 120)')
        timestamp, quantity, source = 'a.BegDate', 'a.intVal1', SCRAP_FROM
    dimensions = [period, AREA, LINE, PRODUCT]
    if not production:
        dimensions.extend([CATEGORY, DEFECT])
    conditions = [timestamp + ' >= %s', timestamp + ' < %s']
    params = [lower, upper]
    if production:
        areas = ('WEAV', 'DYE') if filters['tab'] == 'overview' else ('DYE',)
        conditions.append(AREA + ' IN (' + ', '.join(['%s'] * len(areas)) + ')')
        params.extend(areas)
        if filters['tab'] != 'dyeing':
            conditions.append('(' + AREA + ' <> %s OR ' + PRODUCT_CODE + ' NOT IN ('
                              + ', '.join(['%s'] * len(WEAVING_EXCLUDED_PRODUCTS)) + '))')
            excluded_area = 'DYE' if filters['tab'] == 'weaving' else 'WEAV'
            params.extend([excluded_area, *WEAVING_EXCLUDED_PRODUCTS])
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
        if metric == 'weaving_defects':
            conditions.extend([
                CATEGORY + ' = %s',
                'a.cDefine10 IN (' + ', '.join(['%s'] * len(WEAVING_SCRAP_CLASSES)) + ')',
                DEFECT + ' NOT IN (%s, %s)',
            ])
            params.extend(['织造不合格', *WEAVING_SCRAP_CLASSES, *WEAVING_EXCLUDED_DEFECTS])
    select_params = [] if production else [first_day, first_day, last_day, last_day]
    selected = ', '.join(dimensions)
    query = ('SELECT ' + selected + ', SUM(CAST(' + quantity + ' AS DECIMAL(28, 6))) '
             + source + ' WHERE ' + ' AND '.join(conditions))
    query += ' GROUP BY ' + selected
    if not production:
        params += select_params
    cursor.execute(query, select_params + params)
    return cursor.fetchall()


def summarize(production_rows, scrap_rows, months, products_use_total=False):
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
            denominator = production_total if name in ('categories', 'defects') or (
                name == 'products' and products_use_total) else production
            display_label = {'WEAV': '织造', 'DYE': '染色'}.get(label, label) if name == 'areas' else label
            item = point(display_label, denominator, scrap)
            if name == 'products' and products_use_total:
                item.update(production=float(production), denominator_production=float(denominator))
            points.append(item)
        result[name] = sorted(points, key=lambda item: item['name']) if name == 'months' else sorted(
            points, key=lambda item: (-item['scrap'], item['name']))
    return result


def _previous_month(value):
    year = value.year - 1 if value.month == 1 else value.year
    month = 12 if value.month == 1 else value.month - 1
    return value.replace(year=year, month=month, day=min(value.day, monthrange(year, month)[1]))


def _belt_rows(rows):
    return [(*row[:3], row[3][:4] if len(row[3]) >= 4 else '未分类', *row[4:]) for row in rows]


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
        weaving_defects = _query_rows(cursor, 'weaving_defects', start, end, filters) if filters['tab'] == 'weaving' else None
        if weaving_defects is not None:
            daily_production = _query_rows(cursor, 'production', start, end, filters, daily=True)
            daily_scrap = _query_rows(cursor, 'weaving_defects', start, end, filters, daily=True)
            previous_start, previous_end = _previous_month(start), _previous_month(end)
            previous_production = _query_rows(cursor, 'production', previous_start, previous_end, filters)
            previous_scrap = _query_rows(cursor, 'weaving_defects', previous_start, previous_end, filters)
    result = summarize(production, allocate_scrap(scrap, filters['tab']), months)
    if weaving_defects is not None:
        weaving_summary = summarize(production, allocate_scrap(weaving_defects, 'weaving'), months)
        result['weaving_defects'] = weaving_summary['defects']
        result['weaving_total'] = weaving_summary['total']
        result['weaving_products'] = summarize(
            _belt_rows(production), _belt_rows(allocate_scrap(weaving_defects, 'weaving')), [],
            products_use_total=True)['products']
        previous = summarize(previous_production, allocate_scrap(previous_scrap, 'weaving'), [])
        previous_months = {row['name']: row for row in previous['months']}
        result['weaving_months'] = []
        for row in weaving_summary['months']:
            previous_month = _previous_month(datetime.strptime(row['name'], '%Y-%m')).strftime('%Y-%m')
            comparison = previous_months.get(previous_month, {})
            previous_dpmu = comparison.get('dpmu')
            result['weaving_months'].append({**row, 'previous_month': previous_month,
                'previous_dpmu': previous_dpmu,
                'previous_production': comparison.get('production', 0),
                'previous_scrap': comparison.get('scrap', 0),
                'change_percent': (row['dpmu'] / previous_dpmu - 1) * 100
                if row['dpmu'] is not None and previous_dpmu not in (None, 0) else None})
        day = (start - timedelta(hours=8, minutes=30)).date()
        days = []
        while day <= shifted_end.date():
            days.append(day.isoformat())
            day += timedelta(days=1)
        result['weaving_days'] = summarize(
            daily_production, allocate_scrap(daily_scrap, 'weaving'), days)['months']
    return result