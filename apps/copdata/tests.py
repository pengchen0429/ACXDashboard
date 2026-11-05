import json
from datetime import datetime
from decimal import Decimal
from unittest.mock import MagicMock, patch

from django.db import DatabaseError
from django.test import RequestFactory, SimpleTestCase
from django.urls import resolve, reverse

from common.db import get_cop_data
from .views import copdata_data


class CopDataQueryTests(SimpleTestCase):
	def setUp(self):
		self.connection = MagicMock()
		self.cursor = self.connection.cursor.return_value.__enter__.return_value
		self.columns = [
			'BegDate', 'ProductNO', 'BatchCode', 'decVal4', 'decVal1',
			'decVal2', 'decVal7', 'decVal8', 'decVal9', 'decVal12',
			'decVal29', 'decVal19', 'decVal20', 'decVal21',
		]
		self.cursor.description = [(column,) for column in self.columns]
		self.row = (datetime(2026, 11, 5, 9), 'PRODUCT-1', 'BATCH-1') + (
			Decimal('12.34'),
		) * 11
		self.cursor.fetchall.return_value = [self.row]

	def test_factory_connections_and_returned_fields(self):
		for factory, alias in [('ACX', 'mesaq'), (' cnx ', 'mesaq_cnx')]:
			with self.subTest(factory=factory), patch('common.db.connections') as connections:
				connections.__getitem__.return_value = self.connection
				records = get_cop_data(factory)
				connections.__getitem__.assert_called_once_with(alias)
				self.assertEqual(records, [dict(zip(self.columns, self.row), Factory=factory.strip().upper())])

	def test_join_rules_and_parameterized_filters(self):
		with patch('common.db.connections', {'mesaq': self.connection}):
			get_cop_data(
				start_time='2026-11-01', end_time='2026-11-06',
				product_nos=['PRODUCT-1', "PRODUCT'2"], batch_codes='BATCH-1',
			)
		query, params = self.cursor.execute.call_args.args
		self.assertIn('product.ID = code.DuctID', query)
		self.assertIn('code.TmpCode = sample.TmpCode', query)
		self.assertIn('sample.BatchNo AS BatchCode', query)
		self.assertIn('sample.BegDate >= %s', query)
		self.assertIn('sample.BegDate < %s', query)
		self.assertIn('product.ProductNO IN (%s, %s)', query)
		self.assertIn('sample.BatchNo IN (%s)', query)
		self.assertIn('ORDER BY sample.BegDate DESC, product.ProductNO, sample.BatchNo', query)
		self.assertNotIn('sample.BatchCode', query)
		self.assertNotIn("PRODUCT'2", query)
		self.assertEqual(params, ['2026-11-01', '2026-11-06', 'PRODUCT-1', "PRODUCT'2", 'BATCH-1'])

	def test_invalid_factory_does_not_query(self):
		with patch('common.db.connections') as connections:
			with self.assertRaises(ValueError):
				get_cop_data('OTHER')
			connections.__getitem__.assert_not_called()

	def test_empty_results_and_filters(self):
		self.cursor.fetchall.return_value = []
		with patch('common.db.connections', {'mesaq': self.connection}):
			self.assertEqual(get_cop_data(product_nos=[], batch_codes=[]), [])
		query, params = self.cursor.execute.call_args.args
		self.assertNotIn(' IN (', query)
		self.assertEqual(params, [])


class CopDataApiTests(SimpleTestCase):
	def setUp(self):
		self.factory = RequestFactory()
		self.params = {'date_from': '2026-11-01', 'date_to': '2026-11-05'}

	def test_routes(self):
		self.assertEqual(reverse('copdata'), '/copdata/')
		self.assertEqual(resolve(reverse('copdata-data')).func, copdata_data)

	@patch('apps.copdata.views.get_cop_data')
	def test_real_fields_and_inclusive_end_date(self, query):
		record = {
			'BegDate': datetime(2026, 11, 5, 17, 30), 'Factory': 'ACX',
			'ProductNO': 'PRODUCT-1', 'BatchCode': 'CAR-1',
			'decVal4': Decimal('123.45'), 'decVal1': None,
		}
		query.return_value = [record]
		response = copdata_data(self.factory.get('/copdata/data/', dict(self.params, factory='ACX')))
		data = json.loads(response.content)
		self.assertEqual(response.status_code, 200)
		query.assert_called_once_with('ACX', start_time='2026-11-01', end_time='2026-11-06')
		self.assertEqual(data['records'][0]['decVal4'], 123.45)
		self.assertIsNone(data['records'][0]['decVal1'])
		self.assertEqual(data['records'][0]['BegDate'], '2026-11-05 17:30:00')
		self.assertEqual(data['products'], ['PRODUCT-1'])
		self.assertEqual(data['batches'], ['CAR-1'])

	@patch('apps.copdata.views.get_cop_data', return_value=[])
	def test_default_queries_both_factories(self, query):
		response = copdata_data(self.factory.get('/copdata/data/', self.params))
		self.assertEqual(response.status_code, 200)
		self.assertEqual([call.args[0] for call in query.call_args_list], ['ACX', 'CNX'])

	@patch('apps.copdata.views.get_cop_data')
	def test_invalid_filters_do_not_query(self, query):
		for params in ({}, dict(self.params, factory='OTHER'),
					   dict(self.params, date_from='2026-11-06'),
					   dict(self.params, date_from='2025-01-01')):
			with self.subTest(params=params):
				response = copdata_data(self.factory.get('/copdata/data/', params))
				self.assertEqual(response.status_code, 400)
		query.assert_not_called()

	@patch('apps.copdata.views.get_cop_data', side_effect=DatabaseError('internal details'))
	def test_database_error_does_not_leak_details(self, query):
		with self.assertLogs('apps.copdata.views', level='ERROR'):
			response = copdata_data(self.factory.get('/copdata/data/', self.params))
		self.assertEqual(response.status_code, 503)
		self.assertNotIn(b'internal details', response.content)

	def test_post_not_allowed(self):
		self.assertEqual(copdata_data(self.factory.post('/copdata/data/')).status_code, 405)
