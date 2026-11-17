import logging
import json
from io import BytesIO

from django.shortcuts import render
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from django.db import DatabaseError
from django.http import HttpResponse, JsonResponse, QueryDict
from django.utils import timezone
from django.views.decorators.http import require_GET, require_POST

from openpyxl import Workbook
from openpyxl.cell import WriteOnlyCell
from openpyxl.styles import Alignment, Font, PatternFill

from .services import get_dispatch_details, get_dispatch_filter_options, get_dispatch_summary


logger = logging.getLogger(__name__)


def _dispatch_query_parameters(params):
	sites = list(dict.fromkeys(params.getlist('site', ['ACX'])))
	if not sites or any(site not in ('ACX', 'CNX') for site in sites):
		raise ValueError('select at least one valid site: ACX or CNX')
	start_value = params.get('start', '')
	end_value = params.get('end', '')
	start = datetime.strptime(start_value, '%Y-%m-%d' if len(start_value) == 10 else '%Y-%m-%dT%H:%M')
	end = datetime.strptime(end_value, '%Y-%m-%d' if len(end_value) == 10 else '%Y-%m-%dT%H:%M')
	if start > end:
		raise ValueError('start must not be later than end')
	local_zone = ZoneInfo('Asia/Shanghai')
	return {
		'start': start.replace(tzinfo=local_zone),
		'end': (end + (timedelta(days=1) if len(end_value) == 10 else timedelta(minutes=1))).replace(tzinfo=local_zone),
		'site': sites, 'areas': params.getlist('area'),
		'technicians': params.getlist('technician'), 'dispatchtypes': params.getlist('dispatchtype'),
	}


@require_POST
def dispatch_export(request):
	try:
		payload = json.loads(request.body)
		if not isinstance(payload['query'], str):
			raise ValueError('Invalid export query')
		parameters = _dispatch_query_parameters(QueryDict(payload['query']))
	except (KeyError, TypeError, ValueError, OverflowError):
		return JsonResponse({'success': False, 'error': '导出数据无效，请重新查询后导出。'}, status=400)
	try:
		rows = get_dispatch_details(**parameters)
	except DatabaseError:
		logger.exception('Unable to export dispatch details from Snowflake')
		return JsonResponse({'success': False, 'error': 'Snowflake 明细读取失败，请稍后重试。'}, status=502)
	if len(rows) > 1048575:
		return JsonResponse({'success': False, 'error': '明细超过 Excel 单表行数上限，请缩小查询范围。'}, status=400)
	workbook = Workbook(write_only=True)
	worksheet = workbook.create_sheet('Dispatch明细')
	worksheet.freeze_panes = 'A2'
	for column, width in (('A', 12), ('B', 16), ('C', 28), ('D', 42), ('E', 80)):
		worksheet.column_dimensions[column].width = width
	headers = []
	for title in ('工厂', '时间', '区域', 'Dispatch类型', '描述'):
		cell = WriteOnlyCell(worksheet, value=title)
		cell.font = Font(bold=True, color='FFFFFF')
		cell.fill = PatternFill('solid', fgColor='237A57')
		headers.append(cell)
	worksheet.append(headers)
	for row in rows:
		cells = []
		for key in ('factory', 'reported', 'area', 'type', 'description'):
			value = row[key]
			if key == 'reported' and isinstance(value, str):
				value = datetime.fromisoformat(value)
			if key == 'reported' and isinstance(value, datetime):
				value = value.date()
			cell = WriteOnlyCell(worksheet, value=value)
			cell.alignment = Alignment(vertical='top', wrap_text=key in ('type', 'description'))
			if isinstance(value, str):
				cell.data_type = 's'
			if key == 'reported':
				cell.number_format = 'yyyy-mm-dd'
			cells.append(cell)
		worksheet.append(cells)
	worksheet.auto_filter.ref = 'A1:E%s' % (len(rows) + 1)
	output = BytesIO()
	workbook.save(output)
	response = HttpResponse(output.getvalue(),
		content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
	response['Content-Disposition'] = 'attachment; filename="Dispatch.xlsx"'
	response['Cache-Control'] = 'no-store'
	return response


def dispatch(request):
	today = timezone.localdate(timezone=ZoneInfo('Asia/Shanghai'))
	return render(request, 'dispatch/dispatch.html', {
		'date_from': today.replace(day=1).isoformat() + 'T00:00', 'date_to': today.isoformat() + 'T23:59',
	})


@require_GET
def dispatch_options(request):
	try:
		options = get_dispatch_filter_options()
	except DatabaseError:
		logger.exception('Unable to load dispatch filter options from Snowflake')
		response = JsonResponse({'success': False, 'error': '筛选选项加载失败，请重新打开下拉框重试。'}, status=502)
	else:
		response = JsonResponse({'success': True, 'options': options})
	response['Cache-Control'] = 'no-store'
	return response


@require_GET
def dispatch_details(request):
	try:
		parameters = _dispatch_query_parameters(request.GET)
		page = int(request.GET.get('page', '1'))
		if page < 1 or page > 1000000:
			raise ValueError('Invalid page')
	except (ValueError, OverflowError):
		return JsonResponse({'success': False, 'error': '请选择有效筛选条件和页码。'}, status=400)
	try:
		rows = get_dispatch_details(**parameters, limit=51, offset=(page - 1) * 50)
	except DatabaseError:
		logger.exception('Unable to load dispatch details from Snowflake')
		response = JsonResponse({'success': False, 'error': '记录读取失败，请重试。'}, status=502)
	else:
		response = JsonResponse({'success': True, 'records': rows[:50],
			'page': page, 'page_size': 50, 'has_next': len(rows) > 50})
	response['Cache-Control'] = 'no-store'
	return response


@require_GET
def dispatch_data(request):
	try:
		parameters = _dispatch_query_parameters(request.GET)
	except (ValueError, OverflowError):
		return JsonResponse({'success': False, 'error': '请选择有效站点和起止日期，开始日期不能晚于结束日期。'}, status=400)
	try:
		data = get_dispatch_summary(parameters.pop('start'), parameters.pop('end'), **parameters)
	except DatabaseError:
		logger.exception('Unable to load dispatch summary from Snowflake')
		response = JsonResponse({'success': False, 'error': 'Snowflake 数据读取失败，请稍后重试。'}, status=502)
		response['Cache-Control'] = 'no-store'
		return response
	response = JsonResponse({'success': True, **data})
	response['Cache-Control'] = 'no-store'
	return response
