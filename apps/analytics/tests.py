from datetime import date, datetime
from decimal import Decimal
from unittest.mock import MagicMock, patch

from django.db import DatabaseError
from django.test import SimpleTestCase
from django.urls import reverse

from .views import fetch_daily_trend, fetch_dashboard_statistics, fetch_quality_records


class QualityRecordQueryTests(SimpleTestCase):
	@patch('apps.analytics.views.connections')
	def test_reads_mesaq_with_inclusive_dates_and_pagination(self, connections):
		cursor = MagicMock()
		connections.__getitem__.return_value.cursor.return_value.__enter__.return_value = cursor
		cursor.fetchone.return_value = (201,)
		columns = ['ID', 'RecordDate', 'BegDate', 'CodeType', 'TmpCode',
				   'ProductNO', 'ProductName', 'equipName', 'OrgName',
				   'MyCode', 'SumNum', 'intVal1', 'Remark', 'cDefine10']
		cursor.description = [(column,) for column in columns]
		row = (1, '2026-10-15', datetime(2026, 10, 15, 23, 59), 'inspection',
			   'batch-1', 'product-1', 'Product', 'Machine', 'Team',
			   'Defect', Decimal('1000.5'), Decimal('12.3'), 'Category', 'Scrap category')
		cursor.fetchall.return_value = [row]

		result = fetch_quality_records(date(2026, 10, 4), date(2026, 10, 15), page=2)

		connections.__getitem__.assert_called_once_with('mesaq')
		count_call, records_call = cursor.execute.call_args_list
		expected_dates = [datetime(2026, 10, 4), datetime(2026, 10, 16)]
		self.assertEqual(count_call.args[1], expected_dates)
		self.assertEqual(records_call.args[1], expected_dates + [100, 100])
		self.assertIn('a.BegDate >= %s AND a.BegDate < %s', records_call.args[0])
		self.assertIn('ORDER BY a.BegDate DESC, a.ID DESC', records_call.args[0])
		self.assertIn('a.cDefine10', records_call.args[0])
		self.assertEqual(result['records'][0], dict(zip(columns, row)))
		self.assertEqual(result['records'][0]['cDefine10'], 'Scrap category')
		self.assertEqual(result['total'], 201)
		self.assertEqual(result['pages'], 3)

	@patch('apps.analytics.views.connections')
	def test_filters_begdate_by_minutes(self, connections):
		cursor = connections.__getitem__.return_value.cursor.return_value.__enter__.return_value
		cursor.fetchone.return_value = (0,)
		cursor.description = [('BegDate',)]
		cursor.fetchall.return_value = []
		start = datetime(2026, 10, 15, 14, 15)
		end = datetime(2026, 10, 15, 14, 30)

		fetch_quality_records(start, end)

		count_call, records_call = cursor.execute.call_args_list
		self.assertEqual(count_call.args[1], [start, datetime(2026, 10, 15, 14, 31)])
		self.assertEqual(records_call.args[1], [start, datetime(2026, 10, 15, 14, 31), 0, 100])
		self.assertIn('a.BegDate >= %s AND a.BegDate < %s', records_call.args[0])

	@patch('apps.analytics.views.connections')
	def test_minute_start_and_date_end_include_end_day(self, connections):
		cursor = connections.__getitem__.return_value.cursor.return_value.__enter__.return_value
		cursor.fetchone.return_value = (0,)
		cursor.description = [('BegDate',)]
		cursor.fetchall.return_value = []
		start = datetime(2026, 10, 15, 14, 15)

		fetch_quality_records(start, date(2026, 10, 15))

		self.assertEqual(cursor.execute.call_args_list[0].args[1], [start, datetime(2026, 10, 16)])

	@patch('apps.analytics.views.connections')
	def test_empty_query_returns_no_records(self, connections):
		cursor = connections.__getitem__.return_value.cursor.return_value.__enter__.return_value
		cursor.fetchone.return_value = (0,)
		cursor.description = [('ID',)]
		cursor.fetchall.return_value = []

		result = fetch_quality_records(date(2026, 10, 15), date(2026, 10, 15))

		self.assertEqual(result['records'], [])
		self.assertEqual(result['total'], 0)
		self.assertEqual(result['pages'], 0)

	@patch('apps.analytics.views.connections')
	def test_invalid_query_is_rejected_before_database_access(self, connections):
		for page, page_size in [(0, 100), (1, 0), (1, 1001)]:
			with self.subTest(page=page, page_size=page_size):
				with self.assertRaises(ValueError):
					fetch_quality_records(date(2026, 10, 15), date(2026, 10, 15), page, page_size)
		with self.assertRaises(ValueError):
			fetch_quality_records(date(2026, 10, 16), date(2026, 10, 15))
		with self.assertRaises(ValueError):
			fetch_quality_records(date(9999, 12, 30), date.max)
		connections.__getitem__.assert_not_called()


