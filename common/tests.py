from datetime import datetime
from decimal import Decimal
from unittest.mock import patch

from django.db import DatabaseError
from django.test import SimpleTestCase

from .snowflake import fetch_all, fetch_one


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