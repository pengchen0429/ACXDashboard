import sqlite3
from datetime import datetime, timezone as datetime_timezone
from unittest.mock import patch

from django.db import DatabaseError
from django.template.loader import render_to_string
from django.test import RequestFactory, SimpleTestCase, override_settings
from django.utils.html import strip_tags

from .views import briefing, get_safety_context, get_safety_counts, safety_data


@override_settings(TIME_ZONE='Asia/Shanghai', SNOWFLAKE_DISPATCH_TIME_ZONE='Asia/Shanghai')
class SafetyCountsTests(SimpleTestCase):
	def setUp(self):
		self.now = datetime(2026, 10, 29, 1, tzinfo=datetime_timezone.utc)
		self.types_patch = patch('apps.briefing.views.SAFETY_DISPATCH_TYPE_CODES', (
			'Safety Jidoka - Unsafe Behaviors',
		))
		self.types_patch.start()
		self.addCleanup(self.types_patch.stop)
		self.connection_patch = patch('apps.briefing.views.connections')
		self.connections = self.connection_patch.start()
		self.addCleanup(self.connection_patch.stop)
		self.cursor = self.connections['snowflake'].cursor.return_value.__enter__.return_value
		self.cursor.fetchall.return_value = [
			('Weaving Process', 4, 3, 10), ('Dyeing Process', 2, 2, 6), ('ACX Finishing', 1, 0, 2),
		]

	def test_window_completion_and_current_unclosed_are_separate(self):
		with sqlite3.connect(':memory:') as database:
			database.create_function('CONVERT_TIMEZONE', 3, lambda source, target, value: value)
			def parse_timestamp(value):
				try:
					return datetime.fromisoformat(value).isoformat(' ')
				except (TypeError, ValueError):
					return None
			database.create_function('TRY_TO_TIMESTAMP_NTZ', 1, parse_timestamp)
			database.execute('CREATE TABLE dispatch_fixture (areacode, dispatchtypecode, SERVER_SITE_NAME, reported, completed, closed)')
			rows = [
				('2026-10-01 09:00', None, None),
				('2026-10-28 08:31', '2026-10-28 09:00', '2026-10-28 09:01'),
				('2026-10-01 09:00', '2026-10-28 09:00', None),
				('2026-10-28 10:00', '2026-10-29 08:40', '2026-10-29 08:45'),
				('2026-10-28 11:00', None, None),
				('2026-10-29 08:45', None, '  '),
				('2026-10-29 10:00', None, None),
				('2026-10-28 08:30:59', '2026-10-28 09:00', '2026-10-28 09:01'),
				('2026-10-29 08:30:59', '2026-10-29 08:30:59', None),
				('2026-10-29 08:31', None, None),
				('2026-10-01 09:00', None, 'invalid'),
				('2026-10-01 09:00', None, '2026-10-30 09:00'),
			]
			database.executemany('INSERT INTO dispatch_fixture VALUES (?, ?, ?, ?, ?, ?)', [
				('Weaving Process', 'Safety Jidoka - Unsafe Behaviors', 'china^907371', *row)
				for row in rows
			])
			def execute(query, params):
				query = query.replace('PRD_MANUFACTURING_DB.G_L2L_CONSUMPTION.VW_DISPATCHES', 'dispatch_fixture').replace('%s', '?')
				params = [value.isoformat(' ') if isinstance(value, datetime) else value for value in params]
				self.cursor.fetchall.return_value = database.execute(query, params).fetchall()
			self.cursor.execute.side_effect = execute
			result = get_safety_counts(self.now)
			later = get_safety_counts(self.now.replace(hour=2))
		self.assertEqual((result['reported'], result['completed'], result['unclosed']), (4, 2, 7))
		self.assertEqual((later['reported'], later['completed'], later['unclosed']), (4, 2, 8))

	def test_counts_and_exact_filters(self):
		result = get_safety_counts(self.now)
		self.assertEqual((result['reported'], result['completed']), (7, 5))
		self.assertTrue(result['available'])
		query, params = self.cursor.execute.call_args.args
		self.assertIn('TRY_TO_TIMESTAMP_NTZ("reported")', query)
		self.assertIn('TRY_TO_TIMESTAMP_NTZ("completed")', query)
		self.assertIn('"areacode" IN (%s, %s, %s) AND "dispatchtypecode" IN (%s)', query)
		self.assertIn('AND "SERVER_SITE_NAME" IN (%s)', query)
		self.assertIn('reported_at >= %s AND reported_at < %s', query)
		self.assertIn('completed_at >= %s AND completed_at < %s', query)
		self.assertIn('AND completed_at >= %s AND completed_at < %s', query)
		self.assertIn('reported_at <= %s', query)
		self.assertIn('closed_value IS NULL OR closed_at > %s', query)
		self.assertIn('TRY_TO_TIMESTAMP_NTZ("closed")', query)
		self.assertEqual(result['unclosed'], 18)
		self.assertIn('GROUP BY area_code', query)
		self.assertEqual(params, [
			'Asia/Shanghai', 'Asia/Shanghai', 'Asia/Shanghai',
			'Weaving Process', 'Dyeing Process', 'ACX Finishing',
			'Safety Jidoka - Unsafe Behaviors',
			'china^907371',
			datetime(2026, 10, 28, 8, 31), datetime(2026, 10, 29, 8, 31),
			datetime(2026, 10, 28, 8, 31), datetime(2026, 10, 29, 8, 31),
			datetime(2026, 10, 28, 8, 31), datetime(2026, 10, 29, 8, 31),
			datetime(2026, 10, 29, 9), datetime(2026, 10, 29, 9),
		])

	def test_multiple_dispatch_types_are_parameterized(self):
		dispatch_types = ('Safety Jidoka - Unsafe Behaviors', "Additional safety type's name")
		with patch('apps.briefing.views.SAFETY_DISPATCH_TYPE_CODES', dispatch_types):
			result = get_safety_counts(self.now)
		query, params = self.cursor.execute.call_args.args
		self.assertIn('"dispatchtypecode" IN (%s, %s)', query)
		self.assertEqual(
			params[3 + len(result['area_codes']):-8 - len(result['server_site_names'])],
			list(dispatch_types),
		)
		self.assertNotIn(dispatch_types[1], query)
		self.assertEqual(query.count('%s'), len(params))
		self.assertEqual((result['reported'], result['completed']), (7, 5))
		self.assertEqual(result['dispatch_types'], dispatch_types)

	def test_multiple_areas_are_parameterized(self):
		area_codes = ('Dyeing Process', "Additional area's name")
		self.cursor.fetchall.return_value = [('Dyeing Process', 7, 5, 6)]
		with patch('apps.briefing.views.SAFETY_AREA_CODES', area_codes):
			result = get_safety_counts(self.now)
		query, params = self.cursor.execute.call_args.args
		self.assertIn('"areacode" IN (%s, %s)', query)
		self.assertEqual(params[3:5], list(area_codes))
		self.assertNotIn(area_codes[1], query)
		self.assertEqual(query.count('%s'), len(params))
		self.assertEqual(result['area_codes'], area_codes)
		self.assertEqual((result['reported'], result['completed']), (7, 5))

	def test_multiple_sites_are_parameterized(self):
		site_names = ('china^907371', "Additional site's name")
		with patch('apps.briefing.views.SAFETY_SERVER_SITE_NAMES', site_names):
			result = get_safety_counts(self.now)
		query, params = self.cursor.execute.call_args.args
		self.assertIn('AND "SERVER_SITE_NAME" IN (%s, %s)', query)
		self.assertEqual(params[-8 - len(site_names):-8], list(site_names))
		self.assertNotIn(site_names[1], query)
		self.assertEqual(query.count('%s'), len(params))
		self.assertEqual(result['server_site_names'], site_names)
		self.assertEqual((result['reported'], result['completed']), (7, 5))

	def test_empty_sites_does_not_query_all_sites(self):
		self.connections.reset_mock()
		with patch('apps.briefing.views.SAFETY_SERVER_SITE_NAMES', ()):
			result = get_safety_counts(self.now)
		self.connections.__getitem__.assert_not_called()
		self.assertTrue(result['available'])
		self.assertEqual((result['reported'], result['completed']), (0, 0))
		self.assertTrue(all(area['reported'] == area['completed'] == 0 for area in result['areas']))

	def test_area_counts_follow_configuration_order_and_fill_missing_with_zero(self):
		self.cursor.fetchall.return_value = [('ACX Finishing', 1, 2, 2), ('Weaving Process', 4, 3, 10)]
		result = get_safety_counts(self.now)
		self.assertEqual(result['areas'], [
			{'code': 'Weaving Process', 'label': 'Weaving', 'reported': 4, 'completed': 3, 'unclosed': 10},
			{'code': 'Dyeing Process', 'label': 'Dyeing', 'reported': 0, 'completed': 0, 'unclosed': 0},
			{'code': 'ACX Finishing', 'label': 'Finishing', 'reported': 1, 'completed': 2, 'unclosed': 2},
		])
		self.assertEqual((result['reported'], result['completed']), (5, 5))

	def test_empty_areas_does_not_query_all_areas(self):
		self.connections.reset_mock()
		with patch('apps.briefing.views.SAFETY_AREA_CODES', ()):
			result = get_safety_counts(self.now)
		self.connections.__getitem__.assert_not_called()
		self.assertTrue(result['available'])
		self.assertEqual((result['reported'], result['completed']), (0, 0))

	def test_empty_dispatch_types_does_not_query_all_types(self):
		self.connections.reset_mock()
		with patch('apps.briefing.views.SAFETY_DISPATCH_TYPE_CODES', ()):
			result = get_safety_counts(self.now)
		self.connections.__getitem__.assert_not_called()
		self.assertTrue(result['available'])
		self.assertEqual((result['reported'], result['completed']), (0, 0))

	def test_window_uses_shanghai_calendar_date(self):
		result = get_safety_counts(datetime(2026, 10, 28, 17, tzinfo=datetime_timezone.utc))
		self.assertEqual(result['start'], datetime(2026, 10, 28, 8, 31))
		self.assertEqual(result['end'], datetime(2026, 10, 29, 8, 30))

	def test_window_crosses_year_boundary(self):
		result = get_safety_counts(datetime(2026, 1, 1, 1, tzinfo=datetime_timezone.utc))
		self.assertEqual(result['start'], datetime(2025, 12, 31, 8, 31))
		self.assertEqual(result['end'], datetime(2026, 1, 1, 8, 30))

	def test_custom_window_includes_entire_end_minute(self):
		start = datetime(2026, 10, 1, 7, 15)
		end = datetime(2026, 10, 3, 16, 45)
		result = get_safety_counts(self.now, start=start, end=end)
		self.assertEqual((result['start'], result['end']), (start, end))
		self.assertEqual(self.cursor.execute.call_args.args[1][-8:], [
			start, datetime(2026, 10, 3, 16, 46),
			start, datetime(2026, 10, 3, 16, 46),
			start, datetime(2026, 10, 3, 16, 46),
			datetime(2026, 10, 29, 9), datetime(2026, 10, 29, 9),
		])

	def test_source_timezone_is_configurable(self):
		with override_settings(SNOWFLAKE_DISPATCH_TIME_ZONE='UTC'):
			get_safety_counts(self.now)
		self.assertEqual(self.cursor.execute.call_args.args[1][:3], ['UTC', 'UTC', 'UTC'])

	def test_no_matches_displays_zero(self):
		self.cursor.fetchall.return_value = []
		result = get_safety_counts(self.now)
		self.assertTrue(result['available'])
		self.assertEqual((result['reported'], result['completed']), (0, 0))
		self.assertTrue(all(area['reported'] == area['completed'] == 0 for area in result['areas']))
		page = render_to_string('briefing/briefing.html', {'safety': result})
		self.assertIn('id="safety-reported">0</span>', page)
		self.assertNotIn('187<span', page)

	def test_template_displays_one_line_per_area(self):
		page = render_to_string('briefing/briefing.html', {'safety': get_safety_counts(self.now)})
		text = ' '.join(strip_tags(page).split())
		self.assertEqual(page.count('class="safety-area-row"'), 3)
		self.assertEqual(page.count('class="safety-area-reported"'), 3)
		self.assertEqual(page.count('class="safety-area-completed"'), 3)
		self.assertEqual(page.count('class="safety-area-unclosed"'), 3)
		for label, reported, completed, unclosed in [('Weaving', 4, 3, 10), ('Dyeing', 2, 2, 6), ('Finishing', 1, 0, 2)]:
			self.assertIn(f'{label} \u65b0\u589e {reported} \u8d77\uff0c \u5b8c\u6210 {completed} \u8d77\uff0c \u672a\u5173\u95ed {unclosed} \u8d77', text)
		self.assertLess(page.index('data-label="Weaving"'), page.index('data-label="Dyeing"'))
		self.assertLess(page.index('data-label="Dyeing"'), page.index('data-label="Finishing"'))

	def test_database_failure_does_not_display_zero(self):
		self.cursor.execute.side_effect = DatabaseError('unavailable')
		with self.assertLogs('apps.briefing.views', level='ERROR'):
			result = get_safety_counts(self.now)
		self.assertFalse(result['available'])
		self.assertIsNone(result['reported'])
		self.assertIsNone(result['completed'])
		self.assertIsNone(result['unclosed'])
		self.assertTrue(all(area['unclosed'] is None for area in result['areas']))
		self.assertTrue(all(area['reported'] is None for area in result['areas']))
		page = render_to_string('briefing/briefing.html', {'safety': result})
		self.assertIn('id="safety-reported">--</span>', page)

	def test_initial_page_displays_loading_state_and_endpoint(self):
		page = render_to_string('briefing/briefing.html', {'safety': get_safety_context(self.now)})
		self.assertIn('data-url="/briefing/safety-data/"', page)
		self.assertIn('aria-busy="true"', page)
		self.assertIn('id="safety-time-filter"', page)
		self.assertEqual(page.count('type="datetime-local"'), 2)
		self.assertIn('value="2026-10-28T08:31"', page)
		self.assertIn('value="2026-10-29T08:30"', page)
		self.assertNotIn('id="safety-status"', page)
		self.assertNotIn('id="safety-retry"', page)
		self.assertNotIn('safety-feedback', page)
		self.assertEqual(page.count('class="safety-area-row"'), 3)
		self.assertNotIn('id="safety-reported">0</span>', page)

	def test_page_does_not_wait_for_snowflake(self):
		with patch('apps.briefing.views.render') as render, patch(
			'apps.briefing.views.get_safety_counts', side_effect=AssertionError('Must not query'),
		) as counts:
			briefing(RequestFactory().get('/briefing/'))
		counts.assert_not_called()
		self.assertEqual(render.call_args.args[1], 'briefing/briefing.html')
		self.assertIsNone(render.call_args.args[2]['safety']['reported'])
		self.assertTrue(render.call_args.args[2]['safety']['loading'])

	def test_opening_page_always_uses_default_window(self):
		with patch('apps.briefing.views.render') as render, patch(
			'apps.briefing.views.timezone.now', return_value=self.now,
		):
			briefing(RequestFactory().get('/briefing/', {
				'start_time': '2026-10-01T07:15', 'end_time': '2026-10-03T16:45',
			}))
		context = render.call_args.args[2]['safety']
		self.assertEqual(context['start'], datetime(2026, 10, 28, 8, 31))
		self.assertEqual(context['end'], datetime(2026, 10, 29, 8, 30))


