(function () {
	var sidebar = document.getElementById('sidebar');
	var overlay = document.getElementById('sidebarOverlay');
	var toggle = document.getElementById('menuToggle');
	var sidebarNav = document.getElementById('sidebarNav');
	var sidebarVisibilityToggle = document.getElementById('sidebarVisibilityToggle');
	var sidebarVisibilityIcon = sidebarVisibilityToggle.querySelector('.sidebar-visibility-icon');
	var sidebarVisibilityLabel = sidebarVisibilityToggle.querySelector('.sidebar-visibility-label');

	function closeSidebar() {
		sidebar.classList.remove('open');
		overlay.classList.remove('open');
		toggle.setAttribute('aria-expanded', 'false');
	}

	toggle.addEventListener('click', function () {
		var isOpen = sidebar.classList.toggle('open');
		overlay.classList.toggle('open', isOpen);
		toggle.setAttribute('aria-expanded', String(isOpen));
	});
	overlay.addEventListener('click', closeSidebar);
	sidebarVisibilityToggle.addEventListener('click', function () {
		var isVisible = sidebarVisibilityToggle.getAttribute('aria-expanded') === 'true';
		document.body.classList.toggle('sidebar-collapsed', isVisible);
		sidebarVisibilityToggle.setAttribute('aria-expanded', String(!isVisible));
		sidebarVisibilityToggle.setAttribute('aria-label', isVisible ? '显示主导航' : '隐藏主导航');
		sidebarVisibilityIcon.textContent = isVisible ? '☰' : '‹';
		sidebarVisibilityLabel.textContent = isVisible ? '显示导航' : '隐藏导航';
	});
	sidebarNav.addEventListener('click', function (event) {
		var item = event.target.closest('.nav-item[data-page]');
		if (!item) return;
		document.querySelectorAll('.nav-item').forEach(function (navItem) {
			navItem.classList.remove('active');
			navItem.removeAttribute('aria-current');
		});
		item.classList.add('active');
		item.setAttribute('aria-current', 'page');
		closeSidebar();
	});
})();
