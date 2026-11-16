import csv
import json
from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
from zipfile import ZipFile

from PIL import Image

from django.contrib.auth.models import Permission, User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import DatabaseError
from django.template.loader import render_to_string
from django.test import Client, SimpleTestCase, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from .models import ComplaintList


@override_settings(AUTHENTICATION_BACKENDS=['django.contrib.auth.backends.ModelBackend'])
class ComplaintApiTests(TestCase):
	def setUp(self):
		self.reader = User.objects.create_user(username='complaint-reader')
		self.client.force_login(self.reader)

	def test_anonymous_reads_require_login(self):
		self.client.logout()
		for url in (reverse('complaint-records'), reverse('complaint-record', args=[1])):
			with self.subTest(url=url), self.assertNumQueries(0):
				response = self.client.get(url)
				self.assertRedirects(response, reverse('login') + '?next=' + url, fetch_redirect_response=False)

	def test_authenticated_page_and_navigation_are_available_without_write_permissions(self):
		response = self.client.get(reverse('complaint'))
		self.assertEqual(response.status_code, 200)
		self.assertTemplateUsed(response, 'complaint/complaint.html')
		self.assertContains(response, '<a class="nav-item active" href="/complaint/" data-page="complaint" aria-current="page">')
		self.assertIn('no-store', response['Cache-Control'])
		self.assertIn('no-store', self.client.get(reverse('complaint-records'))['Cache-Control'])
		self.assertContains(response, 'data-can-add="false"')

	def test_writer_page_permissions_do_not_load_records(self):
		self.login_writer()
		with patch('apps.complaint.views.ComplaintList.objects.order_by') as records:
			response = self.client.get(reverse('complaint'))
			records.assert_not_called()
		for permission in ('add', 'change', 'delete'):
			self.assertContains(response, 'data-can-' + permission + '="true"')

	def login_writer(self, codenames=None):
		user = User.objects.create_user(username='complaint-writer')
		permissions = Permission.objects.filter(
			content_type__app_label='complaint',
			codename__in=codenames or ['add_complaintlist', 'change_complaintlist', 'delete_complaintlist'],
		)
		user.user_permissions.set(permissions)
		self.client.force_login(user)

	def test_empty_list_has_no_demo_data(self):
		response = self.client.get(reverse('complaint-records'))
		self.assertEqual(response.status_code, 200)
		self.assertEqual(response.json(), {'records': [], 'permissions': {'add': False, 'change': False, 'delete': False}})

	def test_list_returns_all_columns_and_preserves_large_identifiers(self):
		record = ComplaintList.objects.create(no=9007199254740993, area='ACX', date=timezone.now(),
			customer='真实客户', classification='外观', complaint_type='严重', remark='<script>test</script>')
		response = self.client.get(reverse('complaint-records'))
		self.assertEqual(response.status_code, 200)
		data = response.json()['records'][0]
		self.assertEqual(set(data), {field.name for field in ComplaintList._meta.local_fields})
		self.assertEqual(data['no'], str(record.no))
		self.assertEqual(data['customer'], '真实客户')
		self.assertEqual(data['date'], timezone.localtime(record.date).isoformat())
		self.assertIsNone(data['completion_time'])
		self.assertEqual(data['remark'], '<script>test</script>')

	def test_anonymous_mutations_are_rejected(self):
		record = ComplaintList.objects.create(customer='保留记录')
		self.client.logout()
		self.assertEqual(self.client.post(reverse('complaint-records'), '{}', content_type='application/json').status_code, 302)
		url = reverse('complaint-record', args=[record.no])
		self.assertEqual(self.client.put(url, '{}', content_type='application/json').status_code, 302)
		self.assertEqual(self.client.delete(url).status_code, 302)
		record.refresh_from_db()
		self.assertEqual(record.customer, '保留记录')

	def test_authorized_create_update_detail_delete(self):
		self.login_writer()
		payload = {'area': '染色', 'date': '2026-11-16T08:30:00+08:00', 'customer': '数据库客户',
			'complaint_type': 'A', 'webbing_type': 'W-100', 'complaint': '投诉点',
			'classification': '染色不良', 'defect_pictures': '/media/complaints/test.jpg',
			'root_cause': '根本原因', 'corrective_action': '纠正措施', 'res': '测试责任人',
			'completion_time': '2026-11-17T08:30:00+08:00', 'state': '已解决', 'remark': '备注'}
		response = self.client.post(reverse('complaint-records'), json.dumps(payload), content_type='application/json')
		self.assertEqual(response.status_code, 201)
		url = reverse('complaint-record', args=[response.json()['record']['no']])
		self.assertEqual(self.client.get(url).json()['record']['corrective_action'], '纠正措施')
		payload['remark'] = '更新备注'
		response = self.client.put(url, json.dumps(payload), content_type='application/json')
		self.assertEqual(response.status_code, 200)
		self.assertEqual(ComplaintList.objects.get().remark, '更新备注')
		self.assertEqual(self.client.delete(url).status_code, 200)
		self.assertFalse(ComplaintList.objects.exists())

	def test_permission_is_checked_per_operation(self):
		self.login_writer(['add_complaintlist'])
		response = self.client.post(reverse('complaint-records'), '{}', content_type='application/json')
		self.assertEqual(response.status_code, 201)
		url = reverse('complaint-record', args=[response.json()['record']['no']])
		self.assertEqual(self.client.put(url, '{}', content_type='application/json').status_code, 403)
		self.assertEqual(self.client.delete(url).status_code, 403)

	def test_invalid_payloads_do_not_create_records(self):
		self.login_writer()
		for payload in ('{', '[]', json.dumps({'date': 'not-a-date'}), json.dumps({'customer': 'x' * 201}),
						json.dumps({'area': '其他'}), json.dumps({'complaint_type': '严重'}), json.dumps({'classification': '其他'})):
			with self.subTest(payload=payload):
				response = self.client.post(reverse('complaint-records'), payload, content_type='application/json')
				self.assertEqual(response.status_code, 400)
		self.assertFalse(ComplaintList.objects.exists())

	def test_csrf_is_required_for_writes(self):
		self.client = Client(enforce_csrf_checks=True)
		self.login_writer()
		url = reverse('complaint-records')
		self.assertEqual(self.client.post(url, '{}', content_type='application/json').status_code, 403)
		page = self.client.get(reverse('complaint'))
		token = page.cookies['csrftoken'].value
		self.assertEqual(self.client.post(url, '{}', content_type='application/json', HTTP_X_CSRFTOKEN=token).status_code, 201)

	def test_database_failure_does_not_return_demo_data_or_sql_details(self):
		with patch('apps.complaint.views.ComplaintList.objects.order_by', side_effect=DatabaseError('private database details')):
			with patch('apps.complaint.views.logger.exception'):
				response = self.client.get(reverse('complaint-records'))
		self.assertEqual(response.status_code, 503)
		self.assertNotIn('private database details', response.content.decode())

	def image_upload(self):
		buffer = BytesIO()
		Image.new('RGB', (2, 2), 'red').save(buffer, format='PNG')
		return SimpleUploadedFile('local-picture.png', buffer.getvalue(), content_type='image/png')

	def test_images_upload_and_authenticated_access(self):
		self.login_writer()
		with TemporaryDirectory() as directory, self.settings(COMPLAINT_IMAGE_ROOT=directory):
			response = self.client.post(reverse('complaint-images'), {'images': [self.image_upload(), self.image_upload()]})
			self.assertEqual(response.status_code, 201)
			urls = [image['url'] for image in response.json()['images']]
			paths = [image['path'] for image in response.json()['images']]
			self.assertEqual(len(set(urls)), 2)
			self.assertEqual(len(list(Path(directory).iterdir())), 2)
			for path in paths:
				self.assertEqual(Path(path).parent, Path(directory))
				self.assertTrue(Path(path).is_file())
			response = self.client.post(reverse('complaint-records'), json.dumps({'defect_pictures': '\n'.join(paths)}), content_type='application/json')
			self.assertEqual(response.status_code, 201)
			self.assertEqual(ComplaintList.objects.get().defect_pictures, '\n'.join(paths))
			self.client.force_login(self.reader)
			response = self.client.get(urls[0])
			self.assertEqual(response.status_code, 200)
			self.assertEqual(response['Content-Type'], 'image/png')
			self.assertEqual(response['X-Content-Type-Options'], 'nosniff')
			self.assertIn('no-store', response['Cache-Control'])
			self.assertTrue(b''.join(response.streaming_content).startswith(b'\x89PNG'))
			self.client.logout()
			self.assertEqual(self.client.get(urls[0]).status_code, 302)

	def test_jpeg_alias_mime_types_and_real_format_validation(self):
		self.login_writer()
		with TemporaryDirectory() as directory, self.settings(COMPLAINT_IMAGE_ROOT=directory):
			buffer = BytesIO()
			Image.new('RGB', (2, 2), 'red').save(buffer, format='JPEG')
			for filename, content_type in (('photo.jpg', 'image/jpg'), ('photo.JPG', 'application/octet-stream'), ('photo.JpEg', 'image/pjpeg')):
				with self.subTest(filename=filename, content_type=content_type):
					upload = SimpleUploadedFile(filename, buffer.getvalue(), content_type=content_type)
					response = self.client.post(reverse('complaint-images'), {'images': upload})
					self.assertEqual(response.status_code, 201)
					self.assertTrue(response.json()['images'][0]['path'].endswith('.jpg'))
			buffer = BytesIO()
			Image.new('RGB', (2, 2), 'red').save(buffer, format='BMP')
			upload = SimpleUploadedFile('fake.jpg', buffer.getvalue(), content_type='image/jpeg')
			self.assertEqual(self.client.post(reverse('complaint-images'), {'images': upload}).status_code, 400)

	def test_image_validation_prevents_partial_uploads(self):
		self.login_writer()
		with TemporaryDirectory() as directory, self.settings(COMPLAINT_IMAGE_ROOT=directory):
			invalid = SimpleUploadedFile('fake.png', b'not an image', content_type='image/png')
			response = self.client.post(reverse('complaint-images'), {'images': [self.image_upload(), invalid]})
			self.assertEqual(response.status_code, 400)
			large = SimpleUploadedFile('large.png', b'x' * (10 * 1024 * 1024 + 1), content_type='image/png')
			self.assertEqual(self.client.post(reverse('complaint-images'), {'images': large}).status_code, 400)
			with patch('apps.complaint.views.MAX_IMAGE_PIXELS', 1):
				self.assertEqual(self.client.post(reverse('complaint-images'), {'images': self.image_upload()}).status_code, 400)
			self.assertEqual(self.client.post(reverse('complaint-images'), {}).status_code, 400)
			self.assertEqual(self.client.post(reverse('complaint-images'), {'images': [self.image_upload() for index in range(11)]}).status_code, 400)
			self.assertEqual(list(Path(directory).iterdir()), [])

	def test_unavailable_image_directory_returns_error_without_a_fallback(self):
		self.login_writer()
		with patch('apps.complaint.views.FileSystemStorage.save', side_effect=OSError('private storage details')):
			with patch('apps.complaint.views.logger.exception'):
				response = self.client.post(reverse('complaint-images'), {'images': self.image_upload()})
		self.assertEqual(response.status_code, 503)
		self.assertNotIn('private storage details', response.content.decode())

	def test_image_permissions_and_csrf(self):
		url = reverse('complaint-images')
		self.assertEqual(self.client.post(url, {'images': self.image_upload()}).status_code, 403)
		self.client.logout()
		self.assertEqual(self.client.post(url, {'images': self.image_upload()}).status_code, 302)
		self.client = Client(enforce_csrf_checks=True)
		self.login_writer()
		self.assertEqual(self.client.post(url, {'images': self.image_upload()}).status_code, 403)
		token = self.client.get(reverse('complaint')).cookies['csrftoken'].value
		with TemporaryDirectory() as directory, self.settings(COMPLAINT_IMAGE_ROOT=directory):
			self.assertEqual(self.client.post(url, {'images': self.image_upload()}, HTTP_X_CSRFTOKEN=token).status_code, 201)

	def test_image_path_is_restricted(self):
		with TemporaryDirectory() as directory, self.settings(COMPLAINT_IMAGE_ROOT=directory):
			Path(directory, 'secret.txt').write_text('private fixture', encoding='utf-8')
			self.assertEqual(self.client.get(reverse('complaint-image', args=['secret.txt'])).status_code, 404)
			self.assertEqual(self.client.get(reverse('complaint-image', args=['0' * 32 + '.png'])).status_code, 404)

	def test_export_contains_csv_and_corresponding_images(self):
		with TemporaryDirectory() as directory, self.settings(COMPLAINT_IMAGE_ROOT=directory):
			name = 'a' * 32 + '.png'
			image = self.image_upload().read()
			Path(directory, name).write_bytes(image)
			records = [
				{'no': '9007199254740993', 'customer': '=1+1', 'remark': '中文,换行\n备注', 'defect_pictures': str(Path(directory, name))},
				{'no': '2', 'defect_pictures': reverse('complaint-image', args=[name])},
			]
			with patch('apps.complaint.views.ComplaintList.objects.order_by') as query:
				response = self.client.post(reverse('complaint-export'), json.dumps({'records': records}), content_type='application/json')
				query.assert_not_called()
			self.assertEqual(response.status_code, 200)
			self.assertEqual(response['Content-Type'], 'application/zip')
			self.assertIn('no-store', response['Cache-Control'])
			with ZipFile(BytesIO(b''.join(response.streaming_content))) as bundle:
				self.assertEqual(set(bundle.namelist()), {'complaints.csv', 'images/' + name})
				self.assertEqual(bundle.read('images/' + name), image)
				csv_bytes = bundle.read('complaints.csv')
				self.assertTrue(csv_bytes.startswith(b'\xef\xbb\xbf'))
				rows = list(csv.reader(csv_bytes.decode('utf-8-sig').splitlines(keepends=True)))
				self.assertEqual(len(rows[0]), 15)
				self.assertEqual(rows[1][0], '9007199254740993')
				self.assertEqual(rows[1][3], "'=1+1")
				self.assertEqual(rows[1][8], 'images/' + name)
				self.assertEqual(rows[2][8], 'images/' + name)
				self.assertEqual(rows[1][14], '中文,换行\n备注')

	def test_export_rejects_missing_external_and_traversal_images(self):
		with TemporaryDirectory() as directory, self.settings(COMPLAINT_IMAGE_ROOT=directory):
			name = 'a' * 32 + '.png'
			for reference in (str(Path(directory, name)), '../' + name, str(Path(directory).parent / name), '/complaint/images/../secret.txt/', 'https://example.com/image.jpg'):
				with self.subTest(reference=reference):
					response = self.client.post(reverse('complaint-export'), json.dumps({'records': [{'defect_pictures': reference}]}), content_type='application/json')
					self.assertEqual(response.status_code, 400)
			Path(directory, name).write_bytes(self.image_upload().read())
			with patch('apps.complaint.views.MAX_EXPORT_BYTES', 1):
				response = self.client.post(reverse('complaint-export'), json.dumps({'records': [{'defect_pictures': str(Path(directory, name))}]}), content_type='application/json')
				self.assertEqual(response.status_code, 400)

	def test_export_requires_login_csrf_and_valid_records(self):
		url = reverse('complaint-export')
		for payload in ('{', '[]', '{}', '{"records":[]}', '{"records":[null]}', '{"records":[{"customer":{}}]}'):
			self.assertEqual(self.client.post(url, payload, content_type='application/json').status_code, 400)
		self.client.logout()
		self.assertEqual(self.client.post(url, '{}', content_type='application/json').status_code, 302)
		self.client = Client(enforce_csrf_checks=True)
		self.client.force_login(self.reader)
		self.assertEqual(self.client.post(url, '{"records":[{}]}', content_type='application/json').status_code, 403)
		token = self.client.get(reverse('complaint')).cookies['csrftoken'].value
		response = self.client.post(url, '{"records":[{}]}', content_type='application/json', HTTP_X_CSRFTOKEN=token)
		self.assertEqual(response.status_code, 200)
		response.close()


