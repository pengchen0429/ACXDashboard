(function() {
	var card = document.getElementById('todayProduction');
	if (!card) return;
	var metrics = [
		{ card: card, field: 'actual', loaded: false },
		{ card: document.getElementById('todayDowntime'), field: 'downtime_minutes', loaded: false }
	].filter(function(metric) { return metric.card; });
	var readings = card.querySelectorAll('[data-production-site]');
	var snapshots = {};
	var reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)');

	function renderMetric(metric, site, data) {
		var reading = metric.card.querySelector('[data-production-site="' + site + '"]');
		var value = reading.querySelector('[data-production-value]');
		var siteStatus = reading.querySelector('.production-site-status');
		var total = data && data[metric.field] != null ? Number(data[metric.field]) : NaN;
		if (Number.isFinite(total)) {
			var nextValue = total.toLocaleString('zh-CN', { maximumFractionDigits: 20 });
			var changed = value.textContent !== nextValue;
			var previouslyLoaded = value.textContent !== '--';
			if (changed) value.textContent = nextValue;
			if (changed && previouslyLoaded && !reducedMotion.matches && value.animate) {
				value.animate([{ opacity: 0.65 }, { opacity: 1 }], { duration: 240, easing: 'ease-out' });
			}
			siteStatus.textContent = data.stale ? '数据暂未更新' : '';
			if (data.updated_at) reading.title = '数据更新时间：' + new Date(data.updated_at).toLocaleString('zh-CN');
			metric.loaded = true;
			metric.card.querySelector('.daily-metric-period').textContent = data.start_date.slice(0, 10) + ' 08:30 - ' + data.end_date.slice(0, 10) + ' 08:30';
		} else {
			value.textContent = '--';
			siteStatus.textContent = '暂不可用';
		}
	}

	function refreshSite(reading) {
		var site = reading.dataset.productionSite;
		var controller = new AbortController();
		var timeout = window.setTimeout(function() { controller.abort(); }, 20000);
		return fetch(card.dataset.url + '?site=' + encodeURIComponent(site) + '&include_trend=1', { cache: 'no-store', signal: controller.signal })
			.then(function(response) {
				if (!response.ok) throw new Error('Daily metrics request failed');
				return response.json();
			})
			.then(function(data) {
				snapshots[site] = data;
				metrics.forEach(function(metric) { renderMetric(metric, site, data); });
				renderAreaProduction(site, data);
				renderProductionTrend(site, data);
				renderEquipmentStatus(site, data);
			})
			.catch(function() {
				var data = snapshots[site] ? Object.assign({}, snapshots[site], { stale: true }) : null;
				metrics.forEach(function(metric) { renderMetric(metric, site, data); });
				renderAreaProduction(site, data);
				renderProductionTrend(site, data);
				renderEquipmentStatus(site, data);
			})
			.finally(function() {
				window.clearTimeout(timeout);
				metrics.forEach(function(metric) {
					metric.card.querySelector('[data-production-site="' + site + '"]').setAttribute('aria-busy', 'false');
				});
			});
	}

	function refresh() {
		Promise.all(Array.from(readings, refreshSite)).finally(function() {
			metrics.forEach(function(metric) {
				metric.card.setAttribute('aria-busy', 'false');
				if (!metric.loaded) metric.card.querySelector('.daily-metric-period').textContent = '暂不可用';
			});
			window.setTimeout(refresh, 30000);
		});
	}
	refresh();
})();

/* SECTION: clock */
(function() {
	function tick() {
		var now = new Date();
		var y = now.getFullYear(), m = String(now.getMonth()+1).padStart(2,'0');
		var d = String(now.getDate()).padStart(2,'0');
		var h = String(now.getHours()).padStart(2,'0');
		var mi = String(now.getMinutes()).padStart(2,'0');
		var s = String(now.getSeconds()).padStart(2,'0');
		var el = document.getElementById('topClock');
		if (el) el.textContent = y+'-'+m+'-'+d+' '+h+':'+mi+':'+s;
	}
	tick(); setInterval(tick, 1000);
})();

