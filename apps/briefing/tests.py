from datetime import datetime, timezone as datetime_timezone
from unittest.mock import patch

from django.core.cache import cache
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
			('Weaving Process', 4, 3), ('Dyeing Process', 2, 2), ('ACX Finishing', 1, 0),
		]

	def test_independent_counts_and_exact_filters(self):
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
		self.assertNotIn('closed', query)
		self.assertIn('GROUP BY area_code', query)
		self.assertEqual(params, [
			'Asia/Shanghai', 'Asia/Shanghai',
			'Weaving Process', 'Dyeing Process', 'ACX Finishing',
			'Safety Jidoka - Unsafe Behaviors',
			'china^907371',
			datetime(2026, 10, 28, 8, 31), datetime(2026, 10, 29, 8, 31),
			datetime(2026, 10, 28, 8, 31), datetime(2026, 10, 29, 8, 31),
		])

	def test_multiple_dispatch_types_are_parameterized(self):
		dispatch_types = ('Safety Jidoka - Unsafe Behaviors', "Additional safety type's name")
		with patch('apps.briefing.views.SAFETY_DISPATCH_TYPE_CODES', dispatch_types):
			result = get_safety_counts(self.now)
		query, params = self.cursor.execute.call_args.args
		self.assertIn('"dispatchtypecode" IN (%s, %s)', query)
		self.assertEqual(
			params[2 + len(result['area_codes']):-4 - len(result['server_site_names'])],
			list(dispatch_types),
		)
		self.assertNotIn(dispatch_types[1], query)
		self.assertEqual(query.count('%s'), len(params))
		self.assertEqual((result['reported'], result['completed']), (7, 5))
		self.assertEqual(result['dispatch_types'], dispatch_types)

	def test_multiple_areas_are_parameterized(self):
		area_codes = ('Dyeing Process', "Additional area's name")
		self.cursor.fetchall.return_value = [('Dyeing Process', 7, 5)]
		with patch('apps.briefing.views.SAFETY_AREA_CODES', area_codes):
			result = get_safety_counts(self.now)
		query, params = self.cursor.execute.call_args.args
		self.assertIn('"areacode" IN (%s, %s)', query)
		self.assertEqual(params[2:4], list(area_codes))
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
		self.assertEqual(params[-4 - len(site_names):-4], list(site_names))
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
		self.cursor.fetchall.return_value = [('ACX Finishing', 1, 2), ('Weaving Process', 4, 3)]
		result = get_safety_counts(self.now)
		self.assertEqual(result['areas'], [
			{'code': 'Weaving Process', 'label': 'Weaving', 'reported': 4, 'completed': 3},
			{'code': 'Dyeing Process', 'label': 'Dyeing', 'reported': 0, 'completed': 0},
			{'code': 'ACX Finishing', 'label': 'Finishing', 'reported': 1, 'completed': 2},
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

	def test_source_timezone_is_configurable(self):
		with override_settings(SNOWFLAKE_DISPATCH_TIME_ZONE='UTC'):
			get_safety_counts(self.now)
		self.assertEqual(self.cursor.execute.call_args.args[1][:2], ['UTC', 'UTC'])

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
		for label, reported, completed in [('Weaving', 4, 3), ('Dyeing', 2, 2), ('Finishing', 1, 0)]:
			self.assertIn(f'{label} \u65b0\u589e {reported} \u8d77\uff0c\u5b8c\u6210 {completed} \u8d77', text)
		self.assertLess(page.index('data-label="Weaving"'), page.index('data-label="Dyeing"'))
		self.assertLess(page.index('data-label="Dyeing"'), page.index('data-label="Finishing"'))

	def test_database_failure_does_not_display_zero(self):
		self.cursor.execute.side_effect = DatabaseError('unavailable')
		with self.assertLogs('apps.briefing.views', level='ERROR'):
			result = get_safety_counts(self.now)
		self.assertFalse(result['available'])
		self.assertIsNone(result['reported'])
		self.assertIsNone(result['completed'])
		self.assertTrue(all(area['reported'] is None for area in result['areas']))
		page = render_to_string('briefing/briefing.html', {'safety': result})
		self.assertIn('id="safety-reported">--</span>', page)

	def test_initial_page_displays_loading_state_and_endpoint(self):
		page = render_to_string('briefing/briefing.html', {'safety': get_safety_context(self.now)})
		self.assertIn('data-url="/briefing/safety-data/"', page)
		self.assertIn('aria-busy="true"', page)
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


@override_settings(
	TIME_ZONE='Asia/Shanghai', SNOWFLAKE_DISPATCH_TIME_ZONE='Asia/Shanghai',
	CACHES={'default': {'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
		'LOCATION': 'briefing-safety-tests'}},
)
class SafetyDataTests(SimpleTestCase):
	def setUp(self):
		cache.clear()
		self.addCleanup(cache.clear)
		self.now = datetime(2026, 10, 29, 1, tzinfo=datetime_timezone.utc)
		self.time_patch = patch('apps.briefing.views.timezone.now', return_value=self.now)
		self.time_patch.start()
		self.addCleanup(self.time_patch.stop)
		self.result = get_safety_context(self.now)
		self.result.update(reported=7, completed=5, available=True, loading=False)
		for area, counts in zip(self.result['areas'], [(4, 3), (2, 2), (1, 0)]):
			area.update(reported=counts[0], completed=counts[1])
		self.counts_patch = patch('apps.briefing.views.get_safety_counts', return_value=self.result)
		self.counts = self.counts_patch.start()
		self.addCleanup(self.counts_patch.stop)
		self.request = RequestFactory().get('/briefing/safety-data/')

	def test_route_returns_counts_and_uses_cache(self):
		response = self.client.get('/briefing/safety-data/')
		self.assertEqual(response.status_code, 200)
		self.assertEqual(response.json()['reported'], 7)
		self.assertEqual(response.json()['completed'], 5)
		self.assertEqual(response.json()['areas'][0]['label'], 'Weaving')
		self.assertEqual(response.json()['areas'][0]['reported'], 4)
		self.assertIn('no-store', response['Cache-Control'])
		self.assertEqual(safety_data(self.request).status_code, 200)
		self.counts.assert_called_once_with(self.now)

	def test_cache_expires_after_sixty_seconds(self):
		with patch('apps.briefing.views.cache.set') as store:
			safety_data(self.request)
		self.assertEqual(store.call_args.kwargs['timeout'], 60)

	def test_failure_returns_503_and_is_not_cached(self):
		self.result.update(reported=None, completed=None, available=False)
		self.assertEqual(safety_data(self.request).status_code, 503)
		self.assertEqual(safety_data(self.request).status_code, 503)
		self.assertEqual(self.counts.call_count, 2)

	def test_cache_changes_with_dispatch_types(self):
		safety_data(self.request)
		with patch('apps.briefing.views.SAFETY_DISPATCH_TYPE_CODES', ('Additional type',)):
			safety_data(self.request)
		self.assertEqual(self.counts.call_count, 2)

	def test_cache_changes_with_source_timezone(self):
		safety_data(self.request)
		with override_settings(SNOWFLAKE_DISPATCH_TIME_ZONE='UTC'):
			safety_data(self.request)
		self.assertEqual(self.counts.call_count, 2)

	def test_cache_changes_with_areas(self):
		safety_data(self.request)
		with patch('apps.briefing.views.SAFETY_AREA_CODES', ('Dyeing Process',)):
			safety_data(self.request)
		self.assertEqual(self.counts.call_count, 2)

	def test_cache_changes_with_calendar_date(self):
		safety_data(self.request)
		with patch('apps.briefing.views.timezone.now', return_value=datetime(
			2026, 10, 30, 1, tzinfo=datetime_timezone.utc,
		)):
			safety_data(self.request)
		self.assertEqual(self.counts.call_count, 2)

	def test_cache_changes_with_sites(self):
		safety_data(self.request)
		with patch('apps.briefing.views.SAFETY_SERVER_SITE_NAMES', ('china^123456',)):
			safety_data(self.request)
		self.assertEqual(self.counts.call_count, 2)

	def test_post_is_rejected(self):
		response = safety_data(RequestFactory().post('/briefing/safety-data/'))
		self.assertEqual(response.status_code, 405)
		self.counts.assert_not_called()
