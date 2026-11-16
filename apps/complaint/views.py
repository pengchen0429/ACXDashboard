import csv
import json
import logging
import re
import uuid
import warnings
from io import StringIO
from pathlib import Path
from tempfile import SpooledTemporaryFile
from zipfile import ZIP_DEFLATED, ZipFile

from PIL import Image

from django import forms
from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.core.files.storage import FileSystemStorage
from django.db import DatabaseError, IntegrityError, transaction
from django.http import FileResponse, Http404, JsonResponse
from django.shortcuts import get_object_or_404
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_http_methods

from .models import ComplaintList


logger = logging.getLogger(__name__)
IMAGE_FORMATS = {'JPEG': ('jpg', 'image/jpeg'), 'PNG': ('png', 'image/png'), 'GIF': ('gif', 'image/gif'), 'WEBP': ('webp', 'image/webp')}
MAX_IMAGE_BYTES = 10 * 1024 * 1024
MAX_IMAGE_PIXELS = 20_000_000
MAX_IMAGE_COUNT = 10
MAX_EXPORT_BYTES = 200 * 1024 * 1024
EXPORT_COLUMNS = (
	('no', '编号'), ('area', '区域'), ('date', '时间'), ('customer', '客户'),
	('complaint_type', '投诉等级'), ('webbing_type', '带型'), ('complaint', '投诉点'),
	('classification', '分类'), ('defect_pictures', '投诉图片'), ('root_cause', '根本原因'),
	('corrective_action', '纠正措施'), ('res', '责任人'), ('completion_time', '完成时间'),
	('state', '状态'), ('remark', '备注'),
)


def complaint_image_storage():
	return FileSystemStorage(location=settings.COMPLAINT_IMAGE_ROOT)


class ComplaintForm(forms.ModelForm):
	no = forms.IntegerField(label='编号', min_value=1, max_value=9223372036854775807, error_messages={'required': '请输入编号', 'invalid': '编号必须是整数'})
	area = forms.ChoiceField(label='区域', required=False, choices=[('', '请选择')] + [(value, value) for value in ('织造', '染色', '整理')])
	complaint_type = forms.ChoiceField(label='投诉等级', required=False, choices=[('', '请选择')] + [(value, value) for value in ('A', 'B', 'C')])
	classification = forms.ChoiceField(label='分类', required=False, choices=[('', '请选择')] + [(value, value) for value in ('织造不良', '拉带不良', '染色不良', '整理不良')])

	class Meta:
		model = ComplaintList
		exclude = ['no']


def serialize_complaint(record):
	data = {}
	for field in record._meta.local_fields:
		value = getattr(record, field.name)
		if field.primary_key:
			value = str(value)
		elif field.get_internal_type() == 'DateTimeField' and value is not None:
			if timezone.is_aware(value):
				value = timezone.localtime(value)
			value = value.isoformat()
		data[field.name] = value
	return data


def save_complaint(request, instance=None):
	try:
		data = json.loads(request.body)
	except (ValueError, UnicodeDecodeError):
		return JsonResponse({'error': '请求数据不是有效的 JSON'}, status=400)
	if not isinstance(data, dict):
		return JsonResponse({'error': '请求数据必须是对象'}, status=400)
	if instance is not None and 'no' not in data:
		data['no'] = instance.no
	form = ComplaintForm(data=data, instance=instance)
	if not form.is_valid():
		return JsonResponse({'error': '请检查填写内容', 'fields': form.errors.get_json_data()}, status=400)
	if instance is not None and form.cleaned_data['no'] != instance.no:
		form.add_error('no', '已保存记录的编号不可修改')
	elif instance is None and ComplaintList.objects.filter(pk=form.cleaned_data['no']).exists():
		form.add_error('no', '编号已存在，请使用其他编号')
	if form.errors:
		return JsonResponse({'error': '请检查填写内容', 'fields': form.errors.get_json_data()}, status=400)
	record = form.save(commit=False)
	record.no = form.cleaned_data['no']
	try:
		with transaction.atomic():
			record.save(force_insert=instance is None)
	except IntegrityError:
		return JsonResponse({'error': '编号重复或记录不符合数据库约束，请检查编号后重试'}, status=400)
	return JsonResponse({'record': serialize_complaint(record)}, status=200 if instance else 201)


