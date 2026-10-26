from importlib import import_module

from django.apps import apps
from django.contrib.auth import BACKEND_SESSION_KEY, SESSION_KEY, get_user_model
from django.contrib.auth.models import AnonymousUser, Group, Permission
from django.contrib.contenttypes.models import ContentType
from django.db import connection
from django.test import TestCase
from django.urls import reverse


class PermissionMigrationTests(TestCase):
	def move_permissions(self):
		migration = import_module('apps.accounts.migrations.0001_initial')
		migration.move_page_permissions(apps, connection.schema_editor())

	def legacy_permission(self):
		content_type, _ = ContentType.objects.get_or_create(
			app_label='dashboard', model='pageaccess',
		)
		return Permission.objects.create(
			content_type=content_type, codename='view_equipment', name='Legacy equipment',
		)

	def account_permission(self):
		return Permission.objects.get(
			content_type__app_label='accounts', content_type__model='pageaccess',
			codename='view_equipment',
		)

	def test_accounts_owns_all_seven_declared_permissions(self):
		self.assertEqual(apps.get_app_config('accounts').name, 'apps.accounts')
		permissions = set(Permission.objects.filter(
			content_type__app_label='accounts', content_type__model='pageaccess',
		).values_list('codename', flat=True))
		self.assertEqual(permissions, {
			'view_dashboard', 'view_analytics', 'view_briefing', 'view_equipment',
			'view_dpmu', 'manage_settings', 'manage_users',
		})
		self.assertFalse(Permission.objects.filter(
			content_type__app_label='dashboard', content_type__model='pageaccess',
		).exists())
		self.assertNotIn('PageAccess', [model.__name__ for model in apps.get_app_config('dashboard').get_models()])

	def test_move_preserves_permission_id_and_group_and_user_grants(self):
		self.account_permission().delete()
		permission = self.legacy_permission()
		permission_id = permission.pk
		group = Group.objects.create(name='legacy-group')
		user = get_user_model().objects.create_user(username='legacy-user')
		group.permissions.add(permission)
		user.user_permissions.add(permission)
		self.move_permissions()
		moved = self.account_permission()
		self.assertEqual(moved.pk, permission_id)
		self.assertTrue(group.permissions.filter(pk=moved.pk).exists())
		self.assertTrue(user.user_permissions.filter(pk=moved.pk).exists())

	def test_duplicate_permission_merges_old_and_new_grants(self):
		old_permission = self.legacy_permission()
		new_permission = self.account_permission()
		old_group = Group.objects.create(name='old-group')
		new_group = Group.objects.create(name='new-group')
		old_user = get_user_model().objects.create_user(username='old-user')
		new_user = get_user_model().objects.create_user(username='new-user')
		old_group.permissions.add(old_permission)
		new_group.permissions.add(new_permission)
		old_user.user_permissions.add(old_permission)
		new_user.user_permissions.add(new_permission)
		self.move_permissions()
		self.assertFalse(Permission.objects.filter(pk=old_permission.pk).exists())
		for group in (old_group, new_group):
			self.assertTrue(group.permissions.filter(pk=new_permission.pk).exists())
		for user in (old_user, new_user):
			self.assertTrue(user.user_permissions.filter(pk=new_permission.pk).exists())

	def test_transfer_is_idempotent_and_does_not_restore_revoked_grants(self):
		group = Group.objects.get(name='manager')
		group.permissions.remove(self.account_permission())
		self.move_permissions()
		self.move_permissions()
		self.assertFalse(group.permissions.filter(pk=self.account_permission().pk).exists())

	def test_new_permissions_are_not_automatically_granted(self):
		codenames = ('view_dashboard', 'view_analytics', 'view_briefing', 'manage_settings', 'manage_users')
		self.assertFalse(Group.objects.filter(
			permissions__content_type__app_label='accounts',
			permissions__codename__in=codenames,
		).exists())


