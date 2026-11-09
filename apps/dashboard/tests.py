from django.contrib.auth import SESSION_KEY, get_user_model
from django.contrib.auth.models import Group, Permission
from django.conf import settings
from django.test import Client, TestCase
from django.shortcuts import resolve_url
from django.urls import reverse
from datetime import datetime
from tempfile import TemporaryDirectory
from unittest.mock import patch

from django.test import SimpleTestCase, override_settings

from common.l2l_api import L2LAPIError


@override_settings(TIME_ZONE='Asia/Shanghai', USE_TZ=True)
class TodayProductionTests(SimpleTestCase):
	def setUp(self):
		from django.core.cache import caches
		self.cache_dir = TemporaryDirectory()
		self.addCleanup(self.cache_dir.cleanup)
		self.cache_settings = override_settings(
			CACHES={
				'default': {'BACKEND': 'django.core.cache.backends.locmem.LocMemCache'},
				'dashboard': {
					'BACKEND': 'django.core.cache.backends.filebased.FileBasedCache',
					'LOCATION': self.cache_dir.name + '/data',
				},
			},
			DASHBOARD_CACHE_LOCK_DIR=self.cache_dir.name + '/locks',
		)
		self.cache_settings.enable()
		self.addCleanup(self.cache_settings.disable)
		self.cache = caches['dashboard']

	@patch('apps.dashboard.views.get_daily_production')
	@patch('apps.dashboard.views.timezone.localtime')
	def test_sums_actual_for_current_production_day(self, mock_now, mock_daily):
		from django.utils import timezone
		mock_now.return_value = timezone.make_aware(datetime(2026, 11, 3, 13, 0))
		mock_daily.return_value = [
			{'start_date': '2026-11-03T08:30:00', 'actual': '26520.00', 'downtime_minutes': '10'},
			{'start_date': '2026-11-03T08:30:00', 'actual': '0.1', 'downtime_minutes': '0.1'},
			{'start_date': '2026-11-03T08:30:00', 'actual': '0.2', 'downtime_minutes': '0.2'},
			{'start_date': '2026-11-02T08:30:00', 'actual': '999', 'downtime_minutes': '999'},
			{'start_date': '2026-11-04T08:30:00', 'actual': '999', 'downtime_minutes': '999'},
		]
		response = self.client.get(reverse('dashboard-today-production'))
		self.assertEqual(response.status_code, 200)
		self.assertEqual(response.json()['actual'], '26520.30')
		self.assertEqual(response.json()['downtime_minutes'], '10.3')
		self.assertEqual(response['Cache-Control'], 'no-store')
		mock_daily.assert_called_once_with('2026-11-03 08:30', '2026-11-04 08:30', timeout=15, site='ACX')

	@patch('apps.dashboard.views.get_daily_production')
	@patch('apps.dashboard.views.timezone.localtime')
	def test_midnight_daily_labels_belong_to_same_production_date(self, mock_now, mock_daily):
		from django.utils import timezone
		mock_now.return_value = timezone.make_aware(datetime(2026, 11, 3, 13, 0))
		mock_daily.return_value = [
			{'start_date': stamp, 'actual': actual, 'downtime_minutes': downtime, 'area': area, 'line_id': line_id}
			for stamp, actual, downtime, area, line_id in [
				('2026-10-28T00:00:00', '10', '1', 'Weaving Process', 1),
				('2026-11-02T00:00:00', '20', '2', 'Weaving Process', 1),
				('2026-11-03T00:00:00', '100', '3', 'Weaving Process', 1),
				('2026-11-02T16:00:00Z', '200', '4', 'Dyeing Process', 2),
				('2026-11-03T00:00:00+08:00', '0', '5', 'Weaving Process', 3),
				('2026-11-04T00:00:00', '999', '999', 'Weaving Process', 4),
			]
		]
		for site in ('ACX', 'CNX'):
			with self.subTest(site=site):
				for include_trend in ('0', '1'):
					response = self.client.get(reverse('dashboard-today-production'), {'site': site, 'include_trend': include_trend})
					self.assertEqual(response.status_code, 200)
					payload = response.json()
					self.assertEqual(payload['actual'], '300')
					self.assertEqual(payload['downtime_minutes'], '12')
					self.assertEqual(payload['area_actual'], {'Weaving': '100', 'Dyeing': '200'})
					self.assertEqual(payload['equipment_status'], {'running': 2, 'stopped': 1, 'total': 3})
					if include_trend == '1':
						self.assertEqual(payload['trend'], [
							{'date': day, 'actual': actual} for day, actual in [
								('2026-10-28', '10'), ('2026-10-29', '0'), ('2026-10-30', '0'),
								('2026-10-31', '0'), ('2026-11-01', '0'), ('2026-11-02', '20'), ('2026-11-03', '300'),
							]
						])

	@patch('apps.dashboard.views.get_daily_production')
	@patch('apps.dashboard.views.timezone.localtime')
	def test_midnight_daily_labels_before_shift_start_keep_previous_day(self, mock_now, mock_daily):
		from django.utils import timezone
		mock_now.return_value = timezone.make_aware(datetime(2026, 11, 3, 8, 29))
		mock_daily.return_value = [
			{'start_date': '2026-11-02T00:00:00', 'actual': '100', 'downtime_minutes': '2'},
			{'start_date': '2026-11-03T00:00:00', 'actual': '200', 'downtime_minutes': '3'},
		]
		for include_trend in ('0', '1'):
			payload = self.client.get(reverse('dashboard-today-production'), {'include_trend': include_trend}).json()
			self.assertEqual(payload['start_date'][:10], '2026-11-02')
			self.assertEqual(payload['actual'], '100')
			self.assertEqual(payload['downtime_minutes'], '2')
			if include_trend == '1':
				self.assertEqual(payload['trend'][-2:], [
					{'date': '2026-11-02', 'actual': '100'},
					{'date': '2026-11-03', 'actual': '200'},
				])

	@patch('apps.dashboard.views.get_daily_production', return_value=[])
	@patch('apps.dashboard.views.timezone.localtime')
	def test_production_day_rolls_over_at_0830(self, mock_now, mock_daily):
		from django.utils import timezone
		for hour, minute, start, end in [
			(8, 29, '2026-11-02 08:30', '2026-11-03 08:30'),
			(8, 30, '2026-11-03 08:30', '2026-11-04 08:30'),
		]:
			with self.subTest(hour=hour, minute=minute):
				mock_now.return_value = timezone.make_aware(datetime(2026, 11, 3, hour, minute))
				response = self.client.get(reverse('dashboard-today-production'))
				self.assertEqual(response.json()['actual'], '0')
				self.assertEqual(response.json()['downtime_minutes'], '0')
				mock_daily.assert_called_with(start, end, timeout=15, site='ACX')

	@patch('apps.dashboard.views.get_daily_production')
	@patch('apps.dashboard.views.timezone.localtime')
	def test_sites_have_independent_totals_and_failures(self, mock_now, mock_daily):
		from django.utils import timezone
		mock_now.return_value = timezone.make_aware(datetime(2026, 11, 3, 13, 0))
		mock_daily.side_effect = [
			[{'start_date': '2026-11-03T08:30:00', 'actual': '123', 'downtime_minutes': '12.3'}],
			[{'start_date': '2026-11-03T08:30:00', 'actual': '456', 'downtime_minutes': '45.6'}],
			L2LAPIError('Unavailable'),
			[{'start_date': '2026-11-03T08:30:00', 'actual': '789', 'downtime_minutes': '78.9'}],
		]
		for site, expected in [('ACX', '123'), ('CNX', '456'), ('ACX', None), ('CNX', '789')]:
			with self.subTest(site=site, expected=expected):
				self.cache.clear()
				response = self.client.get(reverse('dashboard-today-production'), {'site': site})
				mock_daily.assert_called_with('2026-11-03 08:30', '2026-11-04 08:30', timeout=15, site=site)
				if expected is None:
					self.assertEqual(response.status_code, 503)
				else:
					self.assertEqual(response.json()['site'], site)
					self.assertEqual(response.json()['actual'], expected)
					self.assertEqual(response.json()['downtime_minutes'], str(int(expected) / 10))

	@patch('apps.dashboard.views.get_daily_production')
	@patch('apps.dashboard.views.timezone.localtime')
	def test_invalid_downtime_is_not_reported_as_zero(self, mock_now, mock_daily):
		from django.utils import timezone
		mock_now.return_value = timezone.make_aware(datetime(2026, 11, 3, 13, 0))
		for downtime in (None, '', 'bad', 'NaN', 'Infinity'):
			with self.subTest(downtime=downtime):
				self.cache.clear()
				mock_daily.return_value = [{
					'start_date': '2026-11-03T08:30:00',
					'actual': '123', 'downtime_minutes': downtime,
				}]
				self.assertEqual(self.client.get(reverse('dashboard-today-production')).status_code, 503)

	@patch('apps.dashboard.views.get_daily_production')
	def test_unknown_site_is_rejected(self, mock_daily):
		response = self.client.get(reverse('dashboard-today-production'), {'site': 'other'})
		self.assertEqual(response.status_code, 400)
		mock_daily.assert_not_called()

	@patch('apps.dashboard.views.get_daily_production')
	def test_unavailable_or_invalid_data_is_not_reported_as_zero(self, mock_daily):
		for rows in [
			[{'actual': '10'}],
			[{'start_date': 'bad', 'actual': '10'}],
		]:
			with self.subTest(rows=rows):
				mock_daily.return_value = rows
				self.assertEqual(self.client.get(reverse('dashboard-today-production')).status_code, 503)
		mock_daily.side_effect = L2LAPIError('Unavailable')
		self.assertEqual(self.client.get(reverse('dashboard-today-production')).status_code, 503)

	@patch('apps.dashboard.views.get_daily_production')
	@patch('apps.dashboard.views.timezone.localtime')
	def test_seven_day_trend_sums_rows_and_keeps_today_metrics(self, mock_now, mock_daily):
		from django.utils import timezone
		mock_now.return_value = timezone.make_aware(datetime(2026, 11, 3, 13, 0))
		mock_daily.return_value = [
			{'start_date': stamp, 'actual': actual, 'downtime_minutes': '2'}
			for stamp, actual in [
				('2026-10-28T08:29:59', '999'),
				('2026-10-28T08:30:00', '0.1'),
				('2026-10-28T08:30:00', '0.2'),
				('2026-11-02T23:00:00Z', '10'),
				('2026-11-03T08:30:00', '100'),
				('2026-11-03T08:30:00', '200'),
				('2026-11-04T08:30:00', '999'),
			]
		]
		for site in ('ACX', 'CNX'):
			response = self.client.get(reverse('dashboard-today-production'), {'site': site, 'include_trend': '1'})
			self.assertEqual(response.status_code, 200)
			self.assertEqual(response.json()['trend'], [
				{'date': day, 'actual': value} for day, value in [
					('2026-10-28', '0.3'), ('2026-10-29', '0'), ('2026-10-30', '0'),
					('2026-10-31', '0'), ('2026-11-01', '0'), ('2026-11-02', '10'), ('2026-11-03', '300'),
				]
			])
			self.assertEqual(response.json()['actual'], '300')
			self.assertEqual(response.json()['downtime_minutes'], '4')
			mock_daily.assert_called_with('2026-10-28 08:30', '2026-11-04 08:30', timeout=15, site=site)
			self.assertEqual(self.client.get(reverse('dashboard-today-production'), {'site': site, 'include_trend': '1'}).json(), response.json())
		self.assertEqual(mock_daily.call_count, 2)

	@patch('apps.dashboard.views.get_daily_production', return_value=[])
	@patch('apps.dashboard.views.timezone.localtime')
	def test_trend_ends_on_calendar_today_even_before_shift_start(self, mock_now, mock_daily):
		from django.utils import timezone
		mock_now.return_value = timezone.make_aware(datetime(2026, 11, 3, 8, 29))
		payload = self.client.get(reverse('dashboard-today-production'), {'include_trend': '1'}).json()
		self.assertEqual(payload['start_date'][:10], '2026-11-02')
		self.assertEqual(len(payload['trend']), 7)
		self.assertEqual(payload['trend'][0], {'date': '2026-10-28', 'actual': '0'})
		self.assertEqual(payload['trend'][-1], {'date': '2026-11-03', 'actual': '0'})
		self.assertNotIn('trend', self.client.get(reverse('dashboard-today-production')).json())
		self.assertEqual(mock_daily.call_count, 2)

	@patch('apps.dashboard.views.get_daily_production')
	@patch('apps.dashboard.views.timezone.localtime')
	def test_invalid_historical_actual_is_not_zero(self, mock_now, mock_daily):
		from django.utils import timezone
		mock_now.return_value = timezone.make_aware(datetime(2026, 11, 3, 13, 0))
		mock_daily.return_value = [{'start_date': '2026-11-02T08:30:00', 'actual': 'NaN'}]
		self.assertEqual(self.client.get(reverse('dashboard-today-production'), {'include_trend': '1'}).status_code, 503)

	def test_post_is_not_allowed(self):
		self.assertEqual(self.client.post(reverse('dashboard-today-production')).status_code, 405)

	@patch('apps.dashboard.views.get_daily_production')
	@patch('apps.dashboard.views.timezone.localtime')
	def test_line_details_sum_by_original_line_and_keep_exact_decimals(self, mock_now, mock_daily):
		from django.utils import timezone
		mock_now.return_value = timezone.make_aware(datetime(2026, 11, 3, 13, 0))
		mock_daily.return_value = [
			{'start_date': stamp, 'line': line, 'line_id': line_id, 'area': 'Weaving Process',
			 'actual': actual, 'demand': demand, 'downtime_minutes': '0', 'products': 1}
			for stamp, line, line_id, actual, demand in [
				('2026-11-03T00:00:00', 'LOOM042A', 1, '0.1', '0.2'),
				('2026-11-03T00:00:00', 'LOOM042A', 1, '0.2', '0.3'),
				('2026-11-03T00:00:00', 'LOOM042B', 2, '0', '10'),
				('2026-11-02T00:00:00', 'LOOM042A', 1, '999', '999'),
			]
		]
		for site in ('ACX', 'CNX'):
			payload = self.client.get(reverse('dashboard-today-production'), {'site': site, 'include_lines': '1'}).json()
			self.assertEqual(payload['actual'], '0.3')
			self.assertEqual(payload['lines'], [
				{'line_id': 1, 'line': 'LOOM042A', 'area': 'Weaving Process', 'product': None, 'demand': '0.5', 'actual': '0.3'},
				{'line_id': 2, 'line': 'LOOM042B', 'area': 'Weaving Process', 'product': None, 'demand': '10', 'actual': '0'},
			])
			self.assertEqual(payload['areas'], ['Weaving Process', 'Dyeing Process', 'Finishing Process'])
			self.assertNotIn('lines', self.client.get(reverse('dashboard-today-production'), {'site': site}).json())
		self.assertEqual(mock_daily.call_count, 4)

	@patch('apps.dashboard.views.get_daily_production')
	@patch('apps.dashboard.views.timezone.localtime')
	def test_invalid_line_demand_is_unavailable_not_zero(self, mock_now, mock_daily):
		from django.utils import timezone
		mock_now.return_value = timezone.make_aware(datetime(2026, 11, 3, 13, 0))
		for demand in ('NaN', None, '-1'):
			with self.subTest(demand=demand):
				self.cache.clear()
				mock_daily.return_value = [{
					'start_date': '2026-11-03T00:00:00',
					'line': 'LOOM001', 'actual': '1', 'demand': demand, 'downtime_minutes': '0',
				}]
				self.assertEqual(self.client.get(reverse('dashboard-today-production'), {'include_lines': '1'}).status_code, 503)

	@patch('django.contrib.auth.models.AnonymousUser.has_perm', return_value=False)
	def test_production_page_inherits_base_and_overview_links_to_it(self, mock_permission):
		response = self.client.get(reverse('dashboard-production'))
		self.assertEqual(response.status_code, 200)
		self.assertTemplateUsed(response, 'dashboard/production_detail.html')
		self.assertTemplateUsed(response, 'base.html')
		self.assertContains(response, 'id="productionSite"')
		self.assertContains(response, 'id="productionArea"')
		self.assertEqual(response.context['production_areas'], ('Weaving Process', 'Dyeing Process', 'Finishing Process'))
		self.assertContains(self.client.get(reverse('dashboard')), 'href="%s"' % reverse('dashboard-production'))

	@patch('apps.dashboard.views.get_daily_production', return_value=[])
	def test_empty_line_data_is_a_successful_empty_list(self, mock_daily):
		response = self.client.get(reverse('dashboard-today-production'), {'include_lines': '1'})
		self.assertEqual(response.status_code, 200)
		self.assertEqual(response.json()['lines'], [])

	@patch('apps.dashboard.views.get_daily_production')
	@patch('apps.dashboard.views.timezone.localtime')
	def test_groups_all_lines_by_exact_area_and_site(self, mock_now, mock_daily):
		from django.utils import timezone
		mock_now.return_value = timezone.make_aware(datetime(2026, 11, 3, 13, 0))
		for site, factor in [('ACX', 1), ('CNX', 2)]:
			with self.subTest(site=site):
				mock_daily.return_value = [
					{'start_date': start, 'area': area, 'actual': str(actual * factor), 'downtime_minutes': '0'}
					for start, area, actual in [
						('2026-11-03T08:30:00', 'Weaving Process', 10),
						('2026-11-03T08:30:00', 'Weaving Process', 20),
						('2026-11-03T08:30:00', 'Dyeing Process', 40),
						('2026-11-03T08:30:00', 'Finishing Process', 99),
						('2026-11-02T08:30:00', 'Weaving Process', 999),
						('2026-11-04T08:30:00', 'Dyeing Process', 999),
					]
				]
				response = self.client.get(reverse('dashboard-today-production'), {'site': site})
				self.assertEqual(response.status_code, 200)
				self.assertEqual(response.json()['area_actual'], {
					'Weaving': str(30 * factor), 'Dyeing': str(40 * factor),
				})
				self.assertEqual(response.json()['actual'], str(169 * factor))
				self.assertEqual(self.client.get(reverse('dashboard-today-production'), {'site': site}).json(), response.json())
		self.assertEqual(mock_daily.call_count, 2)

	@patch('apps.dashboard.views.get_daily_production', return_value=[])
	def test_empty_areas_are_real_zero(self, mock_daily):
		response = self.client.get(reverse('dashboard-today-production'))
		self.assertEqual(response.json()['area_actual'], {'Weaving': '0', 'Dyeing': '0'})
		self.assertEqual(response.json()['equipment_status'], {'running': 0, 'stopped': 0, 'total': 0})

	@patch('apps.dashboard.views.get_daily_production')
	@patch('apps.dashboard.views.timezone.localtime')
	def test_equipment_counts_unique_lines_in_current_shift_per_site(self, mock_now, mock_daily):
		from django.utils import timezone
		mock_now.return_value = timezone.make_aware(datetime(2026, 11, 3, 13, 0))
		for site in ('ACX', 'CNX'):
			with self.subTest(site=site):
				mock_daily.return_value = [
					{'start_date': stamp, 'line_id': line_id, 'line': line, 'actual': actual, 'downtime_minutes': '0'}
					for stamp, line_id, line, actual in [
						('2026-11-03T08:30:00', 1, 'Line A', '0'),
						('2026-11-03T08:30:00', 1, 'Line A', '0.1'),
						('2026-11-03T08:30:00', 1, 'Line A', '0'),
						('2026-11-03T08:30:00', 2, 'Line B', '0.00'),
						('2026-11-03T08:30:00', None, 'Line C', '20'),
						('2026-11-02T08:30:00', 2, 'Line B', '999'),
						('2026-11-04T08:30:00', 4, 'Line D', '999'),
					]
				]
				response = self.client.get(reverse('dashboard-today-production'), {'site': site, 'include_trend': '1'})
				self.assertEqual(response.status_code, 200)
				self.assertEqual(response.json()['equipment_status'], {'running': 2, 'stopped': 1, 'total': 3})
				mock_daily.assert_called_with('2026-10-28 08:30', '2026-11-04 08:30', timeout=15, site=site)

	@patch('apps.dashboard.views.get_daily_production')
	@patch('apps.dashboard.views.timezone.localtime')
	def test_only_acx_merges_loom042_and_loom043_equipment(self, mock_now, mock_daily):
		from django.utils import timezone
		mock_now.return_value = timezone.make_aware(datetime(2026, 11, 3, 13, 0))
		lines = [base + suffix for base in ('LOOM042', 'LOOM043') for suffix in 'ABCD'] + ['LOOM042E', 'LOOM044A']
		for site in ('ACX', 'CNX'):
			for running_line in ('LOOM042B', 'LOOM043D', None):
				with self.subTest(site=site, running_line=running_line):
					self.cache.clear()
					mock_daily.return_value = [
						{
							'start_date': '2026-11-03T08:30:00', 'line_id': index,
							'line': line, 'actual': '0.1' if line == running_line else '0',
							'downtime_minutes': '1', 'area': 'Weaving Process',
						}
						for index, line in enumerate(lines, start=1)
					]
					response = self.client.get(reverse('dashboard-today-production'), {'site': site})
					self.assertEqual(response.status_code, 200)
					total = 4 if site == 'ACX' else 10
					running = 1 if running_line else 0
					self.assertEqual(response.json()['equipment_status'], {'running': running, 'stopped': total - running, 'total': total})
					self.assertEqual(response.json()['actual'], '0.1' if running_line else '0')
					self.assertEqual(response.json()['area_actual']['Weaving'], '0.1' if running_line else '0')
					self.assertEqual(response.json()['downtime_minutes'], '10')

	@patch('apps.dashboard.views.get_daily_production')
	@patch('apps.dashboard.views.timezone.localtime')
	def test_unidentified_or_negative_equipment_is_not_reported_as_stopped(self, mock_now, mock_daily):
		from django.utils import timezone
		mock_now.return_value = timezone.make_aware(datetime(2026, 11, 3, 13, 0))
		for fields in ({'actual': '0'}, {'line_id': 1, 'actual': '-1'}):
			with self.subTest(fields=fields):
				self.cache.clear()
				mock_daily.return_value = [{'start_date': '2026-11-03T08:30:00', 'downtime_minutes': '0', **fields}]
				response = self.client.get(reverse('dashboard-today-production'))
				self.assertEqual(response.status_code, 200)
				self.assertIsNone(response.json()['equipment_status'])

	@patch('apps.dashboard.views.get_daily_production', return_value=[])
	def test_repeated_visitors_share_cached_result(self, mock_daily):
		for unused in range(5):
			response = Client().get(reverse('dashboard-today-production'), {'site': 'ACX'})
			self.assertEqual(response.status_code, 200)
		self.assertEqual(mock_daily.call_count, 1)

	@patch('apps.dashboard.views.get_daily_production', side_effect=L2LAPIError('Unavailable'))
	def test_failure_is_cached_to_limit_retries(self, mock_daily):
		for unused in range(5):
			self.assertEqual(Client().get(reverse('dashboard-today-production')).status_code, 503)
		self.assertEqual(mock_daily.call_count, 1)

	@patch('apps.dashboard.views.get_daily_production')
	def test_concurrent_cold_request_does_not_call_upstream_twice(self, mock_daily):
		def fetch(*args, **kwargs):
			response = Client().get(reverse('dashboard-today-production'))
			self.assertEqual(response.status_code, 503)
			return []
		mock_daily.side_effect = fetch
		self.assertEqual(self.client.get(reverse('dashboard-today-production')).status_code, 200)
		self.assertEqual(mock_daily.call_count, 1)

	@patch('apps.dashboard.views.get_daily_production', return_value=[])
	def test_expired_result_refreshes_and_failure_uses_marked_stale_value(self, mock_daily):
		from django.core.cache.backends.filebased import time as cache_time
		current = cache_time.time()
		with patch('django.core.cache.backends.filebased.time.time', return_value=current):
			self.assertEqual(self.client.get(reverse('dashboard-today-production')).status_code, 200)
		with patch('django.core.cache.backends.filebased.time.time', return_value=current + 31):
			mock_daily.side_effect = L2LAPIError('Unavailable')
			response = self.client.get(reverse('dashboard-today-production'))
			self.assertEqual(response.status_code, 200)
			self.assertTrue(response.json()['stale'])
			self.assertEqual(response.json()['actual'], '0')
			self.assertEqual(response.json()['downtime_minutes'], '0')
			self.assertEqual(mock_daily.call_count, 2)
		with patch('django.core.cache.backends.filebased.time.time', return_value=current + 301):
			self.assertEqual(self.client.get(reverse('dashboard-today-production')).status_code, 503)