@never_cache
@login_required(login_url='login')
@require_http_methods(['GET', 'POST'])
def complaint_records(request):
	try:
		if request.method == 'POST':
			if not request.user.has_perm('complaint.add_complaintlist'):
				return JsonResponse({'error': '没有新增客户投诉的权限'}, status=403)
			return save_complaint(request)
		return JsonResponse({
			'records': [serialize_complaint(record) for record in ComplaintList.objects.order_by('-date', '-no')],
			'permissions': {
				'add': request.user.has_perm('complaint.add_complaintlist'),
				'change': request.user.has_perm('complaint.change_complaintlist'),
				'delete': request.user.has_perm('complaint.delete_complaintlist'),
			},
		})
	except DatabaseError:
		logger.exception('Complaint database operation failed')
		return JsonResponse({'error': '投诉数据暂时无法访问，请稍后重试'}, status=503)


@never_cache
@login_required(login_url='login')
@require_http_methods(['GET', 'PUT', 'DELETE'])
def complaint_record(request, no):
	permission = {'PUT': 'change', 'DELETE': 'delete'}.get(request.method)
	if permission and not request.user.has_perm('complaint.' + permission + '_complaintlist'):
		return JsonResponse({'error': '没有操作客户投诉的权限'}, status=403)
	try:
		record = get_object_or_404(ComplaintList, no=no)
		if request.method == 'PUT':
			return save_complaint(request, instance=record)
		if request.method == 'DELETE':
			record.delete()
			return JsonResponse({'deleted': str(no)})
		return JsonResponse({'record': serialize_complaint(record)})
	except DatabaseError:
		logger.exception('Complaint database operation failed')
		return JsonResponse({'error': '投诉数据暂时无法访问，请稍后重试'}, status=503)


@never_cache
@login_required(login_url='login')
@require_http_methods(['POST'])
def complaint_images(request):
	if not (request.user.has_perm('complaint.add_complaintlist') or request.user.has_perm('complaint.change_complaintlist')):
		return JsonResponse({'error': '没有上传客户投诉图片的权限'}, status=403)
	files = request.FILES.getlist('images')
	if not files or len(files) > MAX_IMAGE_COUNT:
		return JsonResponse({'error': '每次请选择 1 至 10 张图片'}, status=400)
	validated = []
	for upload in files:
		if upload.size > MAX_IMAGE_BYTES:
			return JsonResponse({'error': '每张图片不能超过 10MB'}, status=400)
		try:
			with warnings.catch_warnings():
				warnings.simplefilter('error', Image.DecompressionBombWarning)
				with Image.open(upload) as image:
					if image.format not in IMAGE_FORMATS:
						return JsonResponse({'error': '文件“' + upload.name + '”的实际格式为 ' + str(image.format) + '，不是 JPG、PNG、GIF、WebP；仅修改扩展名无效'}, status=400)
					if image.width * image.height > MAX_IMAGE_PIXELS:
						return JsonResponse({'error': '图片不能超过 2000 万像素'}, status=400)
					extension = IMAGE_FORMATS[image.format][0]
					image.verify()
			upload.seek(0)
			validated.append((upload, extension))
		except (OSError, ValueError, Image.DecompressionBombError, Image.DecompressionBombWarning):
			return JsonResponse({'error': '图片内容无效或文件已损坏'}, status=400)
	storage = complaint_image_storage()
	saved = []
	try:
		for upload, extension in validated:
			name = storage.save(uuid.uuid4().hex + '.' + extension, upload)
			saved.append(name)
	except OSError:
		logger.exception('Complaint image upload failed')
		for name in saved:
			try:
				storage.delete(name)
			except OSError:
				logger.exception('Complaint image cleanup failed')
		return JsonResponse({'error': '图片格式校验已通过，但无法写入图片保存目录，请确认服务器目标磁盘存在且服务账号有写入权限'}, status=503)
	return JsonResponse({'images': [{'path': storage.path(name), 'url': reverse('complaint-image', args=[name])} for name in saved]}, status=201)


