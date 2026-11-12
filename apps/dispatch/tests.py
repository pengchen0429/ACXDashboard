import sqlite3
import json
from io import BytesIO
from datetime import datetime
from unittest.mock import patch
from zoneinfo import ZoneInfo

from django.db import DatabaseError
from django.test import SimpleTestCase, override_settings
from django.urls import resolve, reverse
from openpyxl import load_workbook

from .services import fetch_dispatch_records, get_dispatch_details, get_dispatch_filter_options, get_dispatch_summary


@override_settings(L2L_SITE_ACX='907371', L2L_SITE_CNX='928261',
	SNOWFLAKE_DISPATCH_TIME_ZONE='Asia/Shanghai')
class DispatchSnowflakeTests(SimpleTestCase):
	def setUp(self):
		self.zone = ZoneInfo('Asia/Shanghai')
		self.start = datetime(2026, 11, 1, tzinfo=self.zone)
		self.end = datetime(2026, 12, 1, tzinfo=self.zone)
		self.database = sqlite3.connect(':memory:')
		self.addCleanup(self.database.close)
		self.database.row_factory = sqlite3.Row
		self.database.create_function('TRY_TO_TIMESTAMP_NTZ', 1, self.parse_timestamp)
		self.database.create_function('CONVERT_TIMEZONE', 3, self.convert_timezone)
		self.database.create_function('TO_CHAR', 2, lambda value, pattern: value[:7])
		self.database.execute('CREATE TABLE area_fixture (SERVER_SITE_NAME, code, active, createdby)')
		self.database.executemany('INSERT INTO area_fixture VALUES (?, ?, ?, ?)', [
			('china^907371', code, 'true', 'operator') for code in ('A', 'B', 'C', 'Invalid', 'Outside')
		] + [('china^928261', 'CNX', 'true', 'operator')])
		self.database.execute('''CREATE TABLE dispatches (
			SERVER_SITE_NAME TEXT, reported TEXT, areacode TEXT, createdby TEXT,
			dispatchtypecode TEXT, completed TEXT, closed TEXT, dispatched TEXT, deleted TEXT
		)''')
		self.database.executemany('INSERT INTO dispatches VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)', [
			('china^907371', '2026-11-01T00:00:00', ' A ', ' Alice ', 'Safety', None, '2026-11-02T10:00:00', None, ''),
			('china^907371', '2026-11-30T23:59:59', 'B', 'Bob', 'Quality', None, '', '2026-11-30T10:00:00', None),
			('china^907371', '2026-11-02T00:00:00', 'A', 'Bob', 'Safety', '', '  ', ' ', '  '),
			('china^907371', '2026-11-03T00:00:00', 'A', 'Alice', 'Safety', None, '2026-11-04T10:00:00', None, 'F'),
			('china^907371', '2026-11-04T00:00:00', 'B', 'Carol', 'Quality', '2026-11-05T10:00:00', None, None, ''),
			('china^907371', '2026-10-31T23:59:59', 'Outside', 'Outside', 'Outside', None, None, None, ''),
			('china^907371', '2026-12-01T00:00:00', 'C', 'Alice', 'Safety', None, None, None, ''),
			('china^907371', '2026-11-01T12:00:00', 'Deleted', 'Deleted', 'Deleted', None, None, None, ' T '),
			('china^907371', 'invalid', 'Invalid', 'Invalid', 'Invalid', None, None, None, ''),
			('china^928261', '2026-11-01T12:00:00', 'CNX', 'CNX', 'Safety', None, None, None, ''),
		])
		self.fetch = patch('apps.dispatch.services.fetch_all', side_effect=self.execute_query).start()
		patch('common.snowflake.fetch_all', side_effect=self.execute_query).start()
		self.addCleanup(patch.stopall)

	@staticmethod
	def parse_timestamp(value):
		try:
			return datetime.fromisoformat(value).isoformat(sep=' ')
		except (ValueError, TypeError):
			return None

	@staticmethod
	def convert_timezone(source, target, value):
		if value is None:
			return None
		return datetime.fromisoformat(value).replace(tzinfo=ZoneInfo(source)).astimezone(
			ZoneInfo(target)).replace(tzinfo=None).isoformat(sep=' ')

	def execute_query(self, query, params):
		query = query.replace('PRD_MANUFACTURING_DB.G_L2L_CONSUMPTION.VW_DISPATCHES', 'main.dispatches')
		query = query.replace('PRD_MANUFACTURING_DB.G_L2L_CONSUMPTION.VW_AREAS', 'area_fixture')
		params = [value.isoformat(sep=' ') if isinstance(value, datetime) else value for value in params]
		return [dict(row) for row in self.database.execute(query.replace('%s', '?'), params)]

	def test_reported_local_boundaries_status_and_weighted_totals(self):
		data = get_dispatch_summary(self.start, self.end, site='ACX')
		self.assertEqual(data['stats'], {'total': 5, 'open': 1, 'inwork': 2, 'closed': 2, 'rate': 40.0})
		self.assertEqual(data['trend'], [{'month': '2026-11', 'total': 5, 'closed': 2}])
		self.assertEqual(data['options']['technicians'], ['Alice', 'Bob', 'Carol'])
		self.assertEqual(data['options']['areas'], ['A', 'B'])
		self.assertEqual(sum(row['value'] for row in data['types']), 5)
		self.assertEqual(sum(row['OPEN'] + row['IN WORK'] + row['CLOSED'] for row in data['areas']), 5)

	def test_filter_options_are_independent_of_summary_and_date_range(self):
		options = get_dispatch_filter_options()
		self.assertEqual(options['ACX']['areas'], ['A', 'B', 'C', 'Invalid', 'Outside'])
		self.assertEqual(options['ACX']['technicians'], ['Alice', 'Bob', 'Carol', 'Invalid', 'Outside'])
		self.assertEqual(options['ACX']['dispatchtypes'], ['Invalid', 'Outside', 'Quality', 'Safety'])
		self.assertEqual(options['CNX'], {'areas': ['CNX'], 'technicians': ['CNX'], 'dispatchtypes': ['Safety']})
		self.fetch.assert_called_once()
		self.assertNotIn('COUNT(', self.fetch.call_args.args[0])

	def test_submitter_multiselect_and_combined_filters(self):
		data = get_dispatch_summary(self.start, self.end, site='ACX', areas=['A'],
			technicians=['Alice', 'Bob'], dispatchtypes=['Safety'])
		self.assertEqual(data['stats']['total'], 3)
		self.assertEqual(data['areas'], [{'name': 'A', 'OPEN': 1, 'IN WORK': 0, 'CLOSED': 2}])
		self.assertEqual(data['options']['technicians'], ['Alice', 'Bob', 'Carol'])

	def test_area_rules_apply_to_options_summary_and_detail_export(self):
		self.database.executemany('INSERT INTO area_fixture VALUES (?, ?, ?, ?)', [
			('china^907371', 'Inactive', 'false', 'operator'),
			('china^907371', 'System', 'true', ' SuperUser '),
			('china^928261', 'Cross-site', 'true', 'operator'),
			('china^907371', 'Unused', 'true', 'operator'),
			('china^907371', 'A', 'true', 'operator'),
		])
		self.database.executemany('INSERT INTO dispatches (SERVER_SITE_NAME, reported, areacode, createdby, dispatchtypecode) VALUES (?, ?, ?, ?, ?)', [
			('china^907371', '2026-11-02T00:00:00', code, 'Excluded Person', 'Excluded Type')
			for code in ('Inactive', 'System', 'Cross-site', 'Missing', '')
		])
		options = get_dispatch_filter_options()['ACX']
		self.assertIn('Unused', options['areas'])
		self.assertNotIn('Excluded Person', options['technicians'])
		self.assertNotIn('Excluded Type', options['dispatchtypes'])
		self.assertTrue(all(code not in options['areas'] for code in ('Inactive', 'System', 'Cross-site', 'Missing')))
		self.assertEqual(get_dispatch_summary(self.start, self.end, site='ACX')['stats']['total'], 5)
		self.assertEqual(len(get_dispatch_details(self.start, self.end, site='ACX')), 5)

	def test_completed_without_closed_is_not_closed(self):
		data = get_dispatch_summary(self.start, self.end, site='ACX', technicians=['Carol'])
		self.assertEqual(data['stats'], {'total': 1, 'open': 0, 'inwork': 1, 'closed': 0, 'rate': 0.0})

	def test_sites_are_isolated_and_not_cached(self):
		for site, total in [('ACX', 5), ('ACX', 5), ('CNX', 1)]:
			self.assertEqual(get_dispatch_summary(self.start, self.end, site=site)['stats']['total'], total)
		self.assertEqual(self.fetch.call_count, 3)
		self.assertEqual(self.fetch.call_args.args[1][1], 'china^928261')

	def test_multiple_sites_are_merged_in_one_query_without_duplicate_counts(self):
		data = get_dispatch_summary(self.start, self.end, site=['ACX', 'CNX', 'ACX'])
		self.assertEqual(data['stats'], {'total': 6, 'open': 2, 'inwork': 2, 'closed': 2, 'rate': 33.3})
		self.assertEqual(data['trend'], [{'month': '2026-11', 'total': 6, 'closed': 2}])
		self.assertEqual(data['options']['areas'], ['A', 'B', 'CNX'])
		self.assertIn('CNX', data['options']['technicians'])
		self.fetch.assert_called_once()
		self.assertEqual(self.fetch.call_args.args[1][1:3], ['china^907371', 'china^928261'])

	def test_invalid_or_empty_sites_do_not_query(self):
		for sites in ([], [''], ['ACX', 'other']):
			with self.subTest(sites=sites), self.assertRaises(ValueError):
				fetch_dispatch_records(self.start, self.end, site=sites)
		self.fetch.assert_not_called()

	def test_empty_result_and_empty_months(self):
		data = get_dispatch_summary(self.start, datetime(2027, 2, 1, tzinfo=self.zone),
			site='ACX', technicians=['No such submitter'])
		self.assertEqual(data['stats']['total'], 0)
		self.assertEqual(data['stats']['rate'], 0)
		self.assertEqual(data['trend'], [
			{'month': '2026-11', 'total': 0, 'closed': 0},
			{'month': '2026-12', 'total': 0, 'closed': 0},
			{'month': '2027-01', 'total': 0, 'closed': 0},
		])

	@override_settings(SNOWFLAKE_DISPATCH_TIME_ZONE='UTC')
	def test_source_timezone_and_month_are_converted_before_filtering(self):
		self.database.execute('DELETE FROM dispatches')
		self.database.executemany("INSERT INTO dispatches (SERVER_SITE_NAME, reported, areacode) VALUES (?, ?, 'A')", [
			('china^907371', '2026-10-31T15:59:59'),
			('china^907371', '2026-10-31T16:00:00'),
			('china^907371', '2026-11-30T16:00:00'),
		])
		data = get_dispatch_summary(self.start, self.end, site='ACX')
		self.assertEqual(data['stats']['total'], 1)
		self.assertEqual(data['trend'][0]['total'], 1)

	def test_query_uses_parameter_binding(self):
		fetch_dispatch_records(self.start, self.end, site='ACX')
		query, params = self.fetch.call_args.args
		self.assertIn('"SERVER_SITE_NAME" IN (%s)', query)
		self.assertNotIn('china^907371', query)
		self.assertEqual(params, ['Asia/Shanghai', 'china^907371',
			datetime(2026, 11, 1), datetime(2026, 12, 1)])

	def test_database_failure_propagates(self):
		self.fetch.side_effect = DatabaseError('unavailable')
		with self.assertRaises(DatabaseError):
			get_dispatch_summary(self.start, self.end, site='ACX')

	def test_details_preserve_each_record_and_match_summary_filters(self):
		rows = get_dispatch_details(self.start, self.end, site=['ACX', 'CNX'])
		self.assertEqual(len(rows), 6)
		self.assertEqual({row['factory'] for row in rows}, {'ACX', 'CNX'})
		self.assertEqual(rows[0]['reported'], '2026-11-01 00:00:00')
		filtered = get_dispatch_details(self.start, self.end, site=['ACX', 'CNX'],
			areas=['A'], technicians=['Alice', 'Bob'], dispatchtypes=['Safety'])
		self.assertEqual(len(filtered), 3)
		self.assertTrue(all(row['area'] == 'A' and row['type'] == 'Safety' for row in filtered))
		self.database.execute('INSERT INTO dispatches SELECT * FROM dispatches WHERE createdby = ?', (' Alice ',))
		self.assertEqual(len(get_dispatch_details(self.start, self.end, site='ACX')), 6)