class LoginTests(TestCase):
	@classmethod
	def setUpTestData(cls):
		cls.user = get_user_model().objects.create_user(
			username='login-test', password='short'
		)

	def test_form_posts_to_django_login(self):
		response = self.client.get(reverse('login'))
		self.assertContains(response, 'method="post"')
		self.assertContains(response, 'name="csrfmiddlewaretoken"')
		self.assertContains(response, 'name="username"')
		self.assertContains(response, 'name="password"')

	def test_existing_short_password_authenticates_with_csrf(self):
		client = Client(enforce_csrf_checks=True)
		client.get(reverse('login'))
		response = client.post(reverse('login'), {
			'username': self.user.username,
			'password': 'short',
			'csrfmiddlewaretoken': client.cookies['csrftoken'].value,
		})
		self.assertRedirects(response, reverse('dashboard'))
		self.assertEqual(client.session[SESSION_KEY], str(self.user.pk))

	def test_login_uses_browser_session_cookie(self):
		response = self.client.post(reverse('login'), {
			'username': self.user.username,
			'password': 'short',
		})
		cookie = response.cookies[settings.SESSION_COOKIE_NAME]
		self.assertEqual(cookie['max-age'], '')
		self.assertEqual(cookie['expires'], '')
		self.assertTrue(self.client.session.get_expire_at_browser_close())
		response = self.client.get(reverse('dashboard'))
		self.assertTrue(response.wsgi_request.user.is_authenticated)

	def test_browser_without_session_cookie_is_anonymous(self):
		self.client.post(reverse('login'), {
			'username': self.user.username,
			'password': 'short',
		})
		self.client.cookies.pop(settings.SESSION_COOKIE_NAME)
		response = self.client.get(reverse('dashboard'))
		self.assertFalse(response.wsgi_request.user.is_authenticated)
		self.assertNotContains(response, 'class="sidebar-account"')
		self.assertContains(response, 'class="sidebar-login" href="' + reverse('login') + '"')

	def test_staff_login_preserves_configured_redirect(self):
		self.user.is_staff = True
		self.user.save(update_fields=['is_staff'])
		response = self.client.post(reverse('login'), {
			'username': self.user.username,
			'password': 'short',
		})
		self.assertRedirects(response, resolve_url(settings.LOGIN_REDIRECT_URL), fetch_redirect_response=False)

	def test_invalid_password_shows_error_without_authentication(self):
		response = self.client.post(reverse('login'), {
			'username': self.user.username,
			'password': 'incorrect',
		})
		self.assertEqual(response.status_code, 200)
		self.assertContains(response, 'class="error-message show"')
		self.assertContains(response, 'value="login-test"')
		self.assertNotIn(SESSION_KEY, self.client.session)

	def test_missing_csrf_is_rejected(self):
		response = Client(enforce_csrf_checks=True).post(reverse('login'), {
			'username': self.user.username,
			'password': 'short',
		})
		self.assertEqual(response.status_code, 403)

	def test_internal_next_redirect(self):
		response = self.client.post(reverse('login'), {
			'username': self.user.username,
			'password': 'short',
			'next': reverse('dpmu'),
		})
		self.assertRedirects(response, reverse('dpmu'), fetch_redirect_response=False)

	def test_external_next_redirect_is_rejected(self):
		response = self.client.post(reverse('login'), {
			'username': self.user.username,
			'password': 'short',
			'next': 'https://example.com/',
		})
		self.assertRedirects(response, reverse('dashboard'))