class ComplaintModelTests(TestCase):
	def test_table_and_column_mapping(self):
		self.assertEqual(ComplaintList._meta.db_table, 'complaintlist')
		self.assertEqual(ComplaintList._meta.pk.column, 'No')
		self.assertEqual(
			[field.column for field in ComplaintList._meta.local_fields],
			['No', 'Area', 'Date', 'Customer', 'ComplaintType', 'WebbingType', 'Complaint',
			 'Classification', 'DefectPictures', 'RootCause', 'CorrectiveAction', 'Res',
			 'CompletionTime', 'State', 'Remark'],
		)

	def test_complaint_round_trip(self):
		reported_at = timezone.now()
		complaint = ComplaintList.objects.create(
			area='ACX', date=reported_at, customer='测试客户', complaint_type='严重',
			defect_pictures='/media/complaints/test.jpg', root_cause='根本原因待确认',
		)
		complaint.refresh_from_db()
		self.assertIsNotNone(complaint.no)
		self.assertEqual(complaint.customer, '测试客户')
		self.assertEqual(complaint.date, reported_at)
		self.assertEqual(complaint.defect_pictures, '/media/complaints/test.jpg')
		self.assertEqual(complaint.root_cause, '根本原因待确认')
		self.assertIsNone(complaint.completion_time)
		self.assertEqual(complaint.remark, '')


