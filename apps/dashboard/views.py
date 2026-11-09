import hashlib
import os
from contextlib import contextmanager
from datetime import timedelta
from decimal import Decimal, InvalidOperation
from pathlib import Path

from django.conf import settings
from django.core.cache import caches
from django.http import JsonResponse
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from django.views.decorators.http import require_GET

from common.l2l_api import L2LAPIError, get_daily_production


PRODUCTION_AREAS = ('Weaving Process', 'Dyeing Process', 'Finishing Process')


@contextmanager
def production_refresh_lock(key):
	lock_dir = Path(settings.DASHBOARD_CACHE_LOCK_DIR)
	lock_dir.mkdir(parents=True, exist_ok=True)
	with (lock_dir / (hashlib.sha256(key.encode()).hexdigest() + '.lock')).open('a+b') as lock:
		lock.seek(0, 2)
		if lock.tell() == 0:
			lock.write(b'0')
			lock.flush()
		lock.seek(0)
		try:
			if os.name == 'nt':
				import msvcrt
				msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
			else:
				import fcntl
				fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
		except OSError:
			yield False
		else:
			yield True


def production_response(payload):
	response = JsonResponse(payload, status=503 if 'error' in payload else 200)
	response['Cache-Control'] = 'no-store'
	if 'error' in payload:
		response['Retry-After'] = '2'
	return response


@require_GET
def today_production(request):
	site = request.GET.get('site', 'ACX')
	if site not in ('ACX', 'CNX'):
		return JsonResponse({'error': 'site must be ACX or CNX'}, status=400)
	now = timezone.localtime()
	start = now.replace(hour=8, minute=30, second=0, microsecond=0)
	if now < start:
		start -= timedelta(days=1)
	end = start + timedelta(days=1)
	include_trend = request.GET.get('include_trend') == '1'
	include_lines = request.GET.get('include_lines') == '1'
	trend_end = now.replace(hour=8, minute=30, second=0, microsecond=0) + timedelta(days=1) if include_trend else None
	identity = repr((settings.L2L_BASE_URL, settings.L2L_AUTH, getattr(settings, 'L2L_SITE_' + site, None)))
	key = 'production:v9:%s:%s:%s:%s:%s' % (site, start.isoformat(), trend_end.isoformat() if trend_end else '-', include_lines, hashlib.sha256(identity.encode()).hexdigest())
	cache = caches['dashboard']
	cached = cache.get(key)
	if cached is not None:
		return production_response(cached)
	with production_refresh_lock(key) as acquired:
		cached = cache.get(key)
		if cached is not None:
			return production_response(cached)
		stale = cache.get(key + ':stale')
		fallback = {**stale, 'stale': True} if stale else {'error': 'Production data unavailable'}
		if not acquired:
			return production_response(fallback)
		payload = fetch_production_total(site, start, end, trend_end=trend_end, include_lines=include_lines)
		if 'error' in payload:
			payload = fallback
		else:
			cache.set(key + ':stale', payload, timeout=300)
		cache.set(key, payload, timeout=30)
		return production_response(payload)


def fetch_production_total(site, start, end, *, trend_end=None, include_lines=False):
	try:
		query_start = trend_end - timedelta(days=7) if trend_end else start
		query_end = trend_end or end
		trend_actual = {(query_start + timedelta(days=offset)).date().isoformat(): Decimal('0') for offset in range(7)} if trend_end else {}
		rows = get_daily_production(
			query_start.strftime('%Y-%m-%d %H:%M'),
			query_end.strftime('%Y-%m-%d %H:%M'),
			timeout=15,
			site=site,
		)
		actual = Decimal('0')
		downtime_minutes = Decimal('0')
		area_actual = {'Weaving': Decimal('0'), 'Dyeing': Decimal('0')}
		area_names = {'Weaving Process': 'Weaving', 'Dyeing Process': 'Dyeing'}
		equipment_groups = {base + suffix: base for base in ('LOOM042', 'LOOM043') for suffix in 'ABCD'}
		equipment_by_line = {}
		equipment_available = True
		lines = {}
		for row in rows:
			row_start = parse_datetime(row.get('start_date', ''))
			if row_start is None:
				raise ValueError('Missing production start_date')
			if timezone.is_naive(row_start):
				row_start = timezone.make_aware(row_start, timezone.get_current_timezone())
			row_start = row_start.astimezone(timezone.get_current_timezone())
			if (row_start.hour, row_start.minute, row_start.second, row_start.microsecond) == (0, 0, 0, 0):
				row_start = row_start.replace(hour=8, minute=30)
			if trend_end and query_start <= row_start < trend_end:
				value = Decimal(str(row['actual']))
				if not value.is_finite():
					raise ValueError('Invalid daily production metric')
				day = (row_start.astimezone(timezone.get_current_timezone()) - timedelta(hours=8, minutes=30)).date().isoformat()
				trend_actual[day] += value
			if start <= row_start < end:
				value = Decimal(str(row['actual']))
				downtime = Decimal(str(row['downtime_minutes']))
				if not value.is_finite() or not downtime.is_finite():
					raise ValueError('Invalid daily production metric')
				actual += value
				downtime_minutes += downtime
				line_id = row.get('line_id')
				line = row.get('line')
				identity = ('id', str(line_id)) if line_id is not None else ('line', line)
				if site == 'ACX' and isinstance(line, str) and line.strip().upper() in equipment_groups:
					identity = ('line', equipment_groups[line.strip().upper()])
				if value < 0 or (line_id is None and (not isinstance(line, str) or not line.strip())):
					equipment_available = False
				else:
					equipment_by_line[identity] = equipment_by_line.get(identity, False) or value > 0
				area = area_names.get(row.get('area'))
				if area is not None:
					area_actual[area] += value
				if include_lines:
					if not isinstance(line, str) or not line.strip():
						raise ValueError('Missing production line')
					demand = Decimal(str(row['demand']))
					if not demand.is_finite() or demand < 0 or value < 0:
						raise ValueError('Invalid line production metric')
					line_key = (str(line_id) if line_id is not None else line.strip(), row.get('area'))
					entry = lines.setdefault(line_key, {
						'line_id': line_id, 'line': line.strip(), 'area': row.get('area'),
						'product': None, 'demand': Decimal('0'), 'actual': Decimal('0'),
					})
					entry['demand'] += demand
					entry['actual'] += value
	except (L2LAPIError, InvalidOperation, ValueError, TypeError, KeyError):
		return {'error': 'Production data unavailable'}
	payload = {
		'site': site,
		'actual': format(actual, 'f'),
		'downtime_minutes': format(downtime_minutes, 'f'),
		'area_actual': {area: format(value, 'f') for area, value in area_actual.items()},
		'equipment_status': {
			'running': sum(equipment_by_line.values()),
			'stopped': len(equipment_by_line) - sum(equipment_by_line.values()),
			'total': len(equipment_by_line),
		} if equipment_available else None,
		'start_date': start.isoformat(),
		'end_date': end.isoformat(),
		'updated_at': timezone.now().isoformat(),
		'stale': False,
	}
	if trend_end:
		payload['trend'] = [{'date': day, 'actual': format(value, 'f')} for day, value in trend_actual.items()]
	if include_lines:
		payload['areas'] = list(PRODUCTION_AREAS)
		payload['lines'] = [
			{**entry, 'demand': format(entry['demand'], 'f'), 'actual': format(entry['actual'], 'f')}
			for entry in sorted(lines.values(), key=lambda entry: (str(entry['area']), entry['line']))
		]
	return payload