/* SECTION: chart-instances */
var chartInstances = {};
var areaProductionBySite = { ACX: null, CNX: null };
var trendProductionBySite = { ACX: null, CNX: null };
var trendDates = (function() {
	var today = new Date().toLocaleDateString('sv-SE', { timeZone: 'Asia/Shanghai' });
	return Array.from({ length: 7 }, function(unused, index) {
		var date = new Date(today + 'T00:00:00Z');
		date.setUTCDate(date.getUTCDate() - 6 + index);
		return date.toISOString().slice(0, 10);
	});
})();
echarts.registerTheme('acxCockpit', {
	color: ['#50d9e8', '#54dfad', '#efbd68', '#99bafa', '#f27b83'],
	textStyle: { fontFamily: 'Bahnschrift, Microsoft YaHei, sans-serif' },
	animationDuration: window.matchMedia('(prefers-reduced-motion: reduce)').matches ? 0 : 450,
	animationDurationUpdate: window.matchMedia('(prefers-reduced-motion: reduce)').matches ? 0 : 450,
	animationEasingUpdate: 'cubicOut'
});

/* SECTION: chart-dashboard-trend */
function renderProductionTrend(site, data) {
	trendProductionBySite[site] = data || { error: true };
	var chart = chartInstances.dashTrend;
	if (!chart) return;
	if (data && Array.isArray(data.trend) && data.trend.length === 7) {
		trendDates = data.trend.map(function(day) { return day.date; });
	}
	var messages = [];
	var series = Object.keys(trendProductionBySite).map(function(name) {
		var snapshot = trendProductionBySite[name];
		var values = trendDates.map(function(date) {
			var day = snapshot && Array.isArray(snapshot.trend) ? snapshot.trend.find(function(item) { return item.date === date; }) : null;
			var value = day && day.actual != null ? Number(day.actual) : NaN;
			return Number.isFinite(value) ? value : null;
		});
		if (!snapshot) messages.push(name + ' 加载中');
		else if (values.some(function(value) { return value == null; })) messages.push(name + ' 暂不可用');
		else if (snapshot.stale) messages.push(name + ' 数据暂未更新');
		return { name: name, data: values };
	});
	chart.setOption({ xAxis: { data: trendDates }, series: series });
	document.getElementById('dashTrendStatus').textContent = messages.join(' · ');
	var element = document.getElementById('dashTrend');
	element.setAttribute('aria-busy', String(Object.keys(trendProductionBySite).some(function(name) { return !trendProductionBySite[name]; })));
	element.setAttribute('aria-label', trendDates.map(function(date, index) {
		return date + ' ' + series.map(function(item) {
			return item.name + ' ' + (item.data[index] == null ? '暂不可用' : item.data[index] + ' 米');
		}).join('，');
	}).join('；'));
}

(function() {
	var el = document.getElementById('dashTrend');
	if (!el) return;
	var c = echarts.init(el, 'acxCockpit');
	chartInstances['dashTrend'] = c;
	c.setOption({
		tooltip: { trigger:'axis', backgroundColor:'rgba(10,22,40,0.95)', borderColor:'rgba(0,212,255,0.2)', textStyle:{color:'#e0e6ed',fontSize:12} },
		legend: { bottom:0, left:'center', textStyle:{color:'#6b7b8d',fontSize:11} },
		grid: { top:'10%', bottom:'18%', left:'10%', right:'6%', containLabel:true },
		xAxis: { type:'category', data:trendDates, boundaryGap:true, axisLine:{lineStyle:{color:'rgba(255,255,255,0.08)'}}, axisLabel:{color:'#6b7b8d',fontSize:11,formatter:function(value){return value.slice(5).replace('-', '/');}} },
		yAxis: { type:'value', splitLine:{lineStyle:{color:'rgba(255,255,255,0.04)'}}, axisLabel:{color:'#6b7b8d',fontSize:11,formatter:function(v){return (v/1000).toFixed(0)+'k';}} },
		series: [
			{ name:'ACX', type:'bar', data:trendDates.map(function(){return null;}), barMaxWidth:22, barGap:'20%', itemStyle:{color:'#50d9e8',borderRadius:[2,2,0,0]} },
			{ name:'CNX', type:'bar', data:trendDates.map(function(){return null;}), barMaxWidth:22, itemStyle:{color:'#efbd68',borderRadius:[2,2,0,0]} }
		]
	});
})();