class DailyTrendTests(SimpleTestCase):
	@patch('apps.analytics.views.connections')
	def test_aggregates_scrap_quantity_and_fills_missing_days(self, connections):
		cursor = connections.__getitem__.return_value.cursor.return_value.__enter__.return_value
		cursor.fetchall.return_value = [(date(2026, 10, 15), Decimal('123.45'))]
		result = fetch_daily_trend(datetime(2026, 10, 14, 8), datetime(2026, 10, 15, 14, 30))
		connections.__getitem__.assert_called_once_with('mesaq')
		query, params = cursor.execute.call_args.args
		self.assertIn('SUM(a.intVal1)', query)
		self.assertNotIn('OFFSET', query)
		self.assertEqual(params, [datetime(2026, 10, 14, 8), datetime(2026, 10, 15, 14, 31)])
		self.assertEqual(result['days'], [
			{'date': '2026-10-14', 'scrap': 0},
			{'date': '2026-10-15', 'scrap': Decimal('123.45')},
		])

	@patch('apps.analytics.views.connections')
	def test_api_empty_range_and_minute_parameters(self, connections):
		cursor = connections.__getitem__.return_value.cursor.return_value.__enter__.return_value
		cursor.fetchall.return_value = []
		response = self.client.get(reverse('analytics-daily-trend'), {
			'start_date': '2026-10-15T14:30', 'end_date': '2026-10-15T14:30',
		})
		self.assertEqual(response.status_code, 200)
		self.assertEqual(response.json()['days'], [{'date': '2026-10-15', 'scrap': 0}])

	@patch('apps.analytics.views.connections')
	def test_invalid_range_and_post_do_not_query(self, connections):
		for params in [
			{'start_date': '2026-10-15T14:31', 'end_date': '2026-10-15T14:30'},
			{'start_date': 'bad'},
			{'start_date': '2000-01-01', 'end_date': '2026-10-15'},
		]:
			self.assertEqual(self.client.get(reverse('analytics-daily-trend'), params).status_code, 400)
		self.assertEqual(self.client.post(reverse('analytics-daily-trend')).status_code, 405)
		connections.__getitem__.assert_not_called()

	@patch('apps.analytics.views.fetch_daily_trend', side_effect=DatabaseError('private detail'))
	def test_database_failure_is_sanitized(self, fetch_trend):
		with self.assertLogs('apps.analytics.views', level='ERROR'):
			response = self.client.get(reverse('analytics-daily-trend'))
		self.assertEqual(response.status_code, 503)
		self.assertNotIn('private detail', response.content.decode())


