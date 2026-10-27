from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from .models import Department, Employee, Team


class OrganizationAdminTests(TestCase):
	@classmethod
	def setUpTestData(cls):
		cls.admin_user = get_user_model().objects.create_superuser(
			username="organization-admin", password="test-password"
		)
		cls.user = get_user_model().objects.create_user(username="employee-user")
		cls.group = Group.objects.create(name="organization-role")
		cls.user.groups.add(cls.group)
		cls.department = Department.objects.create(name="Production")
		cls.team = Team.objects.create(name="Team A", department=cls.department)

	def setUp(self):
		self.client.force_login(self.admin_user)
		self.change_url = reverse("admin:auth_user_change", args=[self.user.pk])

	def user_form_data(self, **employee_fields):
		date_joined = timezone.localtime(self.user.date_joined)
		data = {
			"username": self.user.username,
			"is_active": "on",
			"groups": [self.group.pk],
			"date_joined_0": date_joined.strftime("%Y-%m-%d"),
			"date_joined_1": date_joined.strftime("%H:%M:%S"),
			"employee-TOTAL_FORMS": "1",
			"employee-INITIAL_FORMS": "0",
			"employee-MIN_NUM_FORMS": "0",
			"employee-MAX_NUM_FORMS": "1",
			"employee-0-is_active": "on",
		}
		data.update(employee_fields)
		return data

	def test_user_change_shows_employee_inline_and_groups(self):
		response = self.client.get(self.change_url)

		self.assertEqual(response.status_code, 200)
		self.assertContains(response, 'name="employee-0-employee_no"')
		self.assertContains(response, 'name="groups"')

	def test_save_user_creates_employee_without_changing_groups(self):
		response = self.client.post(self.change_url, self.user_form_data(**{
			"employee-0-employee_no": "E001",
			"employee-0-name": "Employee One",
			"employee-0-department": self.department.pk,
			"employee-0-team": self.team.pk,
			"employee-0-is_active": "on",
		}))

		self.assertEqual(response.status_code, 302)
		employee = Employee.objects.get(user=self.user)
		self.assertEqual(employee.employee_no, "E001")
		self.assertEqual(employee.department, self.department)
		self.assertEqual(employee.team, self.team)
		self.assertEqual(list(self.user.groups.all()), [self.group])

	def test_user_can_be_saved_without_employee(self):
		response = self.client.post(self.change_url, self.user_form_data())

		self.assertEqual(response.status_code, 302)
		self.assertFalse(Employee.objects.filter(user=self.user).exists())

	def test_save_user_updates_existing_employee(self):
		employee = Employee.objects.create(
			employee_no="E002", name="Original Name", user=self.user
		)
		response = self.client.post(self.change_url, self.user_form_data(**{
			"employee-INITIAL_FORMS": "1",
			"employee-0-id": employee.pk,
			"employee-0-employee_no": employee.employee_no,
			"employee-0-name": "Updated Name",
			"employee-0-is_active": "on",
		}))

		self.assertEqual(response.status_code, 302)
		employee.refresh_from_db()
		self.assertEqual(employee.name, "Updated Name")
		self.assertEqual(Employee.objects.filter(user=self.user).count(), 1)

	def test_employee_change_allows_selecting_existing_user(self):
		employee = Employee.objects.create(employee_no="E003", name="Unlinked")
		response = self.client.get(
			reverse("admin:organization_employee_change", args=[employee.pk])
		)

		self.assertEqual(response.status_code, 200)
		self.assertContains(response, 'name="user"')
		self.assertContains(response, 'class="admin-autocomplete"')