/* SECTION: chart-dashboard-lines */
function renderAreaProduction(site, data) {
	areaProductionBySite[site] = data || { error: true };
	var chart = chartInstances.dashLines;
	if (!chart) return;
	var groups = ['ACX-Weaving', 'ACX-Dyeing', 'CNX-Weaving', 'CNX-Dyeing'];
	var colors = ['#50d9e8', '#54dfad', '#99bafa', '#efbd68'];
	var values = groups.map(function(group, index) {
		var parts = group.split('-');
		var snapshot = areaProductionBySite[parts[0]];
		var raw = snapshot && snapshot.area_actual ? snapshot.area_actual[parts[1]] : null;
		var value = raw == null ? NaN : Number(raw);
		return { value: Number.isFinite(value) ? value : null, itemStyle: { color: colors[index], borderRadius: [0, 2, 2, 0] } };
	});
	chart.setOption({ series: [{ data: values }] });
	var messages = Object.keys(areaProductionBySite).map(function(name) {
		var snapshot = areaProductionBySite[name];
		if (!snapshot) return name + ' 加载中';
		if (!snapshot.area_actual || ['Weaving', 'Dyeing'].some(function(area) {
			return snapshot.area_actual[area] == null || !Number.isFinite(Number(snapshot.area_actual[area]));
		})) return name + ' 暂不可用';
		return snapshot.stale ? name + ' 数据暂未更新' : '';
	}).filter(Boolean);
	document.getElementById('dashLinesStatus').textContent = messages.join(' · ');
	var element = document.getElementById('dashLines');
	element.setAttribute('aria-busy', String(Object.keys(areaProductionBySite).some(function(name) { return !areaProductionBySite[name]; })));
	element.setAttribute('aria-label', groups.map(function(group, index) {
		return group + '：' + (values[index].value == null ? '暂不可用' : values[index].value + ' 米');
	}).join('；'));
}

(function() {
	var el = document.getElementById('dashLines');
	if (!el) return;
	var c = echarts.init(el, 'acxCockpit');
	chartInstances['dashLines'] = c;
	c.setOption({
		tooltip: { trigger:'axis', backgroundColor:'rgba(10,22,40,0.95)', borderColor:'rgba(0,212,255,0.2)', textStyle:{color:'#e0e6ed',fontSize:12} },
		grid: { top:'8%', bottom:'8%', left:'12%', right:'8%', containLabel:true },
		xAxis: { type:'value', splitLine:{lineStyle:{color:'rgba(255,255,255,0.04)'}}, axisLabel:{color:'#6b7b8d',fontSize:11} },
		yAxis: { type:'category', inverse:true, data:['ACX-Weaving','ACX-Dyeing','CNX-Weaving','CNX-Dyeing'], axisLine:{lineStyle:{color:'rgba(255,255,255,0.08)'}}, axisLabel:{color:'#a0b4c8',fontSize:12} },
		series: [{ type:'bar', barWidth:18,
			data:[null,null,null,null],
			label:{show:true,position:'right',color:'#a0b4c8',fontSize:11,formatter:function(p){return p.value == null ? '--' : Number(p.value).toLocaleString('zh-CN');}}
		}]
	});
})();

/* SECTION: chart-dashboard-equip */
function renderEquipmentStatus(site, data) {
	var chartId = 'dashEquip' + site;
	var chart = chartInstances[chartId];
	if (!chart) return;
	var counts = data && data.equipment_status;
	var valid = counts && ['running', 'stopped', 'total'].every(function(key) {
		return Number.isInteger(counts[key]) && counts[key] >= 0;
	}) && counts.running + counts.stopped === counts.total;
	chart.setOption({
		graphic: [{ id: 'equipment-total', style: { text: (valid ? counts.total : '--') + '\n设备总数' } }],
		series: [{ data: valid ? [{ name: '开机', value: counts.running }, { name: '未开机', value: counts.stopped }] : [] }]
	});
	document.getElementById(chartId + 'Status').textContent = !valid ? '暂不可用' : data.stale ? '数据暂未更新' : counts.total === 0 ? '无设备数据' : '';
	var element = document.getElementById(chartId);
	element.setAttribute('aria-busy', 'false');
	element.setAttribute('aria-label', site + (valid ? '：开机 ' + counts.running + ' 台，未开机 ' + counts.stopped + ' 台，共 ' + counts.total + ' 台' : '设备状态暂不可用'));
}