@override_settings(
	TIME_ZONE='Asia/Shanghai', SNOWFLAKE_DISPATCH_TIME_ZONE='Asia/Shanghai',
)
class SafetyDataTests(SimpleTestCase):
	def setUp(self):
		self.now = datetime(2026, 10, 29, 1, tzinfo=datetime_timezone.utc)
		self.time_patch = patch('apps.briefing.views.timezone.now', return_value=self.now)
		self.time_patch.start()
		self.addCleanup(self.time_patch.stop)
		self.result = get_safety_context(self.now)
		self.result.update(reported=7, completed=5, unclosed=18, available=True, loading=False)
		for area, counts in zip(self.result['areas'], [(4, 3, 10), (2, 2, 6), (1, 0, 2)]):
			area.update(reported=counts[0], completed=counts[1], unclosed=counts[2])
		self.counts_patch = patch('apps.briefing.views.get_safety_counts', return_value=self.result)
		self.counts = self.counts_patch.start()
		self.addCleanup(self.counts_patch.stop)
		self.request = RequestFactory().get('/briefing/safety-data/')

	def test_route_returns_counts_without_reusing_old_snapshot(self):
		response = self.client.get('/briefing/safety-data/')
		self.assertEqual(response.status_code, 200)
		self.assertEqual(response.json()['reported'], 7)
		self.assertEqual(response.json()['completed'], 5)
		self.assertEqual(response.json()['unclosed'], 18)
		self.assertEqual(response.json()['areas'][0]['unclosed'], 10)
		self.assertEqual(response.json()['areas'][0]['label'], 'Weaving')
		self.assertEqual(response.json()['areas'][0]['reported'], 4)
		self.assertIn('no-store', response['Cache-Control'])
		self.assertEqual(safety_data(self.request).status_code, 200)
		self.assertEqual(self.counts.call_count, 2)
		self.counts.assert_called_with(
			self.now, start=datetime(2026, 10, 28, 8, 31), end=datetime(2026, 10, 29, 8, 30),
		)

	def test_custom_window_is_passed_to_counts(self):
		response = self.client.get('/briefing/safety-data/', {
			'start_time': '2026-10-01T07:15', 'end_time': '2026-10-03T16:45',
		})
		self.assertEqual(response.status_code, 200)
		self.counts.assert_called_once_with(
			self.now, start=datetime(2026, 10, 1, 7, 15), end=datetime(2026, 10, 3, 16, 45),
		)

	def test_invalid_time_filters_do_not_query(self):
		for params in [
			{'start_time': '2026-10-01T07:15'},
			{'end_time': '2026-10-03T16:45'},
			{'start_time': 'invalid', 'end_time': '2026-10-03T16:45'},
			{'start_time': '2026-02-30T07:15', 'end_time': '2026-10-03T16:45'},
			{'start_time': '2026-10-04T07:15', 'end_time': '2026-10-03T16:45'},
			{'start_time': '2026-10-01T07:15:30', 'end_time': '2026-10-03T16:45'},
			{'start_time': '2026-10-01T07:15Z', 'end_time': '2026-10-03T16:45'},
			{'start_time': '2026-10-01T07:15', 'end_time': '9999-12-31T23:59'},
		]:
			with self.subTest(params=params):
				self.assertEqual(self.client.get('/briefing/safety-data/', params).status_code, 400)
		self.counts.assert_not_called()

	def test_same_start_and_end_minute_is_valid(self):
		response = self.client.get('/briefing/safety-data/', {
			'start_time': '2026-10-01T07:15', 'end_time': '2026-10-01T07:15',
		})
		self.assertEqual(response.status_code, 200)

	def test_each_time_filter_request_queries_current_counts(self):
		for params in [
			{'start_time': '2026-10-01T07:15', 'end_time': '2026-10-03T16:45'},
			{'start_time': '2026-10-01T07:15', 'end_time': '2026-10-03T16:46'},
			{'start_time': '2026-10-01T07:16', 'end_time': '2026-10-03T16:46'},
		]:
			self.client.get('/briefing/safety-data/', params)
			self.client.get('/briefing/safety-data/', params)
		self.assertEqual(self.counts.call_count, 6)

	def test_same_window_uses_current_request_time(self):
		safety_data(self.request)
		later = datetime(2026, 10, 29, 2, tzinfo=datetime_timezone.utc)
		with patch('apps.briefing.views.timezone.now', return_value=later):
			safety_data(self.request)
		self.assertEqual(self.counts.call_args_list[0].args, (self.now,))
		self.assertEqual(self.counts.call_args_list[1].args, (later,))
		self.assertEqual(self.counts.call_args_list[0].kwargs, self.counts.call_args_list[1].kwargs)

	def test_failure_returns_503_and_is_not_cached(self):
		self.result.update(reported=None, completed=None, available=False)
		self.assertEqual(safety_data(self.request).status_code, 503)
		self.assertEqual(safety_data(self.request).status_code, 503)
		self.assertEqual(self.counts.call_count, 2)

	def test_requests_with_changed_dispatch_types_are_queried(self):
		safety_data(self.request)
		with patch('apps.briefing.views.SAFETY_DISPATCH_TYPE_CODES', ('Additional type',)):
			safety_data(self.request)
		self.assertEqual(self.counts.call_count, 2)

	def test_requests_with_changed_source_timezone_are_queried(self):
		safety_data(self.request)
		with override_settings(SNOWFLAKE_DISPATCH_TIME_ZONE='UTC'):
			safety_data(self.request)
		self.assertEqual(self.counts.call_count, 2)

	def test_requests_with_changed_areas_are_queried(self):
		safety_data(self.request)
		with patch('apps.briefing.views.SAFETY_AREA_CODES', ('Dyeing Process',)):
			safety_data(self.request)
		self.assertEqual(self.counts.call_count, 2)

	def test_requests_with_changed_calendar_date_are_queried(self):
		safety_data(self.request)
		with patch('apps.briefing.views.timezone.now', return_value=datetime(
			2026, 10, 30, 1, tzinfo=datetime_timezone.utc,
		)):
			safety_data(self.request)
		self.assertEqual(self.counts.call_count, 2)

	def test_requests_with_changed_sites_are_queried(self):
		safety_data(self.request)
		with patch('apps.briefing.views.SAFETY_SERVER_SITE_NAMES', ('china^123456',)):
			safety_data(self.request)
		self.assertEqual(self.counts.call_count, 2)

	def test_post_is_rejected(self):
		response = safety_data(RequestFactory().post('/briefing/safety-data/'))
		self.assertEqual(response.status_code, 405)
		self.counts.assert_not_called()
