from decimal import Decimal
from io import StringIO
from unittest import TestCase
from unittest.mock import MagicMock, patch

from django.db import InterfaceError, OperationalError
from django.test import SimpleTestCase
from django.urls import reverse

from apps.equipment.management.commands.collect_machine_data import Command
from common.db import FinsWordReader, collect_machine_data, get_machine_polling_intervals


class EquipmentPageTests(SimpleTestCase):
	def test_equipment_page_renders_with_active_navigation(self):
		self.assertEqual(reverse('equipment'), '/equipment/')
		response = self.client.get(reverse('equipment'))
		self.assertEqual(response.status_code, 200)
		self.assertTemplateUsed(response, 'equipment/equipment.html')
		self.assertTemplateUsed(response, 'base.html')
		self.assertContains(response, 'href="/equipment/" data-page="equipment" aria-current="page"')
		self.assertContains(response, 'css/equipment.css')
		self.assertContains(response, 'js/equipment.js')

	def test_dashboard_has_equipment_navigation_link(self):
		response = self.client.get(reverse('dashboard'))
		self.assertEqual(response.status_code, 200)
		self.assertContains(response, 'href="/equipment/" data-page="equipment"')
		self.assertNotContains(response, 'data-page="equipment" aria-current="page"')


class MachineCollectionTests(TestCase):
	def setUp(self):
		self.connections_patch = patch('common.db.connections')
		self.connections = self.connections_patch.start()
		self.addCleanup(self.connections_patch.stop)
		self.cursor = self.connections.__getitem__.return_value.cursor.return_value.__enter__.return_value
		self.cursor.fetchall.return_value = [
			(1, 'BOT', '10.137.82.203', 'OMRON', 'PLAN_QTY', 'D1450', 'INT', Decimal('1.00')),
		]
		self.reader_factory = MagicMock()
		self.reader = self.reader_factory.return_value.__enter__.return_value
		self.reader.read.return_value = 123

	@patch('common.db.transaction.atomic')
	def test_reads_tag_and_inserts_snapshot(self, atomic):
		result = collect_machine_data(machine_id=1, reader_factory=self.reader_factory)
		self.reader.read.assert_called_once_with('D1450', 'INT')
		query, params = self.cursor.execute.call_args.args
		self.assertIn('INSERT INTO dbo.machine_data ([machine_id], [plan_qty])', query)
		self.assertEqual(params, [1, 123])
		self.assertEqual(result[0]['values'], {'plan_qty': 123})
		self.assertTrue(result[0]['saved'])

	def test_dry_run_does_not_insert(self):
		result = collect_machine_data(dry_run=True, reader_factory=self.reader_factory)
		self.assertEqual(self.cursor.execute.call_count, 1)
		self.assertFalse(result[0]['saved'])

	def test_polling_intervals_use_configured_seconds(self):
		self.cursor.fetchall.return_value = [(1, 5), (2, 7)]
		self.assertEqual(get_machine_polling_intervals(machine_id=1), {1: 5, 2: 7})
		self.assertEqual(self.cursor.execute.call_args.args[1], [1])

	def test_invalid_polling_interval_is_rejected(self):
		for interval in (None, 0, -1):
			self.cursor.fetchall.return_value = [(1, interval)]
			with self.assertRaises(ValueError):
				get_machine_polling_intervals()

	@patch('common.db.transaction.atomic')
	def test_all_configured_tags_are_saved_in_one_snapshot(self, atomic):
		self.cursor.fetchall.return_value = [
			(1, 'BOT', '10.137.82.203', 'OMRON', code, address, data_type, scale)
			for code, address, data_type, scale in [
				('PLAN_QTY', 'D1450', 'INT', Decimal('1')),
				('PROD_QTY', 'D1451', 'INT', Decimal('1')),
				('OK_QTY', 'D1452', 'INT', Decimal('1')),
				('NG_QTY', 'D1453', 'INT', Decimal('1')),
				('CYCLE_TIME', 'D1487', 'BCD', Decimal('0.10')),
			]
		]
		self.reader.read.side_effect = [100, 90, 85, 5, 123]
		result = collect_machine_data(reader_factory=self.reader_factory)
		self.assertEqual(self.cursor.execute.call_count, 2)
		self.assertEqual(self.cursor.execute.call_args.args[1], [1, 100, 90, 85, 5, Decimal('12.30')])
		self.assertEqual(result[0]['values']['production_qty'], 90)

	def test_later_tag_failure_does_not_save_partial_snapshot(self):
		self.cursor.fetchall.return_value.append(
			(1, 'BOT', '10.137.82.203', 'OMRON', 'PROD_QTY', 'D1451', 'INT', Decimal('1')),
		)
		self.reader.read.side_effect = [100, TimeoutError('PLC did not respond')]
		with self.assertRaises(TimeoutError):
			collect_machine_data(reader_factory=self.reader_factory)
		self.assertEqual(self.cursor.execute.call_count, 1)

	def test_bcd_decode_and_invalid_digits(self):
		reader = FinsWordReader('10.137.82.203')
		reader.connection = MagicMock()
		reader.connection.memory_area_read.return_value = b'\x00' * 10 + b'\x01\x01\x00\x00\x01\x23'
		self.assertEqual(reader.read('D1487', 'BCD'), 123)
		reader.connection.memory_area_read.return_value = b'\x00' * 10 + b'\x01\x01\x00\x00\x01\xfa'
		with self.assertRaises(ValueError):
			reader.read('D1487', 'BCD')

	def test_read_failure_does_not_insert(self):
		self.reader.read.side_effect = TimeoutError('PLC did not respond')
		with self.assertRaises(TimeoutError):
			collect_machine_data(reader_factory=self.reader_factory)
		self.assertEqual(self.cursor.execute.call_count, 1)

	def test_fractional_quantity_does_not_insert(self):
		self.cursor.fetchall.return_value[0] = (1, 'BOT', '10.137.82.203', 'OMRON', 'PLAN_QTY', 'D1450', 'INT', Decimal('0.01'))
		with self.assertRaises(ValueError):
			collect_machine_data(reader_factory=self.reader_factory)
		self.assertEqual(self.cursor.execute.call_count, 1)

	def test_fins_response_validation_and_signed_word(self):
		reader = FinsWordReader('10.137.82.203')
		reader.connection = MagicMock()
		reader.connection.memory_area_read.return_value = b'\x00' * 10 + b'\x01\x01\x00\x00\xff\xff'
		self.assertEqual(reader.read('D1450', 'INT'), -1)
		self.assertEqual(reader.read('D1450', 'UINT'), 65535)
		reader.connection.memory_area_read.return_value = b'\x00' * 10 + b'\x01\x01\x11\x01\x00\x00'
		with self.assertRaises(ValueError):
			reader.read('D1450', 'INT')