['ACX', 'CNX'].forEach(function(site) {
	var chartId = 'dashEquip' + site;
	var element = document.getElementById(chartId);
	if (!element) return;
	var chart = echarts.init(element, 'acxCockpit');
	chartInstances[chartId] = chart;
	chart.setOption({
		color: ['#249c73', '#b9c3cf'],
		tooltip: { trigger: 'item', formatter: function(item) { return item.name + ': ' + item.value + ' 台 (' + item.percent + '%)'; } },
		legend: { data: ['开机', '未开机'], bottom: 0, left: 'center', itemWidth: 7, itemHeight: 7, itemGap: 8, icon: 'circle', textStyle: { color: '#637184', fontSize: 10 } },
		graphic: [{ id: 'equipment-total', type: 'text', left: 'center', top: '34%', style: { text: '--\n设备总数', align: 'center', fill: '#202b38', fontSize: 15, lineHeight: 21 } }],
		series: [{ name: site, type: 'pie', radius: ['49%', '70%'], center: ['50%', '44%'],
			label: { show: false }, labelLine: { show: false }, stillShowZeroSum: false,
			emptyCircleStyle: { color: '#eef1f5' }, itemStyle: { borderWidth: 2, borderColor: '#ffffff' }, data: [] }]
	});
});

/* SECTION: chart-dashboard-quality */
(function() {
	var el = document.getElementById('dashQuality');
	if (!el) return;
	var c = echarts.init(el, 'acxCockpit');
	chartInstances['dashQuality'] = c;
	c.setOption({
		tooltip: { trigger:'axis', backgroundColor:'rgba(10,22,40,0.95)', borderColor:'rgba(0,212,255,0.2)', textStyle:{color:'#e0e6ed',fontSize:12} },
		grid: { top:'8%', bottom:'8%', left:'20%', right:'10%', containLabel:true },
		xAxis: { type:'value', splitLine:{lineStyle:{color:'rgba(255,255,255,0.04)'}}, axisLabel:{color:'#6b7b8d',fontSize:11} },
		yAxis: { type:'category', data:['材质问题','包装破损','功能异常','尺寸偏差','外观瑕疵'],
			axisLine:{lineStyle:{color:'rgba(255,255,255,0.08)'}}, axisLabel:{color:'#a0b4c8',fontSize:11} },
		series: [{ type:'bar', barWidth:14,
			data:[7,12,18,28,35].map(function(v){return {value:v,itemStyle:{color:{type:'linear',x:0,y:0,x2:1,y2:0,colorStops:[{offset:0,color:'rgba(255,77,79,0.15)'},{offset:1,color:'#ff4d4f'}]},borderRadius:[0,3,3,0]}};}),
			label:{show:true,position:'right',color:'#a0b4c8',fontSize:11}
		}]
	});
})();

/* SECTION: dashboard-alarms */
(function() {
	var alarms = [
		{time:'09:58',level:'red',msg:'C线 #3 注塑机温度超限 (105°C)'},
		{time:'09:52',level:'orange',msg:'B线包装工位堆料，等待处理'},
		{time:'09:45',level:'green',msg:'A线换模完成，已恢复生产'},
		{time:'09:38',level:'orange',msg:'D线物料库存低于安全水位'},
		{time:'09:30',level:'red',msg:'E线 #1 冲压设备异常停机'},
		{time:'09:22',level:'green',msg:'质检抽检合格，批次 BT-1014 放行'}
	];
	var html = '';
	for (var i = 0; i < alarms.length; i++) {
		var a = alarms[i];
		html += '<li><span class="alarm-dot '+a.level+'"></span><span class="alarm-time">'+a.time+'</span><span class="alarm-msg">'+a.msg+'</span></li>';
	}
	var el = document.getElementById('dashAlarms');
	if (el) el.innerHTML = html;
})();

