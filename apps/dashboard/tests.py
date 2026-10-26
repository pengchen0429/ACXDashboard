from django.contrib.auth import SESSION_KEY, get_user_model
from django.contrib.auth.models import Group, Permission
from django.conf import settings
from django.test import Client, TestCase
from django.shortcuts import resolve_url
from django.urls import reverse


class LoginTests(TestCase):
	@classmethod
	def setUpTestData(cls):
		cls.user = get_user_model().objects.create_user(
			username='login-test', password='short'
		)

	def test_form_posts_to_django_login(self):
		response = self.client.get(reverse('login'))
		self.assertContains(response, 'method="post"')
		self.assertContains(response, 'name="csrfmiddlewaretoken"')
		self.assertContains(response, 'name="username"')
		self.assertContains(response, 'name="password"')

	def test_existing_short_password_authenticates_with_csrf(self):
		client = Client(enforce_csrf_checks=True)
		client.get(reverse('login'))
		response = client.post(reverse('login'), {
			'username': self.user.username,
			'password': 'short',
			'csrfmiddlewaretoken': client.cookies['csrftoken'].value,
		})
		self.assertRedirects(response, reverse('dashboard'))
		self.assertEqual(client.session[SESSION_KEY], str(self.user.pk))

	def test_staff_login_preserves_configured_redirect(self):
		self.user.is_staff = True
		self.user.save(update_fields=['is_staff'])
		response = self.client.post(reverse('login'), {
			'username': self.user.username,
			'password': 'short',
		})
		self.assertRedirects(response, resolve_url(settings.LOGIN_REDIRECT_URL), fetch_redirect_response=False)

	def test_invalid_password_shows_error_without_authentication(self):
		response = self.client.post(reverse('login'), {
			'username': self.user.username,
			'password': 'incorrect',
		})
		self.assertEqual(response.status_code, 200)
		self.assertContains(response, 'class="error-message show"')
		self.assertContains(response, 'value="login-test"')
		self.assertNotIn(SESSION_KEY, self.client.session)

	def test_missing_csrf_is_rejected(self):
		response = Client(enforce_csrf_checks=True).post(reverse('login'), {
			'username': self.user.username,
			'password': 'short',
		})
		self.assertEqual(response.status_code, 403)

	def test_internal_next_redirect(self):
		response = self.client.post(reverse('login'), {
			'username': self.user.username,
			'password': 'short',
			'next': reverse('dpmu'),
		})
		self.assertRedirects(response, reverse('dpmu'), fetch_redirect_response=False)

	def test_external_next_redirect_is_rejected(self):
		response = self.client.post(reverse('login'), {
			'username': self.user.username,
			'password': 'short',
			'next': 'https://example.com/',
		})
		self.assertRedirects(response, reverse('dashboard'))


class PagePermissionTests(TestCase):
	@classmethod
	def setUpTestData(cls):
		cls.users = {}
		for name in ('visitor', 'user', 'manager', 'admin'):
			group, _ = Group.objects.get_or_create(name=name)
			user = get_user_model().objects.create_user(
				username='page-' + name, password='page-test-password',
			)
			user.groups.add(group)
			cls.users[name] = user

	def test_migration_grants_both_permissions_only_to_privileged_groups(self):
		for name in ('visitor', 'user', 'manager', 'admin'):
			with self.subTest(group=name):
				permissions = set(Group.objects.get(name=name).permissions.filter(
					content_type__app_label='dashboard',
				).values_list('codename', flat=True))
				expected = {'view_equipment', 'view_dpmu'} if name in ('manager', 'admin') else set()
				self.assertEqual(permissions, expected)

	def test_anonymous_requests_redirect_to_project_login(self):
		for name in ('equipment', 'dpmu'):
			with self.subTest(page=name):
				url = reverse(name)
				self.assertRedirects(self.client.get(url), reverse('login') + '?next=' + url)
		response = self.client.get(reverse('dashboard'))
		self.assertNotContains(response, 'data-page="equipment"')
		self.assertNotContains(response, 'data-page="dpmu"')

	def test_group_access_matrix_and_navigation(self):
		for name, user in self.users.items():
			self.client.force_login(user)
			allowed = name in ('manager', 'admin')
			response = self.client.get(reverse('dashboard'))
			self.assertEqual(response.status_code, 200)
			self.assertContains(response, 'data-page="briefing"')
			for page in ('equipment', 'dpmu'):
				with self.subTest(group=name, page=page):
					if allowed:
						self.assertContains(response, 'data-page="' + page + '"')
					else:
						self.assertNotContains(response, 'data-page="' + page + '"')
					page_response = self.client.get(reverse(page))
					self.assertEqual(page_response.status_code, 200 if allowed else 403)

	def test_non_staff_group_logins_land_on_dashboard(self):
		for name, user in self.users.items():
			with self.subTest(group=name):
				self.client.logout()
				response = self.client.post(reverse('login'), {
					'username': user.username,
					'password': 'page-test-password',
				})
				self.assertRedirects(response, reverse('dashboard'))

	def test_staff_flag_alone_does_not_grant_page_access(self):
		user = get_user_model().objects.create_user(username='staff-only', is_staff=True)
		self.client.force_login(user)
		for page in ('equipment', 'dpmu'):
			self.assertEqual(self.client.get(reverse(page)).status_code, 403)

	def test_ungrouped_user_has_no_access(self):
		user = get_user_model().objects.create_user(username='ungrouped')
		self.client.force_login(user)
		for page in ('equipment', 'dpmu'):
			self.assertEqual(self.client.get(reverse(page)).status_code, 403)

	def test_superuser_has_access_without_group_membership(self):
		user = get_user_model().objects.create_user(
			username='superuser', is_staff=True, is_superuser=True,
		)
		self.client.force_login(user)
		for page in ('equipment', 'dpmu'):
			self.assertEqual(self.client.get(reverse(page)).status_code, 200)

	def test_multiple_groups_combine_permissions(self):
		user = self.users['user']
		user.groups.add(Group.objects.get(name='manager'))
		self.client.force_login(user)
		for page in ('equipment', 'dpmu'):
			self.assertEqual(self.client.get(reverse(page)).status_code, 200)

	def test_each_page_uses_its_own_permission(self):
		user = get_user_model().objects.create_user(username='equipment-only')
		user.user_permissions.add(Permission.objects.get(
			content_type__app_label='dashboard', codename='view_equipment',
		))
		self.client.force_login(user)
		response = self.client.get(reverse('dashboard'))
		self.assertContains(response, 'data-page="equipment"')
		self.assertNotContains(response, 'data-page="dpmu"')
		self.assertEqual(self.client.get(reverse('equipment')).status_code, 200)
		self.assertEqual(self.client.get(reverse('dpmu')).status_code, 403)
