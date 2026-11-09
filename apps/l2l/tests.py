import io
import json
from datetime import datetime, timezone
from unittest.mock import patch
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, urlsplit

from django.test import SimpleTestCase, override_settings

from common.l2l_api import L2LAPIError, get_daily_production, get_weekly_production, record_pitch_details


@override_settings(
	L2L_BASE_URL="https://example.test/api/1.0/",
	L2L_AUTH="test-secret",
	L2L_SITE="123",
	L2L_SITE_ACX=None,
	TIME_ZONE="Asia/Shanghai",
	USE_TZ=True,
)
class WeeklyProductionTests(SimpleTestCase):
	def response(self, payload):
		return io.BytesIO(json.dumps(payload).encode("utf-8"))

	@patch("common.l2l_api.urlopen")
	def test_request_parameters_and_original_values(self, mock_open):
		rows = [{"line_id": 2401, "actual": "22997.00"}]
		mock_open.return_value = self.response({"success": True, "data": rows})
		result = get_weekly_production(
			"LOOM001,LOOM002", "2026-11-02 08:30",
			show_shifts=True, include_inactive_lines=True, timeout=10,
		)
		self.assertEqual(result, rows)
		url = urlsplit(mock_open.call_args.args[0])
		self.assertEqual(url.path, "/api/1.0/reporting/production/weekly_summary_data_by_line/")
		self.assertEqual(parse_qs(url.query), {
			"auth": ["test-secret"], "site": ["123"],
			"date": ["2026-11-02 08:30"], "linecode": ["LOOM001,LOOM002"],
			"show_shifts": ["true"], "include_inactive_lines": ["true"],
		})
		self.assertEqual(mock_open.call_args.kwargs, {"timeout": 10})

	@patch("common.l2l_api.timezone.now")
	@patch("common.l2l_api.urlopen")
	def test_default_date_uses_local_current_time(self, mock_open, mock_now):
		mock_now.return_value = datetime(2026, 11, 2, 1, 15, tzinfo=timezone.utc)
		mock_open.return_value = self.response({"success": True, "data": []})
		self.assertEqual(get_weekly_production("LOOM001"), [])
		params = parse_qs(urlsplit(mock_open.call_args.args[0]).query)
		self.assertEqual(params["date"], ["2026-11-02 09:15"])

	@patch("common.l2l_api.urlopen")
	def test_invalid_inputs_do_not_send_request(self, mock_open):
		for linecode, date in [("", None), (None, None), ("LOOM001", "2026-11-02")]:
			with self.subTest(linecode=linecode, date=date):
				with self.assertRaises(ValueError):
					get_weekly_production(linecode, date)
		mock_open.assert_not_called()

	@override_settings(L2L_AUTH="")
	@patch("common.l2l_api.urlopen")
	def test_missing_configuration(self, mock_open):
		with self.assertRaises(L2LAPIError):
			get_weekly_production("LOOM001")
		mock_open.assert_not_called()

	@patch("common.l2l_api.urlopen")
	def test_transport_errors_do_not_expose_credentials(self, mock_open):
		errors = [
			HTTPError("https://example.test/?auth=test-secret", 403, "test-secret", {}, None),
			URLError("test-secret"),
			TimeoutError("test-secret"),
		]
		for error in errors:
			with self.subTest(error=type(error).__name__):
				mock_open.side_effect = error
				with self.assertRaises(L2LAPIError) as caught:
					get_weekly_production("LOOM001")
				self.assertNotIn("test-secret", str(caught.exception))
				self.assertTrue(caught.exception.__suppress_context__)

	@patch("common.l2l_api.urlopen")
	def test_invalid_json(self, mock_open):
		mock_open.return_value = io.BytesIO(b"not json")
		with self.assertRaisesMessage(L2LAPIError, "invalid JSON"):
			get_weekly_production("LOOM001")

	@patch("common.l2l_api.urlopen")
	def test_unsuccessful_or_malformed_responses(self, mock_open):
		for payload in [
			{"success": False, "error": "test-secret"}, [],
			{"success": True}, {"success": True, "data": {}},
			{"success": True, "data": [None]},
		]:
			with self.subTest(payload=payload):
				mock_open.return_value = self.response(payload)
				with self.assertRaises(L2LAPIError) as caught:
					get_weekly_production("LOOM001")
				self.assertNotIn("test-secret", str(caught.exception))