@override_settings(AUTHENTICATION_BACKENDS=['django.contrib.auth.backends.ModelBackend'])
class DispatchDataTests(SimpleTestCase):
	@patch('apps.dispatch.views.get_dispatch_details')
	def test_export_creates_four_column_detail_excel(self, mock_details):
		mock_details.return_value = [
			{'factory': 'ACX', 'reported': datetime(2026, 11, 1, 10, 30), 'area': '区域A', 'type': '=1+1'},
			{'factory': 'CNX', 'reported': datetime(2026, 11, 2, 11, 30), 'area': '区域B', 'type': 'Safety'},
		]
		payload = {'query': 'site=ACX&site=CNX&start=2026-11-01&end=2026-11-12&technician=Alice'}
		response = self.client.post(reverse('dispatch-export'), json.dumps(payload), content_type='application/json')
		self.assertEqual(response.status_code, 200)
		self.assertIn('spreadsheetml.sheet', response['Content-Type'])
		workbook = load_workbook(BytesIO(response.content))
		self.assertEqual(workbook.sheetnames, ['Dispatch明细'])
		worksheet = workbook.active
		self.assertEqual(list(worksheet.values), [
			('工厂', '时间', '区域', 'Dispatch类型'),
			('ACX', datetime(2026, 11, 1, 10, 30), '区域A', '=1+1'),
			('CNX', datetime(2026, 11, 2, 11, 30), '区域B', 'Safety'),
		])
		self.assertEqual(worksheet['D2'].data_type, 's')
		self.assertEqual(mock_details.call_args.kwargs['site'], ['ACX', 'CNX'])
		self.assertEqual(mock_details.call_args.kwargs['technicians'], ['Alice'])

	def test_export_rejects_missing_snapshot_and_get(self):
		self.assertEqual(self.client.get(reverse('dispatch-export')).status_code, 405)
		for payload in ('{}', 'null', 'invalid', '{"query": null}',
			'{"query": "site=other&start=2026-11-01&end=2026-11-12"}',
			'{"query": "site=ACX&start=2026-11-12&end=2026-11-01"}'):
			self.assertEqual(self.client.post(reverse('dispatch-export'), payload,
				content_type='application/json').status_code, 400)

	@patch('apps.dispatch.views.get_dispatch_details', return_value=[])
	def test_empty_detail_export_has_only_four_column_header(self, mock_details):
		response = self.client.post(reverse('dispatch-export'), json.dumps({
			'query': 'site=ACX&start=2026-11-01&end=2026-11-12'}), content_type='application/json')
		self.assertEqual(response.status_code, 200)
		workbook = load_workbook(BytesIO(response.content))
		self.assertEqual(list(workbook.active.values), [('工厂', '时间', '区域', 'Dispatch类型')])

	@patch('apps.dispatch.views.logger.exception')
	@patch('apps.dispatch.views.get_dispatch_details', side_effect=DatabaseError('secret'))
	def test_detail_export_database_failure_is_sanitized(self, mock_details, mock_log):
		response = self.client.post(reverse('dispatch-export'), json.dumps({
			'query': 'site=ACX&start=2026-11-01&end=2026-11-12'}), content_type='application/json')
		self.assertEqual(response.status_code, 502)
		self.assertNotIn('secret', response.content.decode())
		mock_log.assert_called_once()

	@patch('apps.dispatch.views.get_dispatch_summary')
	@patch('apps.dispatch.views.get_dispatch_filter_options')
	def test_options_endpoint_does_not_run_summary(self, mock_options, mock_summary):
		mock_options.return_value = {'ACX': {'areas': ['A'], 'technicians': ['Alice'], 'dispatchtypes': ['Safety']}}
		response = self.client.get(reverse('dispatch-options'))
		self.assertEqual(response.status_code, 200)
		self.assertEqual(response.json(), {'success': True, 'options': mock_options.return_value})
		self.assertEqual(response['Cache-Control'], 'no-store')
		mock_summary.assert_not_called()
		self.assertEqual(self.client.post(reverse('dispatch-options')).status_code, 405)

	@patch('apps.dispatch.views.logger.exception')
	@patch('apps.dispatch.views.get_dispatch_filter_options', side_effect=DatabaseError('secret'))
	def test_options_failure_is_explicit_and_sanitized(self, mock_options, mock_log):
		response = self.client.get(reverse('dispatch-options'))
		self.assertEqual(response.status_code, 502)
		self.assertFalse(response.json()['success'])
		self.assertNotIn('secret', response.content.decode())
		mock_log.assert_called_once()

	@patch('apps.dispatch.views.get_dispatch_summary')
	def test_endpoint_validates_inputs_and_passes_filters(self, mock_summary):
		mock_summary.return_value = {'stats': {'total': 0}}
		response = self.client.get(reverse('dispatch-data'), {
			'start': '2026-11-01', 'end': '2026-11-30', 'site': 'CNX',
			'area': ['A', 'B'], 'technician': ['Alice', 'Bob'], 'dispatchtype': 'Safety',
		})
		self.assertEqual(response.status_code, 200)
		self.assertEqual(response['Cache-Control'], 'no-store')
		self.assertEqual(mock_summary.call_args.kwargs, {
			'site': ['CNX'], 'areas': ['A', 'B'], 'technicians': ['Alice', 'Bob'], 'dispatchtypes': ['Safety']})
		self.assertEqual(mock_summary.call_args.args[1].isoformat(), '2026-12-01T00:00:00+08:00')
		mock_summary.reset_mock()
		for params in ({}, {'start': 'bad', 'end': '2026-11-30'},
			{'start': '2026-12-01', 'end': '2026-11-01'},
			{'start': '2026-11-01', 'end': '2026-11-30', 'site': 'other'},
			{'start': '2026-11-01', 'end': '2026-11-30', 'site': ''},
			{'start': '2026-11-01', 'end': '2026-11-30', 'site': ['ACX', 'other']}):
			self.assertEqual(self.client.get(reverse('dispatch-data'), params).status_code, 400)
		mock_summary.assert_not_called()

	@patch('apps.dispatch.views.get_dispatch_summary', return_value={'stats': {'total': 6}})
	def test_endpoint_passes_multiple_sites_and_preserves_default(self, mock_summary):
		params = {'start': '2026-11-01', 'end': '2026-11-30', 'site': ['ACX', 'CNX', 'ACX']}
		self.assertEqual(self.client.get(reverse('dispatch-data'), params).status_code, 200)
		self.assertEqual(mock_summary.call_args.kwargs['site'], ['ACX', 'CNX'])
		params.pop('site')
		self.assertEqual(self.client.get(reverse('dispatch-data'), params).status_code, 200)
		self.assertEqual(mock_summary.call_args.kwargs['site'], ['ACX'])

	@patch('apps.dispatch.views.logger.exception')
	@patch('apps.dispatch.views.get_dispatch_summary', side_effect=DatabaseError('secret'))
	def test_snowflake_failure_is_explicit_and_sanitized(self, mock_summary, mock_log):
		response = self.client.get(reverse('dispatch-data'), {'start': '2026-11-01', 'end': '2026-11-30'})
		self.assertEqual(response.status_code, 502)
		self.assertContains(response, 'Snowflake', status_code=502)
		self.assertNotIn('secret', response.content.decode())
		self.assertEqual(response['Cache-Control'], 'no-store')
		mock_log.assert_called_once()

	def test_endpoint_is_read_only(self):
		self.assertEqual(self.client.post(reverse('dispatch-data')).status_code, 405)