class DashboardStatisticsTests(SimpleTestCase):
	@patch('apps.analytics.views.connections')
	def test_all_dimensions_share_time_range_and_totals(self, connections):
		cursor = connections.__getitem__.return_value.cursor.return_value.__enter__.return_value
		cursor.fetchall.return_value = [
			(date(2026, 10, 15), 'Category', 'Defect', 'Team', 'Machine', 'USER', 'Code', 'Scrap class', 'Product', Decimal('12.50')),
			(date(2026, 10, 15), None, '', 'Team', 'Machine', 'USER', 'Code', None, 'Product', Decimal('1.25')),
		]
		result = fetch_dashboard_statistics(datetime(2026, 10, 14, 8), datetime(2026, 10, 15, 14, 30))
		connections.__getitem__.assert_called_once_with('mesaq')
		query, params = cursor.execute.call_args.args
		self.assertEqual(params, [datetime(2026, 10, 14, 8), datetime(2026, 10, 15, 14, 31)])
		self.assertIn('e.Remark AS Category', query)
		self.assertIn('a.cDefine10 AS ScrapCategory', query)
		self.assertIn('SUM(ScrapQuantity)', query)
		self.assertNotIn('COUNT_BIG(*)', query)
		self.assertNotIn('OFFSET', query)
		self.assertEqual(result['total'], Decimal('13.75'))
		self.assertEqual(result['days'][0]['scrap'], 0)
		self.assertEqual(result['days'][1]['scrap'], Decimal('13.75'))
		self.assertEqual(result['teams'], [{'name': 'Team', 'value': Decimal('13.75')}])
		self.assertEqual(result['category_trend'], [{'name': 'Category', 'data': [0, Decimal('12.50')]}, {'name': 'Unspecified', 'data': [0, Decimal('1.25')]}])
		for dimension in ('categories', 'defects', 'teams', 'devices', 'inspectors', 'barcodes', 'scrap_categories', 'products'):
			self.assertEqual(sum(item['value'] for item in result[dimension]), Decimal('13.75'))

	@patch('apps.analytics.views.connections')
	def test_top_ten_and_deterministic_ties(self, connections):
		cursor = connections.__getitem__.return_value.cursor.return_value.__enter__.return_value
		cursor.fetchall.return_value = [
			(date(2026, 10, 15), 'Category', 'Item%02d' % index, 'Team', 'Item%02d' % index, 'Item%02d' % index, 'Code', 'Class', 'Item%02d' % index, Decimal('1'))
			for index in reversed(range(12))
		]
		result = fetch_dashboard_statistics(date(2026, 10, 15), date(2026, 10, 15))
		for dimension in ('defects', 'devices', 'inspectors', 'products'):
			self.assertEqual(len(result[dimension]), 10)
			self.assertEqual(result[dimension][0]['name'], 'Item00')
		self.assertEqual(result['total'], 12)

	@patch('apps.analytics.views.connections')
	def test_empty_api_returns_all_dimensions(self, connections):
		connections.__getitem__.return_value.cursor.return_value.__enter__.return_value.fetchall.return_value = []
		response = self.client.get(reverse('analytics-statistics'), {'start_date': '2026-10-15T08:00', 'end_date': '2026-10-15T09:30'})
		self.assertEqual(response.status_code, 200)
		self.assertEqual(response.json()['total'], 0)
		self.assertEqual(response.json()['days'], [{'date': '2026-10-15', 'scrap': 0}])
		self.assertEqual(response.json()['category_trend'], [])

	@patch('apps.analytics.views.connections')
	def test_invalid_range_and_post_do_not_query(self, connections):
		for params in [{'start_date': 'bad'}, {'start_date': '2026-10-15T10:00', 'end_date': '2026-10-15T09:00'}, {'start_date': '2000-01-01', 'end_date': '2026-10-15'}]:
			self.assertEqual(self.client.get(reverse('analytics-statistics'), params).status_code, 400)
		self.assertEqual(self.client.post(reverse('analytics-statistics')).status_code, 405)
		connections.__getitem__.assert_not_called()

	@patch('apps.analytics.views.fetch_dashboard_statistics', side_effect=DatabaseError('private detail'))
	def test_database_failure_is_sanitized(self, fetch_statistics):
		with self.assertLogs('apps.analytics.views', level='ERROR'):
			response = self.client.get(reverse('analytics-statistics'))
		self.assertEqual(response.status_code, 503)
		self.assertNotIn('private detail', response.content.decode())