@override_settings(
	L2L_BASE_URL="https://example.test/api/1.0/",
	L2L_AUTH="test-secret",
	L2L_SITE="123",
	L2L_SITE_ACX=None,
)
class DailyProductionTests(SimpleTestCase):
	@override_settings(L2L_SITE_ACX='acx-site', L2L_SITE_CNX='cnx-site')
	@patch('common.l2l_api.urlopen')
	def test_selects_configured_site(self, mock_open):
		for site, expected in [('ACX', 'acx-site'), ('CNX', 'cnx-site'), (None, 'acx-site')]:
			with self.subTest(site=site):
				mock_open.return_value = io.BytesIO(b'{"success": true, "data": []}')
				get_daily_production('2026-11-03 08:30', '2026-11-04 08:30', site=site)
				params = parse_qs(urlsplit(mock_open.call_args.args[0]).query)
				self.assertEqual(params['site'], [expected])

	@override_settings(L2L_SITE_CNX='')
	@patch('common.l2l_api.urlopen')
	def test_missing_selected_site_does_not_fall_back(self, mock_open):
		with self.assertRaises(L2LAPIError):
			get_daily_production('2026-11-03 08:30', '2026-11-04 08:30', site='CNX')
		mock_open.assert_not_called()

	@patch("common.l2l_api.urlopen")
	def test_request_parameters_and_original_values(self, mock_open):
		rows = [{"line_id": 2401, "actual": "899.00"}]
		mock_open.return_value = io.BytesIO(json.dumps({
			"success": True, "data": rows,
		}).encode("utf-8"))
		self.assertEqual(get_daily_production(
			"2026-11-02 08:30", "2026-11-03 08:30", "LOOM001,LOOM002", timeout=10,
		), rows)
		url = urlsplit(mock_open.call_args.args[0])
		self.assertEqual(url.path, "/api/1.0/reporting/production/daily_summary_data_by_line/")
		self.assertEqual(parse_qs(url.query), {
			"auth": ["test-secret"], "site": ["123"],
			"start": ["2026-11-02 08:30"], "end": ["2026-11-03 08:30"],
			"linecode": ["LOOM001,LOOM002"],
		})
		self.assertEqual(mock_open.call_args.kwargs, {"timeout": 10})

	@patch("common.l2l_api.urlopen")
	def test_optional_line_filters(self, mock_open):
		for filters in [{}, {"line_externalid": "ext-1,ext-2"}, {"line_id": "2401,2402"}]:
			with self.subTest(filters=filters):
				mock_open.return_value = io.BytesIO(b'{"success": true, "data": []}')
				self.assertEqual(get_daily_production(
					"2026-11-02 08:30", "2026-11-03 08:30", **filters,
				), [])
				params = parse_qs(urlsplit(mock_open.call_args.args[0]).query)
				for name in ("linecode", "line_externalid", "line_id"):
					if name in filters:
						self.assertEqual(params[name], [filters[name]])
					else:
						self.assertNotIn(name, params)

	@patch("common.l2l_api.urlopen")
	def test_invalid_intervals_do_not_send_request(self, mock_open):
		for start, end in [
			("2026-11-02", "2026-11-03 08:30"),
			("2026-11-02 08:30", "invalid"),
			(None, "2026-11-03 08:30"),
			("2026-11-02 08:30", "2026-11-02 08:30"),
			("2026-11-03 08:30", "2026-11-02 08:30"),
		]:
			with self.subTest(start=start, end=end):
				with self.assertRaises(ValueError):
					get_daily_production(start, end)
		mock_open.assert_not_called()

	@patch("common.l2l_api.urlopen")
	def test_invalid_filters_do_not_send_request(self, mock_open):
		for filters in [{"linecode": " "}, {"line_externalid": ""}, {"line_id": 2401}]:
			with self.subTest(filters=filters):
				with self.assertRaises(ValueError):
					get_daily_production("2026-11-02 08:30", "2026-11-03 08:30", **filters)
		mock_open.assert_not_called()

	@override_settings(L2L_AUTH="")
	@patch("common.l2l_api.urlopen")
	def test_missing_configuration(self, mock_open):
		with self.assertRaises(L2LAPIError):
			get_daily_production("2026-11-02 08:30", "2026-11-03 08:30")
		mock_open.assert_not_called()

	@patch("common.l2l_api.urlopen")
	def test_api_failure(self, mock_open):
		mock_open.return_value = io.BytesIO(b'{"success": false, "error": "test-secret"}')
		with self.assertRaises(L2LAPIError) as caught:
			get_daily_production("2026-11-02 08:30", "2026-11-03 08:30", "LOOM001")
		self.assertNotIn("test-secret", str(caught.exception))


