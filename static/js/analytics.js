(function() {
	var startInput = document.getElementById('analyticsStartDate');
	var endInput = document.getElementById('analyticsEndDate');
	var dateError = document.getElementById('analyticsDateError');
	var queryButton = document.getElementById('analyticsQuery');
	var pageElement = document.querySelector('.analytics-page');
	var colors = ['#5b8ff9', '#5ad8a6', '#f6bd16', '#e86452', '#6dc8ec', '#945fb9', '#ff9845', '#1e9493', '#ff99c3', '#7262fd'];
	var charts = {};
	var statuses = {};
	var activeRequest;
	var params = new URLSearchParams(window.location.search);
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
		category.axisLabel.overflow = 'truncate';
		if (!horizontal) category.axisLabel.rotate = 30;
		return {
			tooltip: {trigger: 'axis', axisPointer: {type: 'shadow'}},
			grid: {top: '8%', bottom: '12%', left: '4%', right: '16%', containLabel: true},
			xAxis: horizontal ? axis('value') : category,
			yAxis: horizontal ? category : axis('value'),
			series: [{name: '报废数量（米）', type: 'bar', barMaxWidth: horizontal ? 18 : 36, itemStyle: {color: color, borderRadius: horizontal ? [0, 4, 4, 0] : [4, 4, 0, 0]}, data: data.map(function(item) {return Number(item.value);}), label: {show: true, position: horizontal ? 'right' : 'top', color: '#c8d6e5', fontSize: 11}, labelLayout: {hideOverlap: true}}]
		};
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
		charts['chart-defect-top10'].setOption(barOption(result.defects, colors[0], true), true);
		charts['chart-team'].setOption(barOption(result.teams, colors[1], false), true);
		charts['chart-device'].setOption(barOption(result.devices, colors[6], true), true);
		charts['chart-inspector'].setOption(barOption(result.inspectors, colors[5], true), true);
		charts['chart-barcode'].setOption(pieOption(result.barcodes, false), true);
		charts['chart-scrap-cat'].setOption(pieOption(result.scrap_categories, true), true);
		charts['chart-product'].setOption(barOption(result.products, colors[1], true), true);
	}
	function clearCharts() {
		render({days: [], total: 0, category_trend: [], categories: [], defects: [], teams: [], devices: [], inspectors: [], barcodes: [], scrap_categories: [], products: []});
	}
	function setStatus(message) {
		Object.keys(statuses).forEach(function(id) {statuses[id].textContent = message; statuses[id].hidden = !message;});
	}
	function setBusy(busy) {
		queryButton.disabled = busy;
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
		var query = new URLSearchParams({start_date: startInput.value, end_date: endInput.value});
		setStatus('');
		setBusy(true);
		try {
			var response = await fetch(pageElement.dataset.statisticsUrl + '?' + query.toString(), {signal: controller.signal, headers: {Accept: 'application/json'}});
			if (!response.ok) throw new Error(response.status === 400 ? '时间范围无效或超过 3660 天，请调整后重试' : '数据查询失败，请稍后重试');
			var result = await response.json();
			if (controller.signal.aborted) return;
			render(result);
			setStatus(Number(result.total) ? '' : '所选时间范围暂无报废数量');
			var url = new URL(window.location.href);
			url.searchParams.set('start_date', query.get('start_date'));
			url.searchParams.set('end_date', query.get('end_date'));
			window.history.replaceState(null, '', url);
		} catch (error) {
			if (controller.signal.aborted) return;
			clearCharts();
			setStatus(error.message || '数据查询失败，请稍后重试');
		} finally {
			if (activeRequest === controller && !controller.signal.aborted) setBusy(false);
		}
	}
	startInput.addEventListener('change', loadStatistics);
	endInput.addEventListener('change', loadStatistics);
	queryButton.addEventListener('click', loadStatistics);
	var observer = new ResizeObserver(function(entries) {
		entries.forEach(function(entry) {charts[entry.target.id].resize();});
	});
	document.querySelectorAll('.analytics-page [data-chart]').forEach(function(element) {observer.observe(element);});
	loadStatistics();
})();