@override_settings(AUTHENTICATION_BACKENDS=['django.contrib.auth.backends.ModelBackend'])
class DispatchPageTests(SimpleTestCase):
	def test_dispatch_page_and_active_navigation(self):
		url = reverse('dispatch')
		self.assertEqual(url, '/dispatch/')
		self.assertEqual(resolve(url).view_name, 'dispatch')
		response = self.client.get(url)
		self.assertEqual(response.status_code, 200)
		self.assertTemplateUsed(response, 'dispatch/dispatch.html')
		self.assertTemplateUsed(response, 'base.html')
		self.assertContains(response, 'Dispatch查询')
		self.assertContains(response, '<a class="nav-item active" href="/dispatch/" data-page="dispatch" aria-current="page">')
		self.assertContains(response, '<details class="nav-group" open>', count=2)
		self.assertContains(response, '/static/js/dispatch.js?v=excel-details-1')
		self.assertContains(response, '/static/css/dispatch.css?v=excel-export-1')
		self.assertContains(response, 'class="btn btn-primary multi-select-confirm"', count=4)
		self.assertContains(response, 'class="btn btn-secondary multi-select-reset"', count=4)
		self.assertContains(response, 'class="multi-select" data-name="Site"')
		self.assertContains(response, 'data-url="/dispatch/data/"')
		self.assertContains(response, 'data-options-url="/dispatch/options/"')
		self.assertContains(response, 'data-export-url="/dispatch/export/"')
		self.assertContains(response, 'id="btnExport"')

	def test_navigation_link_on_dashboard_is_not_active(self):
		response = self.client.get(reverse('dashboard'))
		self.assertEqual(response.status_code, 200)
		self.assertContains(response, '<a class="nav-item" href="/dispatch/" data-page="dispatch">')