class AccountNavigationTests(TestCase):
	@classmethod
	def setUpTestData(cls):
		cls.user = get_user_model().objects.create_user(username='account-user')
		cls.user.groups.add(Group.objects.get(name='manager'))

	def test_anonymous_navigation_shows_login_only(self):
		response = self.client.get(reverse('dashboard'))
		self.assertContains(response, 'class="sidebar-login" href="' + reverse('login') + '"')
		self.assertNotContains(response, 'class="sidebar-account"')
		self.assertNotContains(response, 'class="sidebar-logout-form"')

	def test_authenticated_navigation_shows_username_and_logout(self):
		self.client.force_login(self.user)
		response = self.client.get(reverse('dashboard'))
		self.assertContains(response, '<span class="sidebar-username-text">account-user</span>', html=True)
		self.assertContains(response, 'class="sidebar-logout-form" method="post" action="' + reverse('logout') + '"')
		self.assertContains(response, 'name="csrfmiddlewaretoken"')
		self.assertNotContains(response, 'class="sidebar-login" href="' + reverse('login') + '"')

	def test_username_is_html_escaped(self):
		self.user.username = '<script>unsafe</script>'
		self.user.save(update_fields=['username'])
		self.client.force_login(self.user)
		response = self.client.get(reverse('dashboard'))
		self.assertContains(response, '&lt;script&gt;unsafe&lt;/script&gt;')
		self.assertNotContains(response, '<script>unsafe</script>')

	def test_long_username_is_preserved_in_tooltip(self):
		self.user.username = 'account-' + 'long' * 35
		self.user.save(update_fields=['username'])
		self.client.force_login(self.user)
		response = self.client.get(reverse('dashboard'))
		self.assertContains(response, 'title="' + self.user.username + '"')

	def test_logout_post_with_csrf_clears_session_and_permissions(self):
		client = Client(enforce_csrf_checks=True)
		client.force_login(self.user)
		response = client.get(reverse('dashboard'))
		self.assertContains(response, 'data-page="equipment"')
		response = client.post(reverse('logout'), {
			'csrfmiddlewaretoken': client.cookies['csrftoken'].value,
		})
		self.assertRedirects(response, reverse('dashboard'))
		self.assertNotIn(SESSION_KEY, client.session)
		response = client.get(reverse('dashboard'))
		self.assertNotContains(response, 'class="sidebar-account"')
		self.assertNotContains(response, 'data-page="equipment"')
		self.assertNotContains(response, 'data-page="dpmu"')
		self.assertRedirects(client.get(reverse('equipment')), reverse('login') + '?next=' + reverse('equipment'))

	def test_logout_without_csrf_does_not_end_session(self):
		client = Client(enforce_csrf_checks=True)
		client.force_login(self.user)
		response = client.post(reverse('logout'))
		self.assertEqual(response.status_code, 403)
		self.assertIn(SESSION_KEY, client.session)

	def test_logout_get_does_not_end_session(self):
		self.client.force_login(self.user)
		response = self.client.get(reverse('logout'))
		self.assertEqual(response.status_code, 405)
		self.assertIn(SESSION_KEY, self.client.session)


