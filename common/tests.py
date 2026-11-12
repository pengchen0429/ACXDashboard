from datetime import datetime
import sqlite3
from decimal import Decimal
from unittest.mock import patch

from django.db import DatabaseError
from django.test import SimpleTestCase

from .snowflake import fetch_all, fetch_one, get_active_areas


class SnowflakeReadTests(SimpleTestCase):
	def setUp(self):
		connection_patch = patch('common.snowflake.connections')
		self.connections = connection_patch.start()
		self.addCleanup(connection_patch.stop)
		self.cursor = self.connections['snowflake'].cursor.return_value.__enter__.return_value
		self.cursor.description = [('area',), ('TOTAL',)]

	def test_fetch_all_binds_parameters_and_preserves_column_names(self):
		self.cursor.fetchall.return_value = [('Weaving', 3), ('Dyeing', 2)]
		params = ["value'; DELETE FROM example; --"]
		sql = 'SELECT area, COUNT(*) AS TOTAL FROM example WHERE area = %s GROUP BY area'
		self.assertEqual(fetch_all(sql, params), [{'area': 'Weaving', 'TOTAL': 3}, {'area': 'Dyeing', 'TOTAL': 2}])
		self.cursor.execute.assert_called_once_with(sql, params)
		self.connections['snowflake'].cursor.return_value.__exit__.assert_called_once()

	def test_fetch_one_and_empty_results(self):
		self.cursor.fetchone.return_value = ('Weaving', 3)
		self.assertEqual(fetch_one('SELECT area, TOTAL FROM example'), {'area': 'Weaving', 'TOTAL': 3})
		self.cursor.fetchone.return_value = None
		self.assertIsNone(fetch_one('SELECT area, TOTAL FROM example'))
		self.cursor.fetchall.return_value = []
		self.assertEqual(fetch_all('SELECT area, TOTAL FROM example'), [])

	def test_with_query_preserves_driver_value_types(self):
		reported = datetime(2026, 11, 1)
		self.cursor.description = [('reported',), ('amount',)]
		self.cursor.fetchone.return_value = (reported, Decimal('1.25'))
		self.assertEqual(fetch_one('WITH data AS (SELECT 1) SELECT * FROM data'),
			{'reported': reported, 'amount': Decimal('1.25')})

	def test_rejects_empty_multiple_and_non_select_statements(self):
		for sql in (None, '', '  ', 'DELETE FROM example', 'UPDATE example SET total = 0',
			'CREATE TABLE example (id INT)', 'CALL example()', 'SELECT 1; SELECT 2',
			'WITH data AS (SELECT 1) DELETE FROM example'):
			for reader in (fetch_all, fetch_one):
				with self.subTest(sql=sql, reader=reader.__name__):
					with self.assertRaises(ValueError):
						reader(sql)
		self.cursor.execute.assert_not_called()

	def test_database_errors_propagate_and_close_cursor(self):
		self.cursor.execute.side_effect = DatabaseError('unavailable')
		with self.assertRaises(DatabaseError):
			fetch_all('SELECT 1')
		self.connections['snowflake'].cursor.return_value.__exit__.assert_called_once()


class SnowflakeAreaTests(SimpleTestCase):
	def setUp(self):
		self.database = sqlite3.connect(':memory:')
		self.addCleanup(self.database.close)
		self.database.row_factory = sqlite3.Row
		self.database.execute('CREATE TABLE areas (SERVER_SITE_NAME TEXT, code TEXT, active TEXT, createdby TEXT)')
		self.database.executemany('INSERT INTO areas (SERVER_SITE_NAME, code, active) VALUES (?, ?, ?)', [
			('china^907371', ' Weaving Process ', 'true'),
			('china^907371', 'Weaving Process', 'true'),
			('china^907371', 'Dyeing Process', ' TRUE '),
			('china^907371', 'Old Area', 'false'),
			('china^907371', 'Unknown Area', None),
			('china^907371', '  ', 'true'),
			('china^907371', None, 'true'),
			('china^928261', 'Weaving Process', 'true'),
			('china^928261', 'Finishing Process', 'true'),
			('china^928261', 'Old CNX Area', 'false'),
			('china^other', 'Other Factory', 'true'),
		])
		reader_patch = patch('common.snowflake.fetch_all', side_effect=self.execute_query)
		self.fetch = reader_patch.start()
		self.addCleanup(reader_patch.stop)

	def execute_query(self, query, params):
		query = query.replace('PRD_MANUFACTURING_DB.G_L2L_CONSUMPTION.VW_AREAS', 'areas')
		return [dict(row) for row in self.database.execute(query.replace('%s', '?'), params)]

	def test_default_returns_only_active_areas_by_factory(self):
		self.assertEqual(get_active_areas(), {
			'ACX': ['Dyeing Process', 'Weaving Process'],
			'CNX': ['Finishing Process', 'Weaving Process'],
		})
		self.assertEqual(self.fetch.call_args.args[1], ['china^907371', 'china^928261'])

	def test_single_factory_and_repeated_sites(self):
		self.assertEqual(get_active_areas('CNX'), {'CNX': ['Finishing Process', 'Weaving Process']})
		self.assertEqual(self.fetch.call_args.args[1], ['china^928261'])
		self.assertEqual(list(get_active_areas(['ACX', 'ACX'])), ['ACX'])
		self.assertEqual(self.fetch.call_args.args[1], ['china^907371'])

	def test_factory_without_active_areas_is_retained(self):
		self.database.execute('UPDATE areas SET active = ?', ('false',))
		self.assertEqual(get_active_areas(), {'ACX': [], 'CNX': []})

	def test_superuser_created_areas_are_excluded_but_other_creators_retained(self):
		self.database.executemany('INSERT INTO areas VALUES (?, ?, ?, ?)', [
			('china^907371', 'System Area', 'true', 'superuser'),
			('china^928261', 'System Area', 'true', ' SuperUser '),
			('china^907371', 'User Area', 'true', 'operator'),
			('china^907371', 'Empty Creator', 'true', ''),
			('china^907371', 'Inactive User Area', 'false', 'operator'),
		])
		self.assertEqual(get_active_areas(), {
			'ACX': ['Dyeing Process', 'Empty Creator', 'User Area', 'Weaving Process'],
			'CNX': ['Finishing Process', 'Weaving Process'],
		})

	def test_invalid_sites_do_not_query(self):
		for sites in ([], None, 'other', ['ACX', 'other'], ['907371'], [None]):
			with self.subTest(sites=sites), self.assertRaises(ValueError):
				get_active_areas(sites)
		self.fetch.assert_not_called()

	def test_database_errors_are_not_reported_as_empty_areas(self):
		self.fetch.side_effect = DatabaseError('unavailable')
		with self.assertRaises(DatabaseError):
			get_active_areas()