@override_settings(
	L2L_BASE_URL="https://example.test/api/1.0/",
	L2L_AUTH="test-secret", L2L_SITE_ACX="acx-site", L2L_SITE_CNX="cnx-site",
)
class PitchDetailsTests(SimpleTestCase):
	def record(self, **kwargs):
		params = {
			"start": "2026-11-06 08:30:00", "end": "2026-11-06 09:00:00",
			"linecode": "LOOM001", "productcode": "SKU001",
		}
		return record_pitch_details(**{**params, **kwargs})

	@patch("common.l2l_api.urlopen")
	def test_post_parameters_and_complete_response(self, mock_open):
		payload = {"success": True, "data": {"id": 42}, "message": "recorded"}
		mock_open.return_value = io.BytesIO(json.dumps(payload).encode("utf-8"))
		self.assertEqual(self.record(
			start="2026-11-06 08:30:00.123456", actual="1453.74", scrap=0,
			operator_count="2.50", unit_of_measure_code="M", comment="Shift A & B",
			continue_current_build_sequence=True, site="CNX", timeout=10,
		), payload)
		request = mock_open.call_args.args[0]
		self.assertEqual(request.get_method(), "POST")
		self.assertEqual(urlsplit(request.full_url).path, "/api/1.0/pitchdetails/record_details/")
		self.assertEqual(parse_qs(urlsplit(request.full_url).query), {"auth": ["test-secret"]})
		self.assertEqual(parse_qs(request.data.decode("utf-8")), {
			"site": ["cnx-site"], "linecode": ["LOOM001"], "productcode": ["SKU001"],
			"start": ["2026-11-06 08:30:00.123456"], "end": ["2026-11-06 09:00:00"],
			"actual": ["1453.74"], "scrap": ["0.00"], "operator_count": ["2.50"],
			"unit_of_measure_code": ["M"], "comment": ["Shift A & B"],
			"product_autodetect": ["false"], "continue_current_build_sequence": ["true"],
		})
		self.assertEqual(mock_open.call_args.kwargs, {"timeout": 10})

	@patch("common.l2l_api.urlopen")
	def test_get_external_id_and_autodetect(self, mock_open):
		mock_open.return_value = io.BytesIO(b'{"success": true, "data": {}}')
		self.record(linecode=None, line_externalid="ext-1", productcode=None, product_autodetect=True, method="get")
		params = parse_qs(urlsplit(mock_open.call_args.args[0]).query)
		self.assertEqual(params["site"], ["acx-site"])
		self.assertEqual(params["line_externalid"], ["ext-1"])
		self.assertEqual(params["product_autodetect"], ["true"])
		for name in ("linecode", "productcode", "actual", "scrap", "operator_count"):
			self.assertNotIn(name, params)

	@patch("common.l2l_api.urlopen")
	def test_invalid_inputs_never_send_request(self, mock_open):
		for params in [
			{"start": "2026-11-06 08:30"}, {"start": None},
			{"end": "2026-11-06 08:30:00"}, {"end": "2026-11-06 08:00:00"},
			{"linecode": None}, {"linecode": " "}, {"line_externalid": 123},
			{"productcode": None}, {"productcode": ""}, {"product_autodetect": "false"},
			{"continue_current_build_sequence": "true"}, {"unit_of_measure_code": ""},
			{"actual": "1.234"}, {"scrap": "NaN"}, {"operator_count": "Infinity"},
			{"actual": True}, {"comment": 123}, {"method": "DELETE"}, {"site": "other"},
		]:
			with self.subTest(params=params):
				with self.assertRaises(ValueError):
					self.record(**params)
		mock_open.assert_not_called()

	@patch("common.l2l_api.urlopen")
	def test_transport_errors_are_not_retried_or_exposed(self, mock_open):
		for error in [
			HTTPError("https://example.test/?auth=test-secret", 403, "test-secret", {}, None),
			URLError("test-secret"), TimeoutError("test-secret"),
		]:
			with self.subTest(error=type(error).__name__):
				mock_open.reset_mock()
				mock_open.side_effect = error
				with self.assertRaises(L2LAPIError) as caught:
					self.record()
				self.assertNotIn("test-secret", str(caught.exception))
				mock_open.assert_called_once()

	@patch("common.l2l_api.urlopen")
	def test_invalid_responses(self, mock_open):
		for body in (b"not json", b"[]", b'{"success": false, "error": "test-secret"}'):
			with self.subTest(body=body):
				mock_open.return_value = io.BytesIO(body)
				with self.assertRaises(L2LAPIError) as caught:
					self.record()
				self.assertNotIn("test-secret", str(caught.exception))

	@override_settings(L2L_SITE_CNX="")
	@patch("common.l2l_api.urlopen")
	def test_missing_site_configuration(self, mock_open):
		with self.assertRaises(L2LAPIError):
			self.record(site="CNX")
		mock_open.assert_not_called()
