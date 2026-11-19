import sqlite3
from datetime import datetime
from unittest.mock import Mock, patch

from django.core.exceptions import PermissionDenied
from django.db import DatabaseError
from django.test import RequestFactory, SimpleTestCase

from . import services, views


class DpmuTests(SimpleTestCase):
	def test_weighted_ratio_and_missing_production(self):
		result = services.summarize(
			[('2026-10', 'WEAV', 'W1', 'A', 100), ('2026-10', 'WEAV', 'W2', 'A', 300)],
			[('2026-10', 'WEAV', 'W1', 'A', 'C', 'D', 20),
			 ('2026-10', 'WEAV', 'W2', 'A', 'C', 'D', 20),
			 ('2026-10', 'WEAV', 'W3', 'B', 'C', 'E', 10)], ['2026-09', '2026-10'])
		self.assertEqual(result['total']['dpmu'], 125000)
		self.assertEqual(result['months'][0]['dpmu'], None)
		self.assertEqual(result['defects'][0]['dpmu'], 100000)
		self.assertIsNone(next(row for row in result['lines'] if row['name'] == 'W3')['dpmu'])
		self.assertEqual(result['total']['production'], 400)
		self.assertEqual(result['total']['scrap'], 50)
		for dimension in ('months', 'areas', 'lines', 'products', 'categories', 'defects'):
			for row in result[dimension]:
				with self.subTest(dimension=dimension, name=row['name']):
					if row['production'] > 0:
						self.assertAlmostEqual(row['dpmu'], row['scrap'] / row['production'] * 1000000)
					else:
						self.assertIsNone(row['dpmu'])

	def test_sql_filters_and_shift_bounds(self):
		cursor = Mock()
		cursor.fetchall.return_value = []
		filters = {'tab': 'weaving', 'category': ['C', 'C2'], 'defect': ["D'; --", 'D2']}
		start, end = datetime(2026, 10, 28, 8, 30), datetime(2026, 10, 29, 8, 30)
		services._query_rows(cursor, 'production', start, end, filters)
		sql, params = cursor.execute.call_args.args
		self.assertNotIn(filters['defect'][0], sql)
		self.assertEqual(params[:2], [datetime(2026, 10, 28), datetime(2026, 10, 29)])
		self.assertEqual(params[2:], ['WEAV'])
		services._query_rows(cursor, 'scrap', start, end, filters)
		sql, params = cursor.execute.call_args.args
		self.assertIn('a.cDefine1 = b.equipNo', sql)
		self.assertIn('a.DuctID = p.ID', sql)
		self.assertIn('a.DefCode = g.BarCode', sql)
		self.assertEqual(params[4:6], [start, datetime(2026, 10, 29, 8, 31)])
		self.assertEqual(params[6:10], list(services.CATEGORIES))
		self.assertEqual(params[10:14], ['C', 'C2', "D'; --", 'D2'])
		self.assertEqual(sql.count(' IN ('), 3)
		self.assertEqual(sql.count('%s'), len(params))

	def test_actual_sql_preserves_quantities(self):
		database = sqlite3.connect(':memory:')
		database.create_function('LTRIM', 1, lambda value: value.lstrip() if value else value)
		database.executescript('''
			CREATE TABLE tabWorkDayRpt (RecDate, EquipNo, DuctID, DayQty);
			CREATE TABLE tabEquipment (equipNo, equipName, xflag);
			CREATE TABLE tabEquipType (id, LineName, EquipType);
			CREATE TABLE tabProduct (ID, ProductName);
			INSERT INTO tabEquipment VALUES ('W1', 'Line1', 1);
			INSERT INTO tabEquipType VALUES (1, 'WEAV', 'Weaving');
			INSERT INTO tabProduct VALUES (1, 'A');
			INSERT INTO tabWorkDayRpt VALUES ('2026-10-28', 'W1', 1, 100), ('2026-10-28', 'W1', 1, 300);
		''')
		cursor = Mock()
		services._query_rows(cursor, 'production', datetime(2026, 10, 28, 8, 30),
							 datetime(2026, 10, 29, 8, 30), {'tab': 'overview'})
		sql, params = cursor.execute.call_args.args
		sql = sql.replace("CONVERT(char(7), a.RecDate, 120)", 'substr(a.RecDate, 1, 7)').replace("N'", "'")
		rows = database.execute(sql.replace('%s', '?'),
			[value.strftime('%Y-%m-%d') if isinstance(value, datetime) else value for value in params]).fetchall()
		database.close()
		self.assertEqual(rows, [('2026-10', 'WEAV', 'Line1', 'A', 400)])

	def request(self, params=None):
		request = RequestFactory().get('/dpmu/data/', params or {})
		request.user = Mock(is_authenticated=True)
		request.user.has_perm.return_value = True
		return request

	@patch('apps.dpmu.views.get_summary')
	def test_api_validates_before_database(self, summary):
		for params in ({}, {'start_time': 'invalid'},
					   {'start_time': '2026-10-29T08:30', 'end_time': '2026-10-28T08:30'},
					   {'start_time': '2026-10-28T08:30', 'end_time': '2026-10-29T08:30', 'tab': 'bad'}):
			self.assertEqual(views.data(self.request(params)).status_code, 400)
		summary.assert_not_called()

	@patch('apps.dpmu.views.get_summary')
	def test_api_success_and_database_failure(self, summary):
		params = {'start_time': '2026-10-28T08:30', 'end_time': '2026-10-29T08:30'}
		summary.return_value = {'total': {'dpmu': 0.125}}
		self.assertEqual(views.data(self.request(params)).status_code, 200)
		summary.side_effect = DatabaseError('offline')
		with self.assertLogs('apps.dpmu.views', level='ERROR'):
			self.assertEqual(views.data(self.request(params)).status_code, 503)

	def test_permission_denied(self):
		request = self.request()
		request.user.has_perm.return_value = False
		for view in (views.data, views.options):
			with self.assertRaises(PermissionDenied):
				view(request)

	@patch('apps.dpmu.views.get_options', return_value={'defects': []})
	def test_options(self, options):
		response = views.options(self.request({'start_time': '2026-10-28T08:30', 'end_time': '2026-10-29T08:30'}))
		self.assertEqual(response.status_code, 200)
		self.assertIn('no-store', response['Cache-Control'])

	@patch('apps.dpmu.services.connections')
	def test_exact_month_boundary_uses_last_production_day(self, connections):
		cursor = connections['mesaq'].cursor.return_value.__enter__.return_value
		cursor.fetchall.side_effect = [[], []]
		result = services.get_summary(datetime(2026, 10, 1, 8, 30),
									  datetime(2026, 11, 1, 8, 30), {'tab': 'overview'})
		self.assertEqual([row['name'] for row in result['months']], ['2026-10'])
		sql, params = cursor.execute.call_args.args
		self.assertEqual(str(params[2]), '2026-10-31')
		self.assertEqual(str(params[3]), '2026-10-31')
		self.assertEqual(sql.count('%s'), len(params))

	@patch('apps.dpmu.services.connections')
	def test_partial_shift_includes_next_production_day(self, connections):
		cursor = connections['mesaq'].cursor.return_value.__enter__.return_value
		cursor.fetchall.side_effect = [[], []]
		result = services.get_summary(datetime(2026, 10, 31, 8, 30),
									  datetime(2026, 11, 1, 8, 31), {'tab': 'overview'})
		self.assertEqual([row['name'] for row in result['months']], ['2026-10', '2026-11'])

	@patch('apps.dpmu.views.get_options', side_effect=DatabaseError('offline'))
	def test_options_failure(self, options):
		with self.assertLogs('apps.dpmu.views', level='ERROR'):
			self.assertEqual(views.options(self.request({
				'start_time': '2026-10-28T08:30', 'end_time': '2026-10-29T08:30'})).status_code, 503)

	def test_anonymous_without_permission_redirects(self):
		request = self.request()
		request.user.is_authenticated = False
		request.user.has_perm.return_value = False
		for view in (views.data, views.options):
			response = view(request)
			self.assertEqual(response.status_code, 302)
			self.assertTrue(response.url.startswith('/login/?next='))

	@patch('apps.dpmu.views.get_summary', return_value={'total': {'dpmu': 0}})
	def test_api_multiple_values_are_deduplicated_without_splitting_names(self, summary):
		request = self.request({'start_time': '2026-10-28T08:30', 'end_time': '2026-10-29T08:30',
								'category': ['织造不合格', '过程不合格', '织造不合格', ' '], 'defect': ['D,1', 'D2'],
								'area': 'ignored', 'product': 'ignored'})
		self.assertEqual(views.data(request).status_code, 200)
		self.assertEqual(summary.call_args.args[2],
						 {'tab': 'overview', 'category': ['织造不合格', '过程不合格'], 'defect': ['D,1', 'D2']})

	@patch('apps.dpmu.services.connections')
	def test_options_only_queries_defects(self, connections):
		cursor = connections['mesaq'].cursor.return_value.__enter__.return_value
		cursor.fetchall.return_value = [('织造不合格', 'D'), ('染色报废', 'D2')]
		result = services.get_options(datetime(2026, 10, 28, 8, 30), datetime(2026, 10, 29, 8, 30),
			{'tab': 'overview', 'category': ['织造不合格']})
		self.assertEqual(result, {'categories': ['织造不合格', '染色报废'],
			'defects': [{'category': '织造不合格', 'name': 'D'}]})
		cursor.execute.assert_called_once()
		sql, params = cursor.execute.call_args.args
		self.assertIn('FROM tabDefaultRec', sql)
		self.assertEqual(params[:2], [datetime(2026, 10, 28, 8, 30), datetime(2026, 10, 29, 8, 31)])
		self.assertEqual(params[2:], list(services.CATEGORIES))

	def test_scrap_is_attributed_by_category_and_process_is_split_exactly(self):
		rows = [('2026-10', 'DYE', 'D1', 'A', '织造不合格', 'D', 10),
			('2026-10', 'WEAV', 'W1', 'A', '染色不合格', 'D', 20),
			('2026-10', 'WEAV', 'W1', 'A', '染色报废', 'D', 30),
			('2026-10', 'FP', 'F1', 'A', '过程不合格', 'D', 5),
			('2026-10', 'WEAV', 'W1', 'A', '其他', 'D', 1000)]
		weaving = services.allocate_scrap(rows, 'weaving')
		dyeing = services.allocate_scrap(rows, 'dyeing')
		overview = services.allocate_scrap(rows)
		self.assertEqual(sum(row[-1] for row in weaving), 12.5)
		self.assertEqual(sum(row[-1] for row in dyeing), 52.5)
		self.assertEqual(sum(row[-1] for row in overview), 65)
		self.assertTrue(all(row[1] == 'WEAV' for row in weaving))
		self.assertTrue(all(row[1] == 'DYE' for row in dyeing))
		self.assertEqual(weaving[-1][2], '未分配产线')

	def test_process_split_does_not_duplicate_overview_totals(self):
		rows = [('2026-10', 'WEAV', 'W1', 'A', '过程不合格', 'D', 5)]
		result = services.summarize(
			[('2026-10', 'WEAV', 'W1', 'A', 100), ('2026-10', 'DYE', 'D1', 'A', 200)],
			services.allocate_scrap(rows), ['2026-10'])
		self.assertEqual(result['total']['scrap'], 5)
		self.assertAlmostEqual(result['total']['dpmu'], 5 / 300 * 1000000)
		self.assertEqual({row['name']: row['scrap'] for row in result['areas']}, {'织造': 2.5, '染色': 2.5})
		self.assertEqual(result['categories'][0]['scrap'], 5)

	@patch('apps.dpmu.services.connections')
	def test_options_scope_uses_category_allocation_not_equipment(self, connections):
		cursor = connections['mesaq'].cursor.return_value.__enter__.return_value
		cursor.fetchall.return_value = [('织造不合格', 'D'), ('过程不合格', 'P')]
		result = services.get_options(datetime(2026, 10, 28, 8, 30), datetime(2026, 10, 29, 8, 30),
			{'tab': 'weaving', 'category': []})
		sql, params = cursor.execute.call_args.args
		self.assertEqual(params[2:], ['织造不合格', '过程不合格'])
		self.assertNotIn('EquipType', sql)
		self.assertEqual(result['categories'], ['织造不合格', '过程不合格'])

	@patch('apps.dpmu.views.get_options')
	@patch('apps.dpmu.views.get_summary')
	def test_unknown_categories_and_missing_option_times_are_rejected(self, summary, options):
		request = self.request({'start_time': '2026-10-28T08:30', 'end_time': '2026-10-29T08:30',
			'category': ['其他分类']})
		self.assertEqual(views.data(request).status_code, 400)
		self.assertEqual(views.options(request).status_code, 400)
		self.assertEqual(views.options(self.request()).status_code, 400)
		summary.assert_not_called()
		options.assert_not_called()
