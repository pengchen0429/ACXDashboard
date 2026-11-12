import json
from datetime import datetime
from decimal import Decimal, InvalidOperation
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from django.conf import settings
from django.utils import timezone


class L2LAPIError(RuntimeError):
	pass

# 获取指定产线在给定时间所属生产周的汇总数据，未指定时间时使用当前本地时间。
def get_weekly_production(
	linecode, date=None, *, show_shifts=False, include_inactive_lines=False, timeout=30
):
	"""查询指定产线在某个时间所属生产周的产量汇总（只读）。

	参数：
		linecode：必填产线代码字符串，多条产线用逗号分隔。
		date：本地时间，格式为 YYYY-MM-DD HH:MM；省略时使用当前本地时间。
		show_shifts：是否要求接口返回班次信息，默认 False。
		include_inactive_lines：是否包含非活跃产线，默认 False。
		timeout：HTTP 请求超时秒数，默认 30。

	先校验产线和时间，再调用周汇总接口；生产周的划分由 L2L 决定，
	并非在本地计算。站点使用默认 ACX 配置，缺失时回退到 L2L_SITE。
	返回字典组成的列表，保留接口原始数值表示，不主动转换数字字符串。
	参数不合法时抛出 ValueError；配置、请求或响应异常时抛出 L2LAPIError。
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
	"""查询指定本地时间区间内的日产量汇总（只读）。

	参数：
		start、end：必填起止时间，格式为 YYYY-MM-DD HH:MM，start 必须早于 end。
		linecode：可选产线代码筛选，多条用逗号分隔。
		line_externalid：可选产线外部标识筛选，多条用逗号分隔。
		line_id：可选 L2L 产线 ID 筛选，仍需传入字符串，多条用逗号分隔。
		timeout：HTTP 请求超时秒数，默认 30。
		site：站点名称 ACX 或 CNX；省略时优先使用 ACX 配置。

	校验时间和筛选参数后调用日汇总接口；不传任何产线筛选时，
	查询所选站点下有权访问的全部产线。统计日期和区间边界解释由 L2L 决定。
	返回字典组成的列表，保留接口原始数值表示，不主动转换数字字符串。
	参数不合法时抛出 ValueError；配置、请求或响应异常时抛出 L2LAPIError。
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


def record_pitch_details(
	start, end, linecode=None, *, line_externalid=None, productcode=None,
	product_autodetect=False, actual=None, scrap=None, operator_count=None,
	unit_of_measure_code=None, comment=None, continue_current_build_sequence=False,
	site=None, timeout=30, method="POST",
):
	"""向 L2L 写入指定生产时段的明细，不是查询接口。

	参数：
		start、end：必填本地起止时间，格式为 YYYY-MM-DD HH:MM:SS，
			可附加小数秒（最多 6 位）；start 必须早于 end。
		linecode、line_externalid：产线代码或外部标识，至少提供一个非空字符串。
		productcode：产品代码；未启用产品自动识别时必填。
		product_autodetect：是否由 L2L 自动识别产品，必须为布尔值，默认 False。
		actual：实际产量，可选。
		scrap：报废数量，可选。
		operator_count：操作人员数量，可选。
		unit_of_measure_code：计量单位代码，可选非空字符串。
		comment：备注，可选字符串，允许空字符串。
		continue_current_build_sequence：是否继续当前生产序列，
			必须为布尔值，默认 False。
		site：站点名称 ACX 或 CNX；省略时优先使用 ACX 配置。
		timeout：HTTP 请求超时秒数，默认 30。
		method：GET 或 POST，不区分大小写，默认 POST。

	校验参数后调用 pitchdetails/record_details。actual、scrap 和
	operator_count 必须是有限数值，数值精度最多两位小数，发送时统一保留两位。
	返回完整的 JSON 响应字典，不只提取 data 字段。
	参数不合法时抛出 ValueError；配置、请求或响应异常时抛出 L2LAPIError。

	注意：即使使用 GET，也会修改 L2L 数据。函数不会自动重试；
	报错或超时并不代表写入失败，重试前应确认是否已写入，避免重复记录。
	"""
	if not isinstance(method, str) or method.upper() not in ("GET", "POST"):
		raise ValueError("method must be GET or POST")
	params = {}
	parsed_times = []
	for name, value in (("start", start), ("end", end)):
		for date_format in ("%Y-%m-%d %H:%M:%S.%f", "%Y-%m-%d %H:%M:%S"):
			try:
				parsed = datetime.strptime(value, date_format)
			except (TypeError, ValueError):
				continue
			params[name] = parsed.strftime(date_format)
			parsed_times.append(parsed)
			break
		else:
			raise ValueError("%s must use YYYY-MM-DD HH:MM:SS[.ffffff] format" % name)
	if parsed_times[0] >= parsed_times[1]:
		raise ValueError("start must be earlier than end")
	for name, value in (
		("linecode", linecode), ("line_externalid", line_externalid),
		("productcode", productcode), ("unit_of_measure_code", unit_of_measure_code),
	):
		if value is not None:
			if not isinstance(value, str) or not value.strip():
				raise ValueError("%s must be a non-empty string" % name)
			params[name] = value.strip()
	if linecode is None and line_externalid is None:
		raise ValueError("linecode or line_externalid is required")
	for name, value in (
		("product_autodetect", product_autodetect),
		("continue_current_build_sequence", continue_current_build_sequence),
	):
		if not isinstance(value, bool):
			raise ValueError("%s must be a boolean" % name)
		params[name] = str(value).lower()
	if productcode is None and not product_autodetect:
		raise ValueError("productcode is required unless product_autodetect is True")
	for name, value in (("actual", actual), ("scrap", scrap), ("operator_count", operator_count)):
		if value is not None:
			try:
				number = Decimal(str(value))
				if not number.is_finite() or number != number.quantize(Decimal("0.01")):
					raise ValueError
			except (InvalidOperation, ValueError):
				raise ValueError("%s must be a finite decimal with at most two decimal places" % name) from None
			params[name] = format(number, ".2f")
	if comment is not None:
		if not isinstance(comment, str):
			raise ValueError("comment must be a string")
		params["comment"] = comment
	return _request_l2l("pitchdetails/record_details", params, timeout, site=site, method=method.upper())