class PagePermissionTests(TestCase):
	@classmethod
	def setUpTestData(cls):
		cls.users = {}
		for name in ('visitor', 'user', 'manager', 'admin'):
			group, _ = Group.objects.get_or_create(name=name)
			user = get_user_model().objects.create_user(
				username='page-' + name, password='page-test-password',
			)
			user.groups.add(group)
			cls.users[name] = user

	def test_migration_grants_both_permissions_only_to_privileged_groups(self):
		for name in ('visitor', 'user', 'manager', 'admin'):
			with self.subTest(group=name):
				permissions = set(Group.objects.get(name=name).permissions.filter(
					content_type__app_label='accounts',
				).values_list('codename', flat=True))
				expected = {'view_equipment', 'view_dpmu'} if name in ('manager', 'admin') else set()
				self.assertEqual(permissions, expected)

	def test_anonymous_requests_redirect_to_project_login(self):
		for name in ('equipment', 'dpmu'):
			with self.subTest(page=name):
				url = reverse(name)
				self.assertRedirects(self.client.get(url), reverse('login') + '?next=' + url)
		response = self.client.get(reverse('dashboard'))
		self.assertNotContains(response, 'data-page="equipment"')
		self.assertNotContains(response, 'data-page="dpmu"')

	def test_group_access_matrix_and_navigation(self):
		for name, user in self.users.items():
			self.client.force_login(user)
			allowed = name in ('manager', 'admin')
			response = self.client.get(reverse('dashboard'))
			self.assertEqual(response.status_code, 200)
			self.assertContains(response, 'data-page="briefing"')
			for page in ('equipment', 'dpmu'):
				with self.subTest(group=name, page=page):
					if allowed:
						self.assertContains(response, 'data-page="' + page + '"')
					else:
						self.assertNotContains(response, 'data-page="' + page + '"')
					page_response = self.client.get(reverse(page))
					self.assertEqual(page_response.status_code, 200 if allowed else 403)

	def test_non_staff_group_logins_land_on_dashboard(self):
		for name, user in self.users.items():
			with self.subTest(group=name):
				self.client.logout()
				response = self.client.post(reverse('login'), {
					'username': user.username,
					'password': 'page-test-password',
				})
				self.assertRedirects(response, reverse('dashboard'))

	def test_staff_flag_alone_does_not_grant_page_access(self):
		user = get_user_model().objects.create_user(username='staff-only', is_staff=True)
		self.client.force_login(user)
		for page in ('equipment', 'dpmu'):
			self.assertEqual(self.client.get(reverse(page)).status_code, 403)

	def test_ungrouped_user_has_no_access(self):
		user = get_user_model().objects.create_user(username='ungrouped')
		self.client.force_login(user)
		for page in ('equipment', 'dpmu'):
			self.assertEqual(self.client.get(reverse(page)).status_code, 403)

	def test_superuser_has_access_without_group_membership(self):
		user = get_user_model().objects.create_user(
			username='superuser', is_staff=True, is_superuser=True,
		)
		self.client.force_login(user)
		for page in ('equipment', 'dpmu'):
			self.assertEqual(self.client.get(reverse(page)).status_code, 200)

	def test_multiple_groups_combine_permissions(self):
		user = self.users['user']
		user.groups.add(Group.objects.get(name='manager'))
		self.client.force_login(user)
		for page in ('equipment', 'dpmu'):
			self.assertEqual(self.client.get(reverse(page)).status_code, 200)

	def test_each_page_uses_its_own_permission(self):
		user = get_user_model().objects.create_user(username='equipment-only')
		user.user_permissions.add(Permission.objects.get(
			content_type__app_label='accounts', codename='view_equipment',
		))
		self.client.force_login(user)
		response = self.client.get(reverse('dashboard'))
		self.assertContains(response, 'data-page="equipment"')
		self.assertNotContains(response, 'data-page="dpmu"')
		self.assertEqual(self.client.get(reverse('equipment')).status_code, 200)
		self.assertEqual(self.client.get(reverse('dpmu')).status_code, 403)