class ComplaintTemplateTests(SimpleTestCase):
	def test_three_filter_multiselects_and_initial_permissions(self):
		html = render_to_string('complaint/complaint.html')
		for element_id in ('msType', 'msLevel', 'msStatus'):
			self.assertIn('class="multi-select" id="' + element_id + '"', html)
		self.assertEqual(html.count('class="multi-select-trigger" aria-expanded="false"'), 3)
		self.assertNotIn('id="fLevel"', html)
		self.assertNotIn('id="fStatus"', html)
		self.assertIn('data-can-add="false"', html)

	def test_form_choices_and_local_image_picker(self):
		html = render_to_string('complaint/complaint.html')
		for element_id, values in (
			('fmArea', ('织造', '染色', '整理')),
			('fmLevel', ('A', 'B', 'C')),
			('fmType', ('织造不良', '拉带不良', '染色不良', '整理不良')),
		):
			options = '<option value="">请选择</option>' + ''.join('<option value="' + value + '">' + value + '</option>' for value in values)
			self.assertInHTML('<select class="select-input" id="' + element_id + '">' + options + '</select>', html)
		self.assertIn('data-images-url="/complaint/images/"', html)
		self.assertIn('id="btnAddImage"', html)
		self.assertIn('type="file" id="fmImageFiles"', html)
		self.assertIn('id="imagePreviews"', html)

	def test_database_columns_and_actions_are_preserved(self):
		html = render_to_string('complaint/complaint.html')
		for label in ('编号', '区域', '时间', '客户', '投诉等级', '带型', '投诉点', '分类',
					  '投诉图片', '根本原因', '纠正措施', '责任人', '完成时间', '状态', '备注'):
			with self.subTest(label=label):
				self.assertIn('<th>' + label + '</th>', html)
		self.assertIn('<th class="actions-cell">操作</th>', html)
		self.assertIn('data-records-url="/complaint/records/"', html)
		self.assertNotIn('btnSeedReset', html)

	@override_settings(AUTHENTICATION_BACKENDS=['django.contrib.auth.backends.ModelBackend'])
	def test_anonymous_page_requires_login(self):
		self.assertEqual(reverse('complaint'), '/complaint/')
		response = self.client.get(reverse('complaint'))
		self.assertRedirects(response, reverse('login') + '?next=/complaint/', fetch_redirect_response=False)

	def test_anonymous_navigation_hides_complaint_only(self):
		html = render_to_string('base.html')
		self.assertNotIn('data-page="complaint"', html)
		self.assertIn('data-page="analytics"', html)

	def test_inherits_base_navigation_and_document(self):
		html = render_to_string('complaint/complaint.html')
		self.assertEqual(html.count('<!DOCTYPE html>'), 1)
		self.assertEqual(html.count('<body'), 1)
		self.assertIn('id="sidebarNav"', html)
		self.assertIn('class="complaint-page"', html)

	def test_uses_external_local_assets(self):
		html = render_to_string('complaint/complaint.html')
		self.assertIn('/static/css/complaint.css', html)
		self.assertIn('/static/js/complaint.js', html)
		self.assertIn('/static/js/echarts.min.js', html)
		self.assertNotIn('<style>', html)
		self.assertNotIn('<script>', html)
		self.assertNotIn('image.uc.cn', html)

	def test_preserves_complaint_controls(self):
		html = render_to_string('complaint/complaint.html')
		for element_id in ('btnQuery', 'btnReset', 'btnAdd', 'btnExport', 'formModal', 'detailModal',
						   'chartTrend', 'chartType', 'chartLevel', 'tblBody'):
			with self.subTest(element_id=element_id):
				self.assertIn('id="' + element_id + '"', html)