def get_dispatch_event_data(
	lastupdated=None, *, dispatch_id=None, dispatch_number=None, limit=1000,
	areacode=None, line_ids=None, dispatchtype_ids=None, externalid=None,
	externalid_prefix=None, externalid__isnull=None, open=None, deleted=None,
	reversed=None, site=None, timeout=30,
):
	"""只读查询 L2L Dispatch 记录，返回完整 JSON 响应字典。

	参数：
		lastupdated：UTC 更新时间下限，格式为 YYYY-MM-DD HH:MM:SS。
			不传 dispatch_id 或 dispatch_number 时必填，不转换本地时区。
		dispatch_id、dispatch_number：按内部 ID 或记录编号查询单条记录，
			可传整数或非空字符串。
		limit：单次最多返回的记录数，整数 1 至 1000，默认 1000。
		areacode：区域代码，可选非空字符串。
		line_ids、dispatchtype_ids：产线 ID、Dispatch 类型 ID 筛选，
			可选非空字符串，多个 ID 用逗号分隔。
		externalid、externalid_prefix：外部标识精确值或前缀，可选非空字符串。
		externalid__isnull：True 筛选空外部标识，False 筛选非空值；
			省略时不筛选，必须为布尔值。
		open：1/True 筛选未关闭记录，0/False 筛选已关闭记录。
		deleted：1/True 筛选已删除记录，0/False 筛选未删除记录。
		reversed：1/True 按 lastupdated 降序，0/False 按升序。
			上述三个参数省略时不发送，使用接口默认行为。
		site：ACX 或 CNX，省略时优先使用 ACX 配置。
		timeout：HTTP 请求超时秒数，默认 30。

	调用 dispatches/get_event_data，仅使用 JSON，不支持 format=xml。
	返回完整响应以保留接口提供的同步元数据，不假设 data 的结构。
	参数不合法时抛出 ValueError；配置、请求或响应异常时抛出 L2LAPIError。

	增量同步必须保持站点和筛选参数组合一致，不能跨组合复用同步时间。
	接口按 lastupdated >= 下限查询，可能重复返回记录，调用方需自行去重。
	本函数只查询一批，不自动分页，也不会自动推进同步时间。
	"""
	if lastupdated is None and dispatch_id is None and dispatch_number is None:
		raise ValueError("lastupdated is required unless dispatch_id or dispatch_number is provided")
	params = {}
	if lastupdated is not None:
		try:
			parsed = datetime.strptime(lastupdated, "%Y-%m-%d %H:%M:%S")
			if parsed.strftime("%Y-%m-%d %H:%M:%S") != lastupdated:
				raise ValueError
		except (TypeError, ValueError):
			raise ValueError("lastupdated must use UTC YYYY-MM-DD HH:MM:SS format") from None
		params["lastupdated"] = lastupdated
	if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 1000:
		raise ValueError("limit must be an integer between 1 and 1000")
	params["limit"] = limit
	for name, value in (("dispatch_id", dispatch_id), ("dispatch_number", dispatch_number)):
		if value is not None:
			if isinstance(value, bool) or not isinstance(value, (str, int)) or not str(value).strip():
				raise ValueError("%s must be an integer or non-empty string" % name)
			params[name] = str(value).strip()
	for name, value in (
		("areacode", areacode), ("line_ids", line_ids), ("dispatchtype_ids", dispatchtype_ids),
		("externalid", externalid), ("externalid_prefix", externalid_prefix),
	):
		if value is not None:
			if not isinstance(value, str) or not value.strip():
				raise ValueError("%s must be a non-empty string" % name)
			params[name] = value.strip()
	if externalid__isnull is not None:
		if not isinstance(externalid__isnull, bool):
			raise ValueError("externalid__isnull must be a boolean")
		params["externalid__isnull"] = str(externalid__isnull).lower()
	for name, value in (("open", open), ("deleted", deleted), ("reversed", reversed)):
		if value is not None:
			if not isinstance(value, (bool, int)) or value not in (0, 1):
				raise ValueError("%s must be a boolean or integer 0 or 1" % name)
			params[name] = int(value)
	return _request_l2l("dispatches/get_event_data", params, timeout, site=site)


