import json
from datetime import datetime
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import urlopen

from django.conf import settings
from django.utils import timezone


class L2LAPIError(RuntimeError):
	pass

# 获取指定产线在给定时间所属生产周的汇总数据，未指定时间时使用当前本地时间。
def get_weekly_production(
	linecode, date=None, *, show_shifts=False, include_inactive_lines=False, timeout=30
):
	"""Return weekly summary rows for comma-separated line codes.

	date is a local time string in YYYY-MM-DD HH:MM format, defaulting to now.
	The API decides the production week containing that time. Numeric values
	retain the API's original string representation.
	"""
	if not isinstance(linecode, str) or not linecode.strip():
		raise ValueError("linecode must be a non-empty string")
	if date is None:
		current_time = timezone.now()
		if timezone.is_aware(current_time):
			current_time = timezone.localtime(current_time)
		date = current_time.strftime("%Y-%m-%d %H:%M")
	try:
		date = datetime.strptime(date, "%Y-%m-%d %H:%M").strftime("%Y-%m-%d %H:%M")
	except (TypeError, ValueError):
		raise ValueError("date must use YYYY-MM-DD HH:MM format") from None

	params = {
		"date": date,
		"linecode": linecode.strip(),
		"show_shifts": str(bool(show_shifts)).lower(),
		"include_inactive_lines": str(bool(include_inactive_lines)).lower(),
	}
	return _get_production_summary("weekly_summary_data_by_line", params, timeout)


# 获取指定起止时间内的日产量汇总，可按产线代码、外部标识或 ID 筛选。
def get_daily_production(
	start, end, linecode=None, *, line_externalid=None, line_id=None, timeout=30, site=None
):
	"""Return daily summary rows within an explicit local reporting interval.

	start and end use YYYY-MM-DD HH:MM format. Optional line filters are
	comma-separated strings; omit all filters to query all accessible lines.
	Numeric values retain the API's original string representation.
	site selects ACX or CNX; omitted site defaults to the ACX configuration.
	"""
	try:
		start_time = datetime.strptime(start, "%Y-%m-%d %H:%M")
		end_time = datetime.strptime(end, "%Y-%m-%d %H:%M")
	except (TypeError, ValueError):
		raise ValueError("start and end must use YYYY-MM-DD HH:MM format") from None
	if start_time >= end_time:
		raise ValueError("start must be earlier than end")

	params = {
		"start": start_time.strftime("%Y-%m-%d %H:%M"),
		"end": end_time.strftime("%Y-%m-%d %H:%M"),
	}
	for name, value in (
		("linecode", linecode), ("line_externalid", line_externalid), ("line_id", line_id)
	):
		if value is not None:
			if not isinstance(value, str) or not value.strip():
				raise ValueError("%s must be a non-empty comma-separated string" % name)
			params[name] = value.strip()
	return _get_production_summary("daily_summary_data_by_line", params, timeout, site=site)


# 读取认证和站点配置，发送生产汇总请求，校验响应并统一处理接口异常。
def _get_production_summary(endpoint, params, timeout, *, site=None):
	base_url = getattr(settings, "L2L_BASE_URL", None)
	auth = getattr(settings, "L2L_AUTH", None)
	if site is None:
		site = getattr(settings, "L2L_SITE_ACX", None) or getattr(settings, "L2L_SITE", None)
	elif site in ("ACX", "CNX"):
		site = getattr(settings, "L2L_SITE_" + site, None)
	else:
		raise ValueError("site must be ACX or CNX")
	if not all((base_url, auth, site)):
		raise L2LAPIError("L2L base URL, authentication and requested site must be configured")

	params = {**params, "auth": auth, "site": site}
	url = (
		base_url.rstrip("/")
		+ "/reporting/production/" + endpoint + "/?"
		+ urlencode(params)
	)
	try:
		with urlopen(url, timeout=timeout) as response:
			payload = json.load(response)
	except HTTPError as error:
		raise L2LAPIError("L2L request failed (HTTP %s)" % error.code) from None
	except (URLError, OSError):
		raise L2LAPIError("L2L request failed or timed out") from None
	except (ValueError, UnicodeError):
		raise L2LAPIError("L2L returned invalid JSON") from None

	if not isinstance(payload, dict) or payload.get("success") is not True:
		raise L2LAPIError("L2L reported an unsuccessful response")
	rows = payload.get("data")
	if not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows):
		raise L2LAPIError("L2L returned an unexpected data format")
	return rows
