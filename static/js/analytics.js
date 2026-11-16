(function() {
	var startInput = document.getElementById('analyticsStartDate');
	var endInput = document.getElementById('analyticsEndDate');
	var dateError = document.getElementById('analyticsDateError');
	var queryButton = document.getElementById('analyticsQuery');
	var resetButton = document.getElementById('analyticsReset');
	var filterStatus = document.getElementById('analyticsFilterStatus');
	var pageElement = document.querySelector('.analytics-page');
	var colors = ['#5b8ff9', '#5ad8a6', '#f6bd16', '#e86452', '#6dc8ec', '#945fb9', '#ff9845', '#1e9493', '#ff99c3', '#7262fd'];
	var charts = {};
	var statuses = {};
	var activeRequest;
	var optionsRequest;
	var optionsLoading = false;
	var statisticsLoading = false;
	var optionsError = '';
	var params = new URLSearchParams(window.location.search);
	var filterInputs = {
		product_name: document.getElementById('analyticsProductName'),
		machine: document.getElementById('analyticsMachine'),
		defect: document.getElementById('analyticsDefect')
	};
	var filterWidgets = {};
	Object.keys(filterInputs).forEach(function(name) {
		Array.from(new Set(params.getAll(name))).filter(Boolean).forEach(function(value) {
			filterInputs[name].add(new Option(value, value, true, true));
		});
		filterWidgets[name] = initMultiSelect(filterInputs[name]);
	});
	document.addEventListener('click', function(event) {
		if (!event.target.closest('.quality-select')) closeFilters(false);
	});
	document.addEventListener('keydown', function(event) {
		if (event.key === 'Escape') closeFilters(true);
	});
	function selectedValues(input) {
		return Array.from(input.selectedOptions).map(function(option) {return option.value;});
	}
	function closeFilters(restoreFocus) {
		Object.keys(filterWidgets).forEach(function(name) {filterWidgets[name].close(restoreFocus);});
	}
	function initMultiSelect(input) {
		var label = input.getAttribute('aria-label');
		var root = document.createElement('div');
		root.className = 'quality-select';
		var trigger = document.createElement('button');
		trigger.type = 'button';
		trigger.className = 'quality-select-trigger';
		trigger.setAttribute('aria-expanded', 'false');
		var panel = document.createElement('div');
		panel.id = input.id + 'Options';
		panel.className = 'quality-select-panel';
		panel.hidden = true;
		trigger.setAttribute('aria-controls', panel.id);
		var search = document.createElement('input');
		search.type = 'search';
		search.className = 'quality-select-search';
		search.placeholder = '搜索';
		search.setAttribute('aria-label', '搜索' + label);
		var list = document.createElement('div');
		list.className = 'quality-select-options';
		var actions = document.createElement('div');
		actions.className = 'quality-select-actions';
		var count = document.createElement('span');
		count.setAttribute('aria-live', 'polite');
		var selectAll = document.createElement('button');
		selectAll.type = 'button';
		selectAll.textContent = '全选';
		var reset = document.createElement('button');
		reset.type = 'button';
		reset.textContent = '清空';
		var confirm = document.createElement('button');
		confirm.type = 'button';
		confirm.textContent = '确定';
		actions.append(count, selectAll, reset, confirm);
		panel.append(search, list, actions);
		root.append(trigger, panel);
		input.after(root);
		var draft = [];
		function renderOptions() {
			list.replaceChildren();
			Array.from(input.options).forEach(function(option) {
				if (!option.value.toLowerCase().includes(search.value.toLowerCase())) return;
				var row = document.createElement('label');
				var checkbox = document.createElement('input');
				checkbox.type = 'checkbox';
				checkbox.value = option.value;
				checkbox.checked = draft.includes(option.value);
				var text = document.createElement('span');
				text.textContent = option.value;
				row.append(checkbox, text);
				list.append(row);
			});
			if (!list.children.length) list.textContent = optionsLoading ? '正在加载选项' : (optionsError || '无可选项');
			count.textContent = '已选 ' + draft.length + ' 项';
		}
		function refresh() {
			var values = selectedValues(input);
			trigger.textContent = values.length ? (values.length === 1 ? values[0] : '已选 ' + values.length + ' 项') : '全部';
			trigger.title = values.length ? values.join('\n') : '全部';
			trigger.setAttribute('aria-label', label + '：' + (values.length ? values.join('、') : '全部'));
			if (!panel.hidden) renderOptions();
		}
		function close(restoreFocus) {
			var wasOpen = !panel.hidden;
			panel.hidden = true;
			trigger.setAttribute('aria-expanded', 'false');
			if (wasOpen && restoreFocus) trigger.focus();
		}
		trigger.addEventListener('click', function() {
			var wasOpen = !panel.hidden;
			closeFilters(false);
			if (wasOpen) return;
			draft = selectedValues(input);
			search.value = '';
			renderOptions();
			panel.hidden = false;
			trigger.setAttribute('aria-expanded', 'true');
			search.focus();
			if (optionsError) loadFilterOptions();
		});
		search.addEventListener('input', renderOptions);
		list.addEventListener('change', function(event) {
			var checkbox = event.target;
			if (checkbox.type !== 'checkbox') return;
			draft = draft.filter(function(value) {return value !== checkbox.value;});
			if (checkbox.checked) draft.push(checkbox.value);
			count.textContent = '已选 ' + draft.length + ' 项';
		});
		selectAll.addEventListener('click', function() {
			var matchingValues = Array.from(input.options).filter(function(option) {
				return option.value.toLowerCase().includes(search.value.toLowerCase());
			}).map(function(option) {return option.value;});
			draft = Array.from(new Set(draft.concat(matchingValues)));
			renderOptions();
		});
		reset.addEventListener('click', function() {draft = []; renderOptions();});
		confirm.addEventListener('click', function() {
			Array.from(input.options).forEach(function(option) {option.selected = draft.includes(option.value);});
			close(true);
			refresh();
			input.dispatchEvent(new Event('change'));
		});
		refresh();
		return {refresh: refresh, close: close, setBusy: function(busy) {
			trigger.disabled = busy;
			selectAll.disabled = busy;
			confirm.disabled = busy;
			root.setAttribute('aria-busy', String(busy));
		}};
	}
	var now = new Date();
	var defaultEnd = new Date(now);
	defaultEnd.setHours(8, 30, 0, 0);
	var daysBack = now.getDay() === 1 ? 3 : 1;
	var defaultStart = new Date(defaultEnd);
	defaultStart.setDate(defaultStart.getDate() - daysBack);
	defaultStart.setHours(8, 31, 0, 0);

	function formatInput(value) {
		return value.getFullYear() + '-' + String(value.getMonth() + 1).padStart(2, '0') + '-' + String(value.getDate()).padStart(2, '0') + 'T' + String(value.getHours()).padStart(2, '0') + ':' + String(value.getMinutes()).padStart(2, '0');
	}
	var initialStart = params.get('start_date');
	var initialEnd = params.get('end_date');
	if (initialStart && /^\d{4}-\d{2}-\d{2}$/.test(initialStart)) initialStart += 'T00:00';
	if (initialEnd && /^\d{4}-\d{2}-\d{2}$/.test(initialEnd)) initialEnd += 'T23:59';
	startInput.value = initialStart || formatInput(defaultStart);
	endInput.value = initialEnd || formatInput(defaultEnd);
	if (!startInput.value) startInput.value = formatInput(defaultStart);
	if (!endInput.value) endInput.value = formatInput(defaultEnd);

	function validateRange() {
		var message = '';
		if (!startInput.value || !endInput.value) message = '请选择开始时间和结束时间';
		else if (startInput.value > endInput.value) message = '开始时间不能晚于结束时间';
		startInput.max = endInput.value;
		endInput.min = startInput.value;
		[startInput, endInput].forEach(function(input) {
			input.setCustomValidity(message);
			input.setAttribute('aria-invalid', String(Boolean(message)));
		});
		dateError.textContent = message;
		dateError.hidden = !message;
		return !message;
	}

	document.querySelectorAll('.analytics-page [data-chart]').forEach(function(element) {
		charts[element.id] = echarts.init(element);
		var status = element.parentElement.querySelector('.trend-status');
		if (!status) {
			status = document.createElement('p');
			status.className = 'trend-status';
			status.setAttribute('role', 'status');
			status.hidden = true;
			element.before(status);
		}
		statuses[element.id] = status;
		element.setAttribute('aria-label', element.parentElement.querySelector('.card-title').textContent);
	});

	function axis(type, data) {
		return {type: type, data: data, axisLine: {lineStyle: {color: '#3a5068'}}, axisLabel: {color: '#7b8fa3', fontSize: 11}, splitLine: {show: type === 'value', lineStyle: {color: 'rgba(100,180,255,0.06)'}}};
	}
	function legend() {
		return {type: 'scroll', bottom: 0, left: 'center', textStyle: {color: '#7b8fa3', fontSize: 11}, pageTextStyle: {color: '#7b8fa3'}, pageIconColor: '#7b8fa3', itemWidth: 12, itemHeight: 12};
	}
	function barOption(items, color, horizontal) {
		var data = horizontal ? items.slice().reverse() : items;
		var category = axis('category', data.map(function(item) {return item.name;}));
		category.axisLabel.width = horizontal ? 100 : 65;
		category.axisLabel.overflow = horizontal ? 'breakAll' : 'truncate';
		if (horizontal) {
			category.axisLabel.interval = 0;
			category.axisLabel.lineHeight = 14;
		}
		if (!horizontal) category.axisLabel.rotate = 30;
		return {
			tooltip: {trigger: 'axis', axisPointer: {type: 'shadow'}},
			grid: horizontal
				? {top: 12, bottom: 28, left: 112, right: '16%', containLabel: false}
				: {top: '8%', bottom: '12%', left: '4%', right: '16%', containLabel: true},
			xAxis: horizontal ? axis('value') : category,
			yAxis: horizontal ? category : axis('value'),
			series: [{name: '报废数量（米）', type: 'bar', barMaxWidth: horizontal ? 18 : 36, itemStyle: {color: color, borderRadius: horizontal ? [0, 4, 4, 0] : [4, 4, 0, 0]}, data: data.map(function(item) {return Number(item.value);}), label: {show: true, position: horizontal ? 'right' : 'top', color: '#c8d6e5', fontSize: 11}, labelLayout: {hideOverlap: true}}]
		};
	}
	function renderRanking(id, items, color) {
		var element = document.getElementById(id);
		var lines = items.reduce(function(maximum, item) {
			var width = echarts.format.getTextRect(String(item.name), '11px sans-serif').width;
			return Math.max(maximum, Math.ceil(width / 88));
		}, 1);
		element.parentElement.classList.add('ranking-card');
		element.style.minHeight = Math.max(180, items.length * (lines * 14 + 4) + 40) + 'px';
		charts[id].resize();
		charts[id].setOption(barOption(items, color, true), true);
	}
	function pieOption(items, donut, total) {
		var option = {
			tooltip: {trigger: 'item'}, legend: legend(),
			series: [{name: '报废数量（米）', type: 'pie', radius: donut ? ['34%', '58%'] : '58%', center: ['50%', '40%'], minShowLabelAngle: 10, label: {show: total === undefined, position: 'inside', formatter: '{d}%', color: '#fff', fontSize: 11}, labelLine: {show: false}, itemStyle: {borderRadius: 3, borderColor: '#1a2a3a', borderWidth: 2}, data: items.map(function(item, index) {return {name: item.name, value: Number(item.value), itemStyle: {color: colors[index % colors.length]}};})}]
		};
		if (total !== undefined) option.graphic = [{type: 'text', left: 'center', top: '34%', style: {text: '报废总量\n' + Number(total).toLocaleString() + ' 米', textAlign: 'center', fill: '#c8d6e5', fontSize: 15, fontWeight: 700}}];
		return option;
	}
	function render(result) {
		var dates = result.days.map(function(day) {return day.date;});
		charts['chart-daily-trend'].setOption({
			tooltip: {trigger: 'axis'}, legend: legend(),
			grid: {top: '12%', bottom: '18%', left: '8%', right: '8%', containLabel: true},
			xAxis: axis('category', dates),
			yAxis: Object.assign(axis('value'), {name: '报废数量（米）', nameTextStyle: {color: '#7b8fa3'}}),
			series: [{name: '报废数量（米）', type: 'bar', barMaxWidth: 32, itemStyle: {color: colors[3]}, data: result.days.map(function(day) {return Number(day.scrap);}), label: {show: true, position: 'top', color: '#7b8fa3', fontSize: 11}, labelLayout: {hideOverlap: true}}]
		}, true);
		charts['chart-daily-cat-trend'].setOption({
			tooltip: {trigger: 'axis'}, legend: legend(),
			grid: {top: '8%', bottom: '18%', left: '6%', right: '4%', containLabel: true},
			xAxis: Object.assign(axis('category', dates), {boundaryGap: false}), yAxis: axis('value'),
			series: result.category_trend.map(function(item, index) {return {name: item.name, type: 'line', stack: 'total', areaStyle: {opacity: 0.6}, itemStyle: {color: colors[index % colors.length]}, lineStyle: {width: 1}, symbol: 'none', data: item.data.map(Number)};})
		}, true);
		charts['chart-defect-cat'].setOption(pieOption(result.categories, true, result.total), true);
		renderRanking('chart-defect-top10', result.defects, colors[0]);
		charts['chart-team'].setOption(barOption(result.teams, colors[1], false), true);
		renderRanking('chart-device', result.devices, colors[6]);
		renderRanking('chart-inspector', result.inspectors, colors[5]);
		charts['chart-barcode'].setOption(pieOption(result.barcodes, false), true);
		charts['chart-scrap-cat'].setOption(pieOption(result.scrap_categories, true), true);
		renderRanking('chart-product', result.products, colors[1]);
	}
	function clearCharts() {
		render({days: [], total: 0, category_trend: [], categories: [], defects: [], teams: [], devices: [], inspectors: [], barcodes: [], scrap_categories: [], products: []});
	}
	function setStatus(message) {
		Object.keys(statuses).forEach(function(id) {statuses[id].textContent = message; statuses[id].hidden = !message;});
	}
	function updateFilterOptions(options, query) {
		var changed = false;
		Object.keys(filterInputs).forEach(function(name) {
			var input = filterInputs[name];
			var values = (options[name] || []).slice();
			var selected = query.getAll(name).filter(function(value) {return values.includes(value);});
			if (selected.length !== query.getAll(name).length) changed = true;
			input.replaceChildren();
			values.forEach(function(value) {input.add(new Option(value, value, false, selected.includes(value)));});
			filterWidgets[name].refresh();
		});
		return changed;
	}
	function currentQuery() {
		var query = new URLSearchParams({start_date: startInput.value, end_date: endInput.value});
		Object.keys(filterInputs).forEach(function(name) {
			selectedValues(filterInputs[name]).forEach(function(value) {query.append(name, value);});
		});
		return query;
	}
	function updateQueryButton() {
		queryButton.disabled = optionsLoading || statisticsLoading;
	}
	async function loadFilterOptions() {
		if (optionsRequest) optionsRequest.abort();
		closeFilters(false);
		optionsError = '';
		filterStatus.hidden = true;
		if (!validateRange()) {
			optionsLoading = false;
			Object.keys(filterWidgets).forEach(function(name) {filterWidgets[name].setBusy(false);});
			updateQueryButton();
			return;
		}
		var controller = new AbortController();
		optionsRequest = controller;
		var query = currentQuery();
		query.set('options_only', '1');
		optionsLoading = true;
		Object.keys(filterWidgets).forEach(function(name) {filterWidgets[name].setBusy(true);});
		updateQueryButton();
		try {
			var response = await fetch(pageElement.dataset.statisticsUrl + '?' + query.toString(), {signal: controller.signal, headers: {Accept: 'application/json'}});
			if (!response.ok) throw new Error('筛选项加载失败，请重新打开下拉框重试');
			var result = await response.json();
			if (controller.signal.aborted) return;
			if (updateFilterOptions(result.filter_options || {}, query)) await loadFilterOptions();
		} catch (error) {
			if (controller.signal.aborted) return;
			optionsError = error.message || '筛选项加载失败，请重新打开下拉框重试';
			filterStatus.textContent = optionsError;
			filterStatus.hidden = false;
		} finally {
			if (optionsRequest === controller && !controller.signal.aborted) {
				optionsLoading = false;
				Object.keys(filterWidgets).forEach(function(name) {filterWidgets[name].setBusy(false);});
				updateQueryButton();
			}
		}
	}
	function setBusy(busy) {
		statisticsLoading = busy;
		updateQueryButton();
		Object.keys(charts).forEach(function(id) {
			document.getElementById(id).setAttribute('aria-busy', String(busy));
			if (busy) charts[id].showLoading('default', {text: '加载中', color: colors[0], textColor: '#c8d6e5', maskColor: 'rgba(26,42,58,0.85)'});
			else charts[id].hideLoading();
		});
	}
	async function loadStatistics() {
		if (activeRequest) activeRequest.abort();
		clearCharts();
		if (!validateRange()) {
			setBusy(false);
			setStatus('请选择有效的时间范围');
			return;
		}
		var controller = new AbortController();
		activeRequest = controller;
		var query = currentQuery();
		setStatus('');
		setBusy(true);
		try {
			var response = await fetch(pageElement.dataset.statisticsUrl + '?' + query.toString(), {signal: controller.signal, headers: {Accept: 'application/json'}});
			if (!response.ok) throw new Error(response.status === 400 ? '时间范围无效或超过 3660 天，请调整后重试' : '数据查询失败，请稍后重试');
			var result = await response.json();
			if (controller.signal.aborted) return;
			render(result);
			setStatus(Number(result.total) ? '' : '所选条件暂无报废数量');
			var url = new URL(window.location.href);
			url.searchParams.set('start_date', query.get('start_date'));
			url.searchParams.set('end_date', query.get('end_date'));
			Object.keys(filterInputs).forEach(function(name) {
				url.searchParams.delete(name);
				query.getAll(name).forEach(function(value) {url.searchParams.append(name, value);});
			});
			window.history.replaceState(null, '', url);
		} catch (error) {
			if (controller.signal.aborted) return;
			clearCharts();
			setStatus(error.message || '数据查询失败，请稍后重试');
		} finally {
			if (activeRequest === controller && !controller.signal.aborted) setBusy(false);
		}
	}
	startInput.addEventListener('change', loadFilterOptions);
	endInput.addEventListener('change', loadFilterOptions);
	queryButton.addEventListener('click', loadStatistics);
	resetButton.addEventListener('click', function() {
		closeFilters(false);
		Object.keys(filterInputs).forEach(function(name) {
			Array.from(filterInputs[name].options).forEach(function(option) {option.selected = false;});
			filterWidgets[name].refresh();
		});
		loadFilterOptions();
	});
	Object.keys(filterInputs).forEach(function(name) {filterInputs[name].addEventListener('change', loadFilterOptions);});
	var observer = new ResizeObserver(function(entries) {
		entries.forEach(function(entry) {charts[entry.target.id].resize();});
	});
	document.querySelectorAll('.analytics-page [data-chart]').forEach(function(element) {observer.observe(element);});
	loadFilterOptions();
	loadStatistics();
})();