/* SECTION: cockpit-chart-style */
(function() {
	var axisLabel = { color: '#91a7b3', fontSize: 10 };
	var splitLine = { lineStyle: { color: 'rgba(147,179,193,0.08)', type: 'dashed' } };
	var tooltip = { backgroundColor: '#19262f', borderColor: '#344e5b', padding: [9, 12], textStyle: { color: '#e8f0f3', fontSize: 12 }, extraCssText: 'box-shadow:0 6px 24px #0005;border-radius:4px;' };
	Object.keys(chartInstances).forEach(function(chartId) {
		chartInstances[chartId].setOption({ tooltip: tooltip });
	});
	chartInstances.dashTrend.setOption({
		legend: { top: 4, bottom: 'auto', right: 0, left: 'auto', icon: 'rect', itemWidth: 10, itemHeight: 8, textStyle: { color: '#9aadb8', fontSize: 10 } },
		grid: { top: 36, bottom: 8, left: 0, right: 12, containLabel: true },
		xAxis: { axisLabel: Object.assign({}, axisLabel, { interval: 0, fontSize: 9 }), axisTick: { show: false } },
		yAxis: { name: '米', nameTextStyle: { color: '#91a7b3', fontSize: 10 }, axisLabel: Object.assign({}, axisLabel, { formatter: function(value) { return Math.abs(value) >= 10000 ? Number((value / 10000).toFixed(1)) + '万' : String(value); } }), splitLine: splitLine }
	});
	chartInstances.dashLines.setOption({
		grid: { top: 12, bottom: 8, left: 0, right: 58, containLabel: true },
		xAxis: { name: '米', nameGap: 12, nameTextStyle: { color: '#91a7b3', fontSize: 10 }, axisLabel: axisLabel, splitLine: splitLine },
		yAxis: { axisTick: { show: false }, axisLine: { show: false }, axisLabel: { color: '#b3c5cd', fontSize: 11 } },
		series: [{ barWidth: 12, showBackground: true, backgroundStyle: { color: '#ffffff04', borderRadius: 2 }, label: { color: '#c5d5dd' } }]
	});
	chartInstances.dashQuality.setOption({
		grid: { top: 12, bottom: 8, left: 0, right: 28, containLabel: true },
		xAxis: { axisLabel: axisLabel, splitLine: splitLine },
		yAxis: { axisTick: { show: false }, axisLine: { show: false }, axisLabel: { color: '#aabfc9', fontSize: 10 } },
		series: [{ barWidth: 10, label: { color: '#c5d5dd' }, data: [7, 12, 18, 28, 35].map(function(value, index) { return { value: value, itemStyle: { color: ['#516d7c', '#698794', '#9caeaa', '#efbd68', '#f27b83'][index], borderRadius: [0, 2, 2, 0] } }; }) }]
	});
	var sparkElement = document.getElementById('sparkOutput');
	if (sparkElement) {
		var spark = echarts.init(sparkElement, 'acxCockpit');
		chartInstances.sparkOutput = spark;
		spark.setOption({ grid: { top: 3, bottom: 1, left: 0, right: 0 }, xAxis: { type: 'category', show: false, boundaryGap: false, data: ['10/08', '10/09', '10/10', '10/11', '10/12', '10/13', '10/14'] }, yAxis: { type: 'value', show: false, min: 10000 }, series: [{ type: 'line', smooth: true, symbol: 'none', data: [11200, 12450, 11800, 13100, 12680, 12450, 12846], lineStyle: { color: '#50d9e8', width: 1.5 }, areaStyle: { color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [{ offset: 0, color: '#50d9e825' }, { offset: 1, color: '#50d9e800' }]) } }] });
	}
})();

/* SECTION: fullscreen */
(function() {
	var button = document.getElementById('dashboardFullscreen');
	if (!button) return;
	if (!document.fullscreenEnabled) { button.hidden = true; return; }
	button.addEventListener('click', function() {
		var action = document.fullscreenElement ? document.exitFullscreen() : document.documentElement.requestFullscreen();
		action.catch(function() { button.title = '浏览器暂不允许全屏'; });
	});
	document.addEventListener('fullscreenchange', function() {
		var active = Boolean(document.fullscreenElement);
		button.setAttribute('aria-pressed', String(active));
		button.setAttribute('aria-label', active ? '退出全屏' : '进入全屏');
		button.title = active ? '退出全屏' : '进入全屏';
		resizeDashboardCharts();
	});
})();

/* SECTION: resize */
function resizeDashboardCharts() {
	Object.keys(chartInstances).forEach(function(chartId) {
		if (chartInstances[chartId] && chartInstances[chartId].resize) chartInstances[chartId].resize();
	});
}

window.addEventListener('resize', resizeDashboardCharts);
var dashboardResizeObserver = new ResizeObserver(resizeDashboardCharts);
Object.keys(chartInstances).forEach(function(chartId) {
	dashboardResizeObserver.observe(chartInstances[chartId].getDom());
});
