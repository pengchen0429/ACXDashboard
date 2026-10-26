from django.contrib.auth.views import LoginView
from django.urls import reverse


class AccountsLoginView(LoginView):
	def get_success_url(self):
		redirect_url = super().get_success_url()
		if redirect_url == reverse('admin:index') and not self.request.user.is_staff:
			return reverse('dashboard')
		return redirect_url
