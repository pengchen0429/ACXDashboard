from django.template.loader import render_to_string
from django.test import SimpleTestCase, override_settings
from django.urls import include, path
from django.views.generic import TemplateView


urlpatterns = [
	path('', include('config.urls')),
	path('dyecontrol/', TemplateView.as_view(template_name='base.html'), name='dyecontrol'),
]


class DyecontrolNavigationTests(SimpleTestCase):
	def test_missing_route_does_not_break_navigation_with_permission(self):
		html = render_to_string('base.html', {'perms': {'accounts': {'view_dyecontrol': True}}})
		self.assertNotIn('data-page="dyecontrol"', html)

	@override_settings(ROOT_URLCONF=__name__)
	def test_registered_route_is_shown_with_permission(self):
		html = render_to_string('base.html', {'perms': {'accounts': {'view_dyecontrol': True}}})
		self.assertIn('href="/dyecontrol/" data-page="dyecontrol"', html)

	@override_settings(ROOT_URLCONF=__name__)
	def test_registered_route_is_hidden_without_permission(self):
		html = render_to_string('base.html', {'perms': {'accounts': {'view_dyecontrol': False}}})
		self.assertNotIn('data-page="dyecontrol"', html)