class VisitorPermissionTests(TestCase):
	@classmethod
	def setUpTestData(cls):
		cls.visitor, _ = Group.objects.get_or_create(name='visitor')
		cls.equipment_permission = Permission.objects.get(
			content_type__app_label='accounts', codename='view_equipment',
		)
		cls.visitor.permissions.add(cls.equipment_permission)

	def test_anonymous_access_and_navigation_match_visitor_permissions(self):
		response = self.client.get(reverse('equipment'))
		self.assertEqual(response.status_code, 200)
		self.assertContains(response, 'data-page="equipment"')
		self.assertNotContains(response, 'data-page="dpmu"')
		self.assertContains(response, 'class="sidebar-login" href="' + reverse('login') + '"')
		self.assertNotContains(response, 'class="sidebar-account"')
		self.assertFalse(response.wsgi_request.user.is_authenticated)
		self.assertNotIn(SESSION_KEY, self.client.session)

	def test_ungranted_page_still_redirects_to_login(self):
		self.assertRedirects(
			self.client.get(reverse('dpmu')),
			reverse('login') + '?next=' + reverse('dpmu'),
		)

	def test_group_edits_take_effect_on_next_request(self):
		self.assertEqual(self.client.get(reverse('equipment')).status_code, 200)
		self.visitor.permissions.remove(self.equipment_permission)
		self.assertEqual(self.client.get(reverse('equipment')).status_code, 302)
		response = self.client.get(reverse('dashboard'))
		self.assertNotContains(response, 'data-page="equipment"')
		self.visitor.permissions.add(self.equipment_permission)
		self.assertEqual(self.client.get(reverse('equipment')).status_code, 200)

	def test_missing_visitor_group_denies_access_without_creating_it(self):
		self.visitor.delete()
		self.assertRedirects(
			self.client.get(reverse('equipment')),
			reverse('login') + '?next=' + reverse('equipment'),
		)
		self.assertFalse(Group.objects.filter(name='visitor').exists())

	def test_authenticated_user_does_not_inherit_visitor_permissions(self):
		user = get_user_model().objects.create_user(username='ordinary-user')
		self.client.force_login(user)
		self.assertEqual(self.client.get(reverse('equipment')).status_code, 403)
		response = self.client.get(reverse('dashboard'))
		self.assertNotContains(response, 'data-page="equipment"')
		self.assertContains(response, 'ordinary-user')
		self.assertEqual(self.client.session[BACKEND_SESSION_KEY], 'django.contrib.auth.backends.ModelBackend')

	def test_authenticated_visitor_group_member_keeps_normal_group_access(self):
		user = get_user_model().objects.create_user(username='visitor-member')
		user.groups.add(self.visitor)
		self.client.force_login(user)
		self.assertEqual(self.client.get(reverse('equipment')).status_code, 200)
		self.assertEqual(self.client.get(reverse('dpmu')).status_code, 403)

	def test_anonymous_permission_queries_are_cached_on_user_only(self):
		user = AnonymousUser()
		with self.assertNumQueries(1):
			self.assertTrue(user.has_perm('accounts.view_equipment'))
			self.assertFalse(user.has_perm('accounts.view_dpmu'))
			self.assertTrue(user.has_module_perms('accounts'))
			self.assertEqual(user.get_all_permissions(), {'accounts.view_equipment'})
		self.assertFalse(user.is_authenticated)
		self.assertFalse(user.is_staff)
		self.assertFalse(user.is_superuser)

	def test_visitor_group_does_not_grant_admin_model_permissions_to_anonymous(self):
		self.visitor.permissions.add(Permission.objects.get(
			content_type__app_label='auth', codename='change_user',
		))
		user = AnonymousUser()
		self.assertTrue(user.has_perm('accounts.view_equipment'))
		self.assertFalse(user.has_perm('auth.change_user'))
		self.assertFalse(user.has_module_perms('auth'))
		self.assertRedirects(
			self.client.get(reverse('admin:index')),
			reverse('admin:login') + '?next=' + reverse('admin:index'),
		)