def _get_production_summary(endpoint, params, timeout, *, site=None):
	"""内部辅助函数：调用生产汇总接口并提取、校验 data 列表。

	endpoint 是汇总接口名称（不含 reporting/production/ 前缀）；
	params 是业务参数字典，timeout 是超时秒数，site 是可选 ACX/CNX 站点。
	本函数补全接口路径，再由 _request_l2l 负责认证、发送请求和基础响应校验。
	返回响应中的 data，要求它是列表且每一项都是字典，允许空列表。
	data 缺失或结构不符合要求时抛出 L2LAPIError；底层请求异常继续向外传递。
	"""
	payload = _request_l2l("reporting/production/" + endpoint, params, timeout, site=site)
	rows = payload.get("data")
	if not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows):
		raise L2LAPIError("L2L returned an unexpected data format")
	return rows


def _request_l2l(endpoint, params, timeout, *, site=None, method="GET"):
	"""内部辅助函数：统一读取 L2L 配置、发送 HTTP 请求并校验 JSON 响应。

	参数：
		endpoint：相对于 L2L_BASE_URL 的接口路径。
		params：业务参数字典；发送前复制并补入配置中的真实站点标识。
		timeout：HTTP 请求超时秒数。
		site：ACX 或 CNX，分别读取 L2L_SITE_ACX 或 L2L_SITE_CNX；
			省略时优先读取 L2L_SITE_ACX，再回退到 L2L_SITE。
		method：内部调用约定为大写 GET 或 POST，默认 GET；
			仅等于 POST 时发送表单请求，否则按 GET 发送。

	读取 L2L_BASE_URL 和 L2L_AUTH，拼接地址并编码参数。
	POST 将认证放在 URL、其余参数放在 UTF-8 表单请求体；
	GET 将全部参数（含认证和站点）放在 URL 查询字符串。
	返回完整响应字典，要求 success 字段严格为 True；本函数不校验 data。
	不支持的站点名称抛出 ValueError；缺少配置、HTTP 错误、网络错误、
	超时、无效 JSON 或接口返回失败时抛出 L2LAPIError，不自动重试。
	"""
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

	params = {**params, "site": site}
	url = base_url.rstrip("/") + "/" + endpoint + "/?"
	if method == "POST":
		request = Request(
			url + urlencode({"auth": auth}), data=urlencode(params).encode("utf-8"),
			headers={"Content-Type": "application/x-www-form-urlencoded; charset=utf-8"},
			method="POST",
		)
	else:
		request = url + urlencode({**params, "auth": auth})
	try:
		with urlopen(request, timeout=timeout) as response:
			payload = json.load(response)
	except HTTPError as error:
		raise L2LAPIError("L2L request failed (HTTP %s)" % error.code) from None
	except (URLError, OSError):
		raise L2LAPIError("L2L request failed or timed out") from None
	except (ValueError, UnicodeError):
		raise L2LAPIError("L2L returned invalid JSON") from None

	if not isinstance(payload, dict) or payload.get("success") is not True:
		raise L2LAPIError("L2L reported an unsuccessful response")
	return payload