class MachinePollingTests(TestCase):
	def run_polling(self, intervals, fail_first=False, collection_duration=0,
					configuration_error=None, collection_error=None):
		clock = [0]
		calls = []
		options = {'watch': True, 'machine_id': None, 'dry_run': False,
				   'source_node': None, 'destination_node': None}
		command = Command(stdout=StringIO(), stderr=StringIO())

		def sleep(seconds):
			clock[0] += seconds
			if clock[0] >= 11:
				raise KeyboardInterrupt

		def collect(**kwargs):
			calls.append((kwargs['machine_id'], clock[0]))
			clock[0] += collection_duration
			if (fail_first or collection_error is not None) and len(calls) == 1:
				raise collection_error if collection_error is not None else TimeoutError('PLC timeout')
			return []

		configuration_calls = [0]

		def read_intervals(machine_id):
			configuration_calls[0] += 1
			if configuration_error is not None and configuration_calls[0] == 1:
				raise configuration_error
			return intervals(clock[0])

		module = 'apps.equipment.management.commands.collect_machine_data'
		with patch(module + '.time') as mock_time, \
			 patch(module + '.get_machine_polling_intervals') as get_intervals, \
			 patch(module + '.collect_machine_data', side_effect=collect), \
			 patch(module + '.connections') as connections, \
			 patch(module + '.close_old_connections'):
			mock_time.monotonic.side_effect = lambda: clock[0]
			mock_time.sleep.side_effect = sleep
			get_intervals.side_effect = read_intervals
			command.handle(**options)
			if configuration_error is not None or collection_error is not None:
				connections.__getitem__.return_value.close.assert_called_once_with()
		return calls

	def test_each_machine_uses_its_own_interval(self):
		calls = self.run_polling(lambda now: {1: 5, 2: 7})
		self.assertEqual(calls, [(1, 0), (2, 0), (1, 5), (2, 7), (1, 10)])

	def test_failed_machine_retries_next_interval_without_blocking_others(self):
		calls = self.run_polling(lambda now: {1: 5, 2: 7}, fail_first=True)
		self.assertEqual(calls, [(1, 0), (2, 0), (1, 5), (2, 7), (1, 10)])

	def test_interval_changes_are_applied_while_running(self):
		calls = self.run_polling(lambda now: {1: 5 if now < 2 else 3})
		self.assertEqual(calls, [(1, 0), (1, 3), (1, 6), (1, 9)])

	def test_disabled_machine_stops_being_collected(self):
		calls = self.run_polling(lambda now: {1: 5} if now < 2 else {})
		self.assertEqual(calls, [(1, 0)])

	def test_slow_collection_waits_full_interval_before_next_snapshot(self):
		calls = self.run_polling(lambda now: {1: 5}, collection_duration=2)
		self.assertEqual(calls, [(1, 0), (1, 7)])

	def test_database_disconnect_during_configuration_reconnects_and_resumes(self):
		for error_type in (OperationalError, InterfaceError):
			with self.subTest(error_type=error_type):
				calls = self.run_polling(lambda now: {1: 5}, configuration_error=error_type('08S01'))
				self.assertEqual(calls, [(1, 5), (1, 10)])

	def test_database_write_failure_closes_connection_and_waits_for_next_cycle(self):
		calls = self.run_polling(lambda now: {1: 5, 2: 7}, collection_error=OperationalError('08S01'))
		self.assertEqual(calls, [(1, 0), (2, 0), (1, 5), (2, 7), (1, 10)])