@never_cache
@login_required(login_url='login')
@require_http_methods(['GET'])
def complaint_image(request, name):
	if not re.fullmatch(r'[0-9a-f]{32}\.(jpg|png|gif|webp)', name):
		raise Http404
	storage = complaint_image_storage()
	try:
		image_file = storage.open(name, 'rb')
	except FileNotFoundError:
		raise Http404
	extension = name.rsplit('.', 1)[1]
	content_type = next(value[1] for value in IMAGE_FORMATS.values() if value[0] == extension)
	response = FileResponse(image_file, content_type=content_type)
	response['X-Content-Type-Options'] = 'nosniff'
	return response


@never_cache
@login_required(login_url='login')
@require_http_methods(['POST'])
def complaint_export(request):
	try:
		data = json.loads(request.body)
	except (ValueError, UnicodeDecodeError):
		return JsonResponse({'error': '导出数据不是有效的 JSON'}, status=400)
	records = data.get('records') if isinstance(data, dict) else None
	if not isinstance(records, list) or not records or len(records) > 10000:
		return JsonResponse({'error': '每次请导出 1 至 10000 条投诉记录'}, status=400)
	archive = SpooledTemporaryFile(max_size=10 * 1024 * 1024)
	try:
		storage = complaint_image_storage()
		root = Path(storage.location).resolve()
		images = {}
		total_bytes = 0
		output = StringIO(newline='')
		writer = csv.writer(output)
		writer.writerow([label for key, label in EXPORT_COLUMNS])
		for record in records:
			if not isinstance(record, dict):
				raise ValueError('导出记录格式不正确')
			row = []
			for key, label in EXPORT_COLUMNS:
				value = record.get(key)
				if not isinstance(value, (str, int, float, bool, type(None))):
					raise ValueError('导出字段格式不正确')
				value = '' if value is None else str(value)
				if key == 'defect_pictures':
					references = []
					for reference in value.splitlines():
						reference = reference.strip()
						if not reference:
							continue
						match = re.fullmatch(re.escape(reverse('complaint-images')) + r'([0-9a-f]{32}\.(?:jpg|png|gif|webp))/', reference)
						if match:
							image_path = Path(storage.path(match.group(1))).resolve()
						else:
							image_path = Path(reference)
							if not image_path.is_absolute():
								raise ValueError('部分图片不在投诉图片目录内，无法打包')
							image_path = image_path.resolve()
						if image_path.parent != root or not re.fullmatch(r'[0-9a-f]{32}\.(jpg|png|gif|webp)', image_path.name):
							raise ValueError('部分图片不在投诉图片目录内，无法打包')
						name = 'images/' + image_path.name
						if name not in images:
							total_bytes += image_path.stat().st_size
							if total_bytes > MAX_EXPORT_BYTES:
								raise ValueError('导出图片总大小不能超过 200MB，请缩小查询范围')
							images[name] = image_path
						references.append(name)
					value = '\n'.join(references)
				if re.match(r'^\s*[=+\-@]|^[\t\r\n]', value):
					value = "'" + value
				row.append(value)
			writer.writerow(row)
		with ZipFile(archive, 'w', compression=ZIP_DEFLATED) as bundle:
			bundle.writestr('complaints.csv', output.getvalue().encode('utf-8-sig'))
			for name, image_path in images.items():
				bundle.write(image_path, name)
		archive.seek(0)
		response = FileResponse(archive, content_type='application/zip', as_attachment=True, filename='complaints_' + timezone.localdate().isoformat() + '.zip')
		response['X-Content-Type-Options'] = 'nosniff'
		return response
	except FileNotFoundError:
		archive.close()
		return JsonResponse({'error': '部分投诉图片文件不存在，无法导出完整图片，请检查图片目录'}, status=400)
	except ValueError as error:
		archive.close()
		return JsonResponse({'error': str(error)}, status=400)
	except OSError:
		archive.close()
		logger.exception('Complaint export failed')
		return JsonResponse({'error': '导出失败，无法读取投诉图片或创建压缩包'}, status=503)