class QualityRecordApiTests(SimpleTestCase):
	@patch('apps.analytics.views.fetch_quality_records')
	def test_get_returns_records_and_serializes_database_values(self, fetch_records):
		fetch_records.return_value = {'records': [{
			'BegDate': datetime(2026, 10, 15, 12, 30),
			'SumNum': Decimal('1000.50'),
			'intVal1': Decimal('12.30'),
			'Remark': None,
			'cDefine10': 'Scrap category',
		}], 'total': 1}

		response = self.client.get(reverse('analytics-data'), {
			'start_date': '2026-10-04', 'end_date': '2026-10-15',
			'page': '2', 'page_size': '50',
		})

		self.assertEqual(response.status_code, 200)
		fetch_records.assert_called_once_with(date(2026, 10, 4), date(2026, 10, 15), 2, 50)
		record = response.json()['records'][0]
		self.assertEqual(record['BegDate'], '2026-10-15T12:30:00')
		self.assertEqual(record['SumNum'], '1000.50')
		self.assertEqual(record['intVal1'], '12.30')
		self.assertIsNone(record['Remark'])
		self.assertEqual(record['cDefine10'], 'Scrap category')

	@patch('apps.analytics.views.timezone.localdate', return_value=date(2026, 10, 15))
	@patch('apps.analytics.views.fetch_quality_records', return_value={'records': [], 'total': 0})
	def test_accepts_minute_selection(self, fetch_records, localdate):
		response = self.client.get(reverse('analytics-data'), {
			'start_date': '2026-10-15T14:15', 'end_date': '2026-10-15T14:30',
		})

		self.assertEqual(response.status_code, 200)
		fetch_records.assert_called_once_with(datetime(2026, 10, 15, 14, 15), datetime(2026, 10, 15, 14, 30), 1, 100)

	@patch('apps.analytics.views.timezone.localdate', return_value=date(2026, 10, 15))
	@patch('apps.analytics.views.fetch_quality_records', return_value={'records': [], 'total': 0})
	def test_defaults_to_last_thirty_days(self, fetch_records, localdate):
		response = self.client.get(reverse('analytics-data'))

		self.assertEqual(response.status_code, 200)
		fetch_records.assert_called_once_with(date(2026, 9, 16), date(2026, 10, 15), 1, 100)

	@patch('apps.analytics.views.connections')
	def test_invalid_parameters_do_not_access_database(self, connections):
		invalid_queries = [
			{'start_date': 'not-a-date'},
			{'end_date': '20261015'},
			{'start_date': '2026-10-15T14:31', 'end_date': '2026-10-15T14:30'},
			{'start_date': '2026-10-15T14:15:00'},
			{'start_date': '2026-10-15T14:15+08:00'},
			{'start_date': '2026-10-16', 'end_date': '2026-10-15'},
			{'page': '0'},
			{'page': 'not-a-number'},
			{'page_size': '1001'},
			{'end_date': '9999-12-31'},
		]
		for query in invalid_queries:
			with self.subTest(query=query):
				response = self.client.get(reverse('analytics-data'), query)
				self.assertEqual(response.status_code, 400)
		connections.__getitem__.assert_not_called()

	@patch('apps.analytics.views.fetch_quality_records')
	def test_post_is_not_allowed(self, fetch_records):
		response = self.client.post(reverse('analytics-data'))

		self.assertEqual(response.status_code, 405)
		fetch_records.assert_not_called()

	@patch('apps.analytics.views.fetch_quality_records', side_effect=DatabaseError('private database detail'))
	def test_database_errors_are_not_exposed_to_client(self, fetch_records):
		with self.assertLogs('apps.analytics.views', level='ERROR'):
			response = self.client.get(reverse('analytics-data'))

		self.assertEqual(response.status_code, 503)
		self.assertNotIn('private database detail', response.content.decode())
		self.assertIn('error', response.json())
