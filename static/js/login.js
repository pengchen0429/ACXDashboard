(function () {
	const loginForm = document.getElementById('loginForm');
	const loginBtn = document.getElementById('loginBtn');

	loginForm.addEventListener('submit', function (event) {
		if (loginBtn.disabled) {
			event.preventDefault();
			return;
		}

		loginBtn.disabled = true;
		loginBtn.innerHTML = '<span class="loading"></span>登录中...';
	});

	window.addEventListener('pageshow', function () {
		loginBtn.disabled = false;
		loginBtn.textContent = '登录系统';
	});

	window.addEventListener('load', function () {
		document.getElementById('username').focus();
	});
})();
