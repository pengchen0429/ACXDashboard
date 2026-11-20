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
		self.assertEqual(params[2:], ['DYE', 'DYE', *services.WEAVING_EXCLUDED_PRODUCTS])
		self.assertEqual(sql.count('%s'), len(params))
		services._query_rows(cursor, 'production', start, end, filters, daily=True)
		daily_sql, daily_params = cursor.execute.call_args.args
		self.assertIn('CONVERT(char(10), a.RecDate, 120)', daily_sql)
		self.assertEqual(daily_params, params)
		services._query_rows(cursor, 'scrap', start, end, filters)
		sql, params = cursor.execute.call_args.args
		self.assertIn('a.cDefine1 = b.equipNo', sql)
		self.assertIn('a.DuctID = p.ID', sql)
		self.assertIn('a.DefCode = g.BarCode', sql)
		self.assertEqual(params[4:6], [start, datetime(2026, 10, 29, 8, 31)])
		self.assertEqual(params[6:9], list(services.CATEGORIES))
		self.assertNotIn('过程不合格', params)
		self.assertEqual(params[9:13], ['C', 'C2', "D'; --", 'D2'])
		self.assertEqual(sql.count(' IN ('), 3)
		self.assertEqual(sql.count('%s'), len(params))

	def test_actual_sql_preserves_quantities(self):
		database = sqlite3.connect(':memory:')
		database.create_function('LTRIM', 1, lambda value: value.lstrip() if value else value)
		database.executescript('''
			CREATE TABLE tabWorkDayRpt (RecDate, EquipNo, DuctID, DayQty);
			CREATE TABLE tabEquipment (equipNo, equipName, xflag);
			CREATE TABLE tabEquipType (id, LineName, EquipType);
			CREATE TABLE tabProduct (ID, ProductName, ProductNO);
			INSERT INTO tabEquipment VALUES ('W1', 'Line1', 1);
			INSERT INTO tabEquipType VALUES (1, 'WEAV', 'Weaving');
			INSERT INTO tabProduct VALUES (1, 'A', 'A');
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

	def test_weaving_uses_dye_production_with_six_product_exclusions(self):
		database = sqlite3.connect(':memory:')
		self.addCleanup(database.close)
		database.executescript('''
			CREATE TABLE tabWorkDayRpt (RecDate, EquipNo, DuctID, DayQty);
			CREATE TABLE tabEquipment (equipNo, equipName, xflag);
			CREATE TABLE tabEquipType (id, LineName);
			CREATE TABLE tabProduct (ID, ProductName, ProductNO);
			INSERT INTO tabEquipment VALUES ('W1', 'Weaving1', 1), ('D1', 'Dyeing1', 2);
			INSERT INTO tabEquipType VALUES (1, 'WEAV'), (2, 'DYE');
			INSERT INTO tabProduct VALUES (100, 'P1000YYYY000M', 'A'), (101, NULL, NULL),
			(102, '', ''), (103, 'Near match', 'P1000YYYY000MX');
			INSERT INTO tabWorkDayRpt VALUES
			('2026-10-28', 'W1', 100, 400), ('2026-10-28', 'W1', 101, 13),
			('2026-10-28', 'W1', 102, 19), ('2026-10-28', 'W1', 103, 7),
			('2026-10-28', 'W1', 999, 17), ('2026-10-28', 'D1', 100, 400);
		''')
		for product_id, name in enumerate(services.WEAVING_EXCLUDED_PRODUCTS, 1):
			database.execute('INSERT INTO tabProduct VALUES (?, ?, ?)', [product_id, str(product_id), ' ' + name + ' '])
			for equipment, quantity in (('W1', 10), ('D1', 20)):
				database.execute('INSERT INTO tabWorkDayRpt VALUES (?, ?, ?, ?)',
					['2026-10-28', equipment, product_id, quantity])
		for tab, expected in (('overview', {'WEAV': 456, 'DYE': 520}),
							  ('weaving', {'DYE': 400}), ('dyeing', {'DYE': 520})):
			with self.subTest(tab=tab):
				cursor = Mock()
				services._query_rows(cursor, 'production', datetime(2026, 10, 28, 8, 30),
					datetime(2026, 10, 29, 8, 30), {'tab': tab})
				sql, params = cursor.execute.call_args.args
				self.assertEqual(sql.count('%s'), len(params))
				if tab != 'dyeing':
					self.assertIn('p.ProductNO', sql)
				sql = sql.replace("CONVERT(char(7), a.RecDate, 120)", 'substr(a.RecDate, 1, 7)').replace("N'", "'")
				rows = database.execute(sql.replace('%s', '?'),
					[value.strftime('%Y-%m-%d') if isinstance(value, datetime) else value for value in params]).fetchall()
				totals = {}
				for month, area, line, product, quantity in rows:
					totals[area] = totals.get(area, 0) + quantity
				self.assertEqual(totals, expected)

	def test_weaving_defect_sql_applies_chart_only_restrictions(self):
		cursor = Mock()
		cursor.fetchall.return_value = []
		filters = {'tab': 'weaving', 'category': ['织造不合格'], 'defect': ['D']}
		start, end = datetime(2026, 10, 28, 8, 30), datetime(2026, 10, 29, 8, 30)
		services._query_rows(cursor, 'weaving_defects', start, end, filters)
		sql, params = cursor.execute.call_args.args
		self.assertIn('a.cDefine10 IN (%s, %s, %s, %s, %s)', sql)
		self.assertIn(services.CATEGORY + ' = %s', sql)
		self.assertIn(services.DEFECT + ' NOT IN (%s, %s)', sql)
		self.assertEqual(params[-12:-4], ['织造不合格', *services.WEAVING_SCRAP_CLASSES,
			*services.WEAVING_EXCLUDED_DEFECTS])
		self.assertEqual(sql.count('%s'), len(params))
		services._query_rows(cursor, 'scrap', start, end, filters)
		self.assertNotIn('a.cDefine10', cursor.execute.call_args.args[0])

	@patch('apps.dpmu.services.connections')
	def test_weaving_defect_chart_preserves_other_statistics_and_denominator(self, connections):
		cursor = connections['mesaq'].cursor.return_value.__enter__.return_value
		production = [('2026-10', 'DYE', 'D1', 'A', 400)]
		scrap = [('2026-10', 'WEAV', 'W1', 'A', '织造不合格', 'D', 40)]
		filtered = [('2026-10', 'WEAV', 'W1', 'A', '织造不合格', 'D', 10)]
		cursor.fetchall.side_effect = [production, scrap, filtered, [], [], [], []]
		result = services.get_summary(datetime(2026, 10, 28, 8, 30),
			datetime(2026, 10, 29, 8, 30), {'tab': 'weaving'})
		self.assertEqual(result['total']['scrap'], 40)
		self.assertEqual(result['defects'][0]['dpmu'], 100000)
		self.assertEqual(result['weaving_defects'], [
			{'name': 'D', 'production': 400, 'scrap': 10, 'dpmu': 25000}])
		self.assertEqual(result['weaving_total'],
			{'name': 'TOTAL', 'production': 400, 'scrap': 10, 'dpmu': 25000})
		self.assertIsNone(result['weaving_months'][0]['previous_dpmu'])
		self.assertIsNone(result['weaving_months'][0]['change_percent'])
		self.assertEqual(cursor.execute.call_count, 7)
		for index in (0, 3, 5):
			self.assertEqual(cursor.execute.call_args_list[index].args[1][2:4], ['DYE', 'DYE'])
		for tab in ('overview', 'dyeing'):
			cursor.reset_mock()
			cursor.fetchall.side_effect = [production, scrap]
			result = services.get_summary(datetime(2026, 10, 28, 8, 30),
				datetime(2026, 10, 29, 8, 30), {'tab': tab})
			self.assertNotIn('weaving_defects', result)
			self.assertNotIn('weaving_total', result)
			self.assertEqual(cursor.execute.call_count, 2)

	@patch('apps.dpmu.services.connections')
	def test_weaving_monthly_comparison_daily_trend_and_product_denominators(self, connections):
		cursor = connections['mesaq'].cursor.return_value.__enter__.return_value
		production = [('2024-02', 'WEAV', 'W1', 'P20AAYYYY000J', 100), ('2024-02', 'WEAV', 'W1', 'P25BBYYYY000J', 300)]
		scrap = [('2024-02', 'WEAV', 'W1', 'P20AAYYYY000J', '织造不合格', 'D', 10),
			('2024-02', 'WEAV', 'W1', 'P25BBYYYY000J', '织造不合格', 'D', 15)]
		daily_production = [('2024-02-28', 'WEAV', 'W1', 'A', 100), ('2024-02-29', 'WEAV', 'W1', 'B', 300)]
		daily_scrap = [('2024-02-28', 'WEAV', 'W1', 'A', '织造不合格', 'D', 10),
			('2024-02-29', 'WEAV', 'W1', 'B', '织造不合格', 'D', 15)]
		cursor.fetchall.side_effect = [production, scrap, scrap, daily_production, daily_scrap,
			[('2024-01', 'WEAV', 'W1', 'A', 200)],
			[('2024-01', 'WEAV', 'W1', 'A', '织造不合格', 'D', 10)]]
		result = services.get_summary(datetime(2024, 2, 27, 8, 30), datetime(2024, 3, 1, 8, 30), {'tab': 'weaving'})
		self.assertEqual(result['weaving_total']['dpmu'], 62500)
		self.assertEqual(result['weaving_months'][0]['previous_month'], '2024-01')
		self.assertEqual(result['weaving_months'][0]['previous_dpmu'], 50000)
		self.assertEqual(result['weaving_months'][0]['change_percent'], 25)
		self.assertEqual([row['name'] for row in result['weaving_days']], ['2024-02-27', '2024-02-28', '2024-02-29'])
		self.assertEqual([row['dpmu'] for row in result['weaving_days']], [None, 100000, 50000])
		self.assertEqual(sum(row['scrap'] for row in result['weaving_days']), result['weaving_total']['scrap'])
		self.assertEqual({row['name']: row['dpmu'] for row in result['weaving_products']}, {'P20A': 25000, 'P25B': 37500})
		self.assertEqual({row['name']: row['production'] for row in result['weaving_products']}, {'P20A': 100, 'P25B': 300})
		self.assertTrue(all(row['denominator_production'] == 400 for row in result['weaving_products']))
		for call in cursor.execute.call_args_list:
			self.assertEqual(call.args[0].count('%s'), len(call.args[1]))
		self.assertIn('CONVERT(char(10), a.RecDate, 120)', cursor.execute.call_args_list[3].args[0])
		self.assertIn('CONVERT(char(10), CASE', cursor.execute.call_args_list[4].args[0])
		self.assertEqual(cursor.execute.call_args_list[5].args[1][:2], [datetime(2024, 1, 27), datetime(2024, 2, 1)])

	def test_belt_extracts_product_name_characters_one_to_four_before_aggregation(self):
		production = [('2026-10', 'WEAV', 'W1', 'P20AAYYYY000J', 100),
			('2026-10', 'WEAV', 'W2', 'P20AAZZZZ001M', 300),
			('2026-10', 'WEAV', 'W1', 'AB', 50)]
		scrap = [('2026-10', 'WEAV', 'W1', 'P20AAYYYY000J', '织造不合格', 'D', 10),
			('2026-10', 'WEAV', 'W2', 'P20AAZZZZ001M', '织造不合格', 'D', 30),
			('2026-10', 'WEAV', 'W3', 'P25BBYYYY000J', '织造不合格', 'D', 5)]
		result = services.summarize(services._belt_rows(production), services._belt_rows(scrap), [])
		belts = {row['name']: row for row in result['products']}
		self.assertEqual(belts['P20A'], {'name': 'P20A', 'production': 400, 'scrap': 40, 'dpmu': 100000})
		self.assertIsNone(belts['P25B']['dpmu'])
		self.assertEqual(belts['未分类']['production'], 50)
		self.assertEqual(sum(row['production'] for row in belts.values()), 450)
		self.assertEqual(sum(row['scrap'] for row in belts.values()), 45)
		self.assertEqual(production[0][3], 'P20AAYYYY000J')
		self.assertEqual(services._belt_rows([('2026-10', 'WEAV', 'W1', 'P20A', 1)])[0][3], 'P20A')

	def test_belt_total_denominator_does_not_change_default_product_ratios(self):
		production = [('2026-10', 'WEAV', 'W1', 'P20A', 100), ('2026-10', 'WEAV', 'W2', 'P25B', 300)]
		scrap = [('2026-10', 'WEAV', 'W1', 'P20A', '织造不合格', 'D', 10),
			('2026-10', 'WEAV', 'W3', 'P30C', '织造不合格', 'D', 5)]
		result = services.summarize(production, scrap, [], products_use_total=True)
		belts = {row['name']: row for row in result['products']}
		self.assertEqual(belts['P20A']['dpmu'], 25000)
		self.assertEqual(belts['P30C']['dpmu'], 12500)
		self.assertEqual(belts['P20A']['production'], 100)
		self.assertEqual(belts['P25B']['production'], 300)
		self.assertEqual(belts['P30C']['production'], 0)
		self.assertEqual(sum(row['production'] for row in belts.values()), result['total']['production'])
		self.assertTrue(all(row['denominator_production'] == 400 for row in belts.values()))
		self.assertEqual(sum(row['dpmu'] for row in belts.values()), result['total']['dpmu'])
		original = services.summarize(production, scrap, [])
		self.assertEqual(next(row for row in original['products'] if row['name'] == 'P20A')['dpmu'], 100000)
		self.assertTrue(all(row['dpmu'] is None for row in services.summarize(
			[], scrap, [], products_use_total=True)['products']))

	def test_previous_month_clamps_days_and_handles_year_rollover(self):
		for value, expected in (
			(datetime(2024, 3, 31, 8, 30), datetime(2024, 2, 29, 8, 30)),
			(datetime(2023, 3, 31, 8, 30), datetime(2023, 2, 28, 8, 30)),
			(datetime(2024, 1, 15, 8, 30), datetime(2023, 12, 15, 8, 30)),
		):
			with self.subTest(value=value):
				self.assertEqual(services._previous_month(value), expected)

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
								'category': ['织造不合格', '染色不合格', '织造不合格', ' '], 'defect': ['D,1', 'D2'],
								'area': 'ignored', 'product': 'ignored'})
		self.assertEqual(views.data(request).status_code, 200)
		self.assertEqual(summary.call_args.args[2],
						 {'tab': 'overview', 'category': ['织造不合格', '染色不合格'], 'defect': ['D,1', 'D2']})

	@patch('apps.dpmu.views.get_summary')
	@patch('apps.dpmu.views.get_options')
	def test_process_category_is_rejected_before_database(self, options, summary):
		for view in (views.data, views.options):
			response = view(self.request({'start_time': '2026-10-28T08:30',
				'end_time': '2026-10-29T08:30', 'category': '过程不合格'}))
			self.assertEqual(response.status_code, 400)
		options.assert_not_called()
		summary.assert_not_called()

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

	def test_scrap_is_attributed_by_category_and_process_is_excluded(self):
		rows = [('2026-10', 'DYE', 'D1', 'A', '织造不合格', 'D', 10),
			('2026-10', 'WEAV', 'W1', 'A', '染色不合格', 'D', 20),
			('2026-10', 'WEAV', 'W1', 'A', '染色报废', 'D', 30),
			('2026-10', 'FP', 'F1', 'A', '过程不合格', 'D', 5),
			('2026-10', 'WEAV', 'W1', 'A', '其他', 'D', 1000)]
		weaving = services.allocate_scrap(rows, 'weaving')
		dyeing = services.allocate_scrap(rows, 'dyeing')
		overview = services.allocate_scrap(rows)
		self.assertEqual(sum(row[-1] for row in weaving), 10)
		self.assertEqual(sum(row[-1] for row in dyeing), 50)
		self.assertEqual(sum(row[-1] for row in overview), 60)
		self.assertTrue(all(row[1] == 'WEAV' for row in weaving))
		self.assertTrue(all(row[1] == 'DYE' for row in dyeing))
		self.assertEqual(weaving[-1][2], '未分配产线')

	def test_process_is_excluded_from_all_statistics(self):
		rows = [('2026-10', 'WEAV', 'W1', 'A', '过程不合格', 'D', 5)]
		for tab in ('overview', 'weaving', 'dyeing'):
			self.assertEqual(services.allocate_scrap(rows, tab), [])
		result = services.summarize(
			[('2026-10', 'WEAV', 'W1', 'A', 100), ('2026-10', 'DYE', 'D1', 'A', 200)],
			services.allocate_scrap(rows), ['2026-10'])
		self.assertEqual(result['total']['production'], 300)
		self.assertEqual(result['total']['scrap'], 0)
		self.assertEqual(result['total']['dpmu'], 0)
		for dimension in ('months', 'areas', 'lines', 'products', 'categories', 'defects'):
			self.assertTrue(all(row['scrap'] == 0 for row in result[dimension]))
		self.assertEqual(result['categories'], [])
		self.assertEqual(result['defects'], [])

	@patch('apps.dpmu.services.connections')
	def test_options_scope_uses_category_allocation_not_equipment(self, connections):
		cursor = connections['mesaq'].cursor.return_value.__enter__.return_value
		cursor.fetchall.return_value = [('织造不合格', 'D')]
		result = services.get_options(datetime(2026, 10, 28, 8, 30), datetime(2026, 10, 29, 8, 30),
			{'tab': 'weaving', 'category': []})
		sql, params = cursor.execute.call_args.args
		self.assertEqual(params[2:], ['织造不合格'])
		self.assertNotIn('EquipType', sql)
		self.assertEqual(result['categories'], ['织造不合格'])

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
