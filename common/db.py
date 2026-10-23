# 数据库公共操作
import ipaddress
import re
import socket
from decimal import Decimal

from django.db import connections, transaction
from fins import FinsPLCMemoryAreas
from fins.udp import UDPFinsConnection


TAG_COLUMNS = {
	'PLAN_QTY': 'plan_qty',
	'PROD_QTY': 'production_qty',
	'PRODUCTION_QTY': 'production_qty',
	'OK_QTY': 'ok_qty',
	'NG_QTY': 'ng_qty',
	'CYCLE_TIME': 'cycle_time',
}


class FinsWordReader:
	def __init__(self, ip_address, source_node=None, destination_node=None, timeout=3):
		self.connection = None
		self.ip_address = str(ipaddress.IPv4Address(ip_address))
		self.source_node = source_node
		self.destination_node = destination_node
		self.timeout = timeout

	def __enter__(self):
		source_node = self.source_node
		if source_node is None:
			with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as route_socket:
				route_socket.connect((self.ip_address, 9600))
				source_node = int(route_socket.getsockname()[0].split('.')[-1])
		destination_node = self.destination_node
		if destination_node is None:
			destination_node = int(self.ip_address.split('.')[-1])
		if not 1 <= source_node <= 254 or not 1 <= destination_node <= 254:
			raise ValueError('FINS node numbers must be between 1 and 254')
		self.connection = UDPFinsConnection()
		try:
			self.connection.connect(self.ip_address, bind_port=0)
			self.connection.srce_node_add = source_node
			self.connection.dest_node_add = destination_node
			self.connection.fins_socket.settimeout(self.timeout)
		except Exception:
			self.connection.fins_socket.close()
			raise
		return self

	def read(self, address, data_type):
		match = re.fullmatch(r'D(\d+)', address.strip().upper())
		if not match or int(match.group(1)) > 65535:
			raise ValueError('Only D0-D65535 word addresses are supported: ' + address)
		data_type = data_type.strip().upper()
		if data_type not in ('INT', 'UINT', 'WORD', 'BCD'):
			raise ValueError('Unsupported PLC data type: ' + data_type)
		word_address = int(match.group(1)).to_bytes(2, 'big') + b'\x00'
		response = self.connection.memory_area_read(
			FinsPLCMemoryAreas().DATA_MEMORY_WORD, word_address, 1,
		)
		if len(response) < 14 or response[10:12] != b'\x01\x01':
			raise ValueError('Invalid FINS memory read response')
		if response[12:14] != b'\x00\x00':
			raise ValueError('FINS read failed with end code ' + response[12:14].hex())
		if len(response) != 16:
			raise ValueError('Invalid FINS word payload length')
		if data_type == 'BCD':
			digits = response[14:16].hex()
			if any(digit not in '0123456789' for digit in digits):
				raise ValueError('Invalid packed BCD word: ' + digits)
			return int(digits)
		return int.from_bytes(response[14:16], 'big', signed=data_type == 'INT')

	def __exit__(self, exception_type, exception, traceback):
		self.connection.fins_socket.close()


def get_machine_polling_intervals(machine_id=None):
	query = """
SELECT m.id, m.polling_interval
FROM dbo.machine m
WHERE m.is_active = 1
AND EXISTS (SELECT 1 FROM dbo.machine_tag t WHERE t.machine_id = m.id)
"""
	params = []
	if machine_id is not None:
		query += ' AND m.id = %s'
		params.append(machine_id)
	with connections['default'].cursor() as cursor:
		cursor.execute(query, params)
		rows = cursor.fetchall()
	intervals = {}
	for current_id, interval in rows:
		if interval is None or interval <= 0:
			raise ValueError('polling_interval must be positive for machine ' + str(current_id))
		intervals[current_id] = interval
	return intervals


def collect_machine_data(machine_id=None, dry_run=False, source_node=None,
						 destination_node=None, reader_factory=None):
	reader_factory = reader_factory or FinsWordReader
	query = """
SELECT m.id, m.machine_code, m.ip_address, m.plc_brand,
	   t.tag_code, t.plc_address, t.data_type, t.scale
FROM dbo.machine m
JOIN dbo.machine_tag t ON t.machine_id = m.id
WHERE m.is_active = 1
"""
	params = []
	if machine_id is not None:
		query += ' AND m.id = %s'
		params.append(machine_id)
	query += ' ORDER BY m.id, t.id'
	with connections['default'].cursor() as cursor:
		cursor.execute(query, params)
		rows = cursor.fetchall()
	machines = {}
	for row in rows:
		machines.setdefault(row[0], []).append(row)
	if not machines:
		raise ValueError('No active machines with configured tags were found')
	results = []
	for current_id, tags in machines.items():
		if (tags[0][3] or '').strip().upper() != 'OMRON':
			raise ValueError('Only OMRON FINS machines are supported')
		columns = []
		for tag in tags:
			column = TAG_COLUMNS.get(tag[4].strip().upper())
			if column is None or column in columns:
				raise ValueError('Unsupported or duplicate tag_code: ' + tag[4])
			columns.append(column)
		values = []
		with reader_factory(tags[0][2], source_node=source_node,
							destination_node=destination_node) as reader:
			for tag, column in zip(tags, columns):
				raw_value = reader.read(tag[5], tag[6])
				value = Decimal(raw_value) * (Decimal(tag[7]) if tag[7] is not None else Decimal(1))
				if not value.is_finite():
					raise ValueError('Non-finite value for ' + tag[4])
				if column != 'cycle_time':
					if value != value.to_integral_value() or not -2147483648 <= value <= 2147483647:
						raise ValueError('Value does not fit SQL INT for ' + tag[4])
					value = int(value)
				values.append(value)
		if not dry_run:
			column_sql = ', '.join('[' + column + ']' for column in columns)
			placeholders = ', '.join(['%s'] * (len(values) + 1))
			with transaction.atomic(using='default'):
				with connections['default'].cursor() as cursor:
					cursor.execute(
						'INSERT INTO dbo.machine_data ([machine_id], ' + column_sql + ') VALUES (' + placeholders + ')',
						[current_id] + values,
					)
		results.append({'machine_id': current_id, 'machine_code': tags[0][1],
						'values': dict(zip(columns, values)), 'saved': not dry_run})
	return results