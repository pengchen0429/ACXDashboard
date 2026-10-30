(function() {
  var card = document.getElementById('safety-kpi');
  if (!card) return;
  var reported = document.getElementById('safety-reported');
  var details = document.getElementById('safety-details');
  var form = document.getElementById('safety-time-filter');
  var startInput = document.getElementById('safety-start');
  var endInput = document.getElementById('safety-end');
  var defaultButton = document.getElementById('safety-time-default');
  var activeController = null;
  var dpmuController = null;
  var improvementController = null;

  function renderDispatchCounts(result, reportedElement, detailsElement) {
    if (!result.available || !Number.isInteger(result.reported) || result.reported < 0 ||
        !Number.isInteger(result.completed) || result.completed < 0 ||
        !Number.isInteger(result.unclosed) || result.unclosed < 0 || !Array.isArray(result.areas)) {
      throw new Error('Invalid dispatch response');
    }
    var rows = result.areas.map(function(area) {
      if (typeof area.label !== 'string' ||
          !Number.isInteger(area.reported) || area.reported < 0 ||
          !Number.isInteger(area.completed) || area.completed < 0 ||
          !Number.isInteger(area.unclosed) || area.unclosed < 0) {
        throw new Error('Invalid area response');
      }
      var row = document.createElement('div');
      row.className = 'safety-area-row';
      row.dataset.label = area.label;
      var name = document.createElement('span');
      name.className = 'safety-area-name';
      name.textContent = area.label;
      var metrics = document.createElement('span');
      metrics.className = 'safety-area-metrics';
      [
        {key: 'reported', label: '新增', suffix: ' 起，'},
        {key: 'completed', label: '完成', suffix: ' 起，'},
        {key: 'unclosed', label: '未关闭', suffix: ' 起'}
      ].forEach(function(metric) {
        var group = document.createElement('span');
        group.className = 'safety-area-metric';
        var value = document.createElement('strong');
        value.className = 'safety-area-' + metric.key;
        value.textContent = area[metric.key];
        group.append(metric.label + ' ', value, metric.suffix);
        metrics.append(group);
      });
      row.append(name, ' ', metrics);
      return row;
    });
    reportedElement.textContent = result.reported;
    detailsElement.replaceChildren.apply(detailsElement, rows);
  }

  async function loadImprovement(start, end) {
    var improvementCard = document.getElementById('improvement-kpi');
    if (!improvementCard) return;
    if (improvementController) improvementController.abort();
    var controller = new AbortController();
    improvementController = controller;
    var timer = setTimeout(function() { controller.abort(); }, 35000);
    var reportedElement = document.getElementById('improvement-reported');
    var detailsElement = document.getElementById('improvement-details');
    improvementCard.setAttribute('aria-busy', 'true');
    reportedElement.textContent = '--';
    detailsElement.querySelectorAll('strong').forEach(function(value) { value.textContent = '--'; });
    var url = new URL(improvementCard.dataset.url, window.location.href);
    url.searchParams.set('start_time', start);
    url.searchParams.set('end_time', end);
    url.searchParams.set('include_trend', '1');
    clearTrendChart('chartImprovement', start, end);
    try {
      var response = await fetch(url, {signal: controller.signal, credentials: 'same-origin', cache: 'no-store'});
      if (!response.ok) throw new Error('Improvement request failed');
      var result = await response.json();
      if (improvementController !== controller) return;
      renderDispatchCounts(result, reportedElement, detailsElement);
      updateDispatchTrend(result.trend, improvementChart, 'trend-placeholder');
    } catch (error) {
      if (improvementController !== controller) return;
      console.warn('Unable to load improvement counts', error);
    } finally {
      clearTimeout(timer);
      if (improvementController === controller) {
        improvementCard.setAttribute('aria-busy', 'false');
        improvementController = null;
      }
    }
  }

  async function loadDpmu(start, end) {
    var dpmuCard = document.getElementById('dpmu-kpi');
    if (!dpmuCard) return;
    if (dpmuController) dpmuController.abort();
    var controller = new AbortController();
    dpmuController = controller;
    var timer = setTimeout(function() { controller.abort(); }, 35000);
    var value = document.getElementById('dpmu-value');
    var scrap = document.getElementById('dpmu-scrap');
    var production = document.getElementById('dpmu-production');
    var status = document.getElementById('dpmu-status');
    dpmuCard.setAttribute('aria-busy', 'true');
    value.textContent = scrap.textContent = production.textContent = '--';
    status.textContent = '查询中';
    var url = new URL(dpmuCard.dataset.url, window.location.href);
    url.searchParams.set('start_time', start);
    url.searchParams.set('end_time', end);
    url.searchParams.set('include_trend', '1');
    clearTrendChart('chartDpmu', start, end);
    try {
      var response = await fetch(url, {signal: controller.signal, credentials: 'same-origin', cache: 'no-store'});
      if (!response.ok) throw new Error('DPMU request failed');
      var result = await response.json();
      if (dpmuController !== controller) return;
      if (!result.available || !['production', 'scrap'].every(function(key) {
        return (typeof result[key] === 'string' || typeof result[key] === 'number') &&
          String(result[key]).trim() !== '' && Number.isFinite(Number(result[key]));
      }) || !(result.dpmu === null ||
          ((typeof result.dpmu === 'string' || typeof result.dpmu === 'number') &&
          String(result.dpmu).trim() !== '' && Number.isFinite(Number(result.dpmu))))) {
        throw new Error('Invalid DPMU response');
      }
      production.textContent = Number(result.production).toLocaleString('zh-CN', {maximumFractionDigits: 6});
      scrap.textContent = Number(result.scrap).toLocaleString('zh-CN', {maximumFractionDigits: 6});
      value.textContent = result.dpmu === null ? '--' : String(Number(Number(result.dpmu).toPrecision(6)));
      status.textContent = Number(result.production) <= 0 ? '无有效产量' : '';
      updateDpmuTrend(result.trend);
    } catch (error) {
      if (dpmuController !== controller) return;
      value.textContent = scrap.textContent = production.textContent = '--';
      status.textContent = '数据暂不可用';
      console.warn('Unable to load DPMU counts', error);
    } finally {
      clearTimeout(timer);
      if (dpmuController === controller) {
        dpmuCard.setAttribute('aria-busy', 'false');
        dpmuController = null;
      }
    }
  }

  function validateRange() {
    endInput.setCustomValidity(startInput.value && endInput.value &&
      startInput.value > endInput.value ? '结束时间不能早于开始时间' : '');
  }

  async function loadSafety() {
    validateRange();
    if (!form.reportValidity()) return;
    loadDpmu(startInput.value, endInput.value);
    loadImprovement(startInput.value, endInput.value);
    if (activeController) activeController.abort();
    var controller = new AbortController();
    activeController = controller;
    var timer = setTimeout(function() { controller.abort(); }, 35000);
    var url = new URL(card.dataset.url, window.location.href);
    url.searchParams.set('start_time', startInput.value);
    url.searchParams.set('end_time', endInput.value);
    url.searchParams.set('include_trend', '1');
    updateDemoCharts(startInput.value, endInput.value);
    var chartElement = document.getElementById('chartSafety');
    chartElement.dataset.startTime = startInput.value;
    chartElement.dataset.endTime = endInput.value;
    safetyChart.setOption({
      xAxis: {data: []}, series: (safetyChart.getOption().series || []).map(function(series) {
        return {id: series.id, data: []};
      }),
      graphic: [{id: 'safety-chart-placeholder', type: 'text', left: 'center', top: 'middle', invisible: false, style: {text: '--', fill: '#9db8e0', fontSize: 18}}]
    });
    card.setAttribute('aria-busy', 'true');
    reported.textContent = '--';
    details.querySelectorAll('.safety-area-reported, .safety-area-completed, .safety-area-unclosed').forEach(function(value) {
      value.textContent = '--';
    });
    try {
      var response = await fetch(url, {
        signal: controller.signal,
        credentials: 'same-origin',
        cache: 'no-store'
      });
      if (!response.ok) throw new Error('Safety request failed');
      var result = await response.json();
      if (activeController !== controller) return;
      renderDispatchCounts(result, reported, details);
      updateDispatchTrend(result.trend, safetyChart, 'safety-chart-placeholder');
    } catch (error) {
      if (activeController !== controller) return;
      reported.textContent = '--';
      console.warn('Unable to load safety counts', error);
    } finally {
      clearTimeout(timer);
      if (activeController === controller) {
        card.setAttribute('aria-busy', 'false');
        activeController = null;
      }
    }
  }

  form.addEventListener('submit', function(event) {
    event.preventDefault();
    loadSafety();
  });
  startInput.addEventListener('input', validateRange);
  endInput.addEventListener('input', validateRange);
  defaultButton.addEventListener('click', function() {
    form.reset();
    loadSafety();
  });
  queueMicrotask(loadSafety);
})();

var isMobile = window.innerWidth <= 768;

/* ================= 示例数据（可整体替换为真实数据） ================= */
var data = {
  months: ['25-11','25-12','26-01','26-02','26-03','26-04','26-05','26-06','26-07','26-08','26-09','26-10'],
  defectTypes: ['尺寸超差','外观划伤','焊接缺陷','装配错位','包装破损','其他'],
  defectCounts: [42,31,18,12,7,5],
  output: [28.5,30.2,27.8,31.5,33.0,32.4,34.1,33.6,35.2,34.8,36.0,37.2],
  otd: [95.5,94.8,96.2,95.0,96.8,97.1,96.5,97.8,98.0,97.5,98.2,98.6],
  otdTarget: 98,
  cost: [
    { name: '原材料', value: 486 },
    { name: '人工', value: 152 },
    { name: '能源动力', value: 68 },
    { name: '折旧摊销', value: 54 },
    { name: '其他费用', value: 40 }
  ]
};

/* 帕累托累计占比 */
var totalDefects = data.defectCounts.reduce(function(a,b){return a+b;}, 0);
var cum = 0;
var cumPct = data.defectCounts.map(function(v){ cum += v; return +(cum / totalDefects * 100).toFixed(1); });

/* ================= 暗色主题通用配置 ================= */
var AX = { color: '#9db8e0', fontSize: isMobile ? 10 : 11 };
var LEGEND = { show: false };
var SPLIT = { lineStyle: { color: 'rgba(88,140,220,0.15)' } };
var TIP = {
  backgroundColor: 'rgba(10,25,52,0.94)',
  borderColor: 'rgba(64,140,255,0.4)',
  textStyle: { color: '#d7e6ff', fontSize: 12 }
};
function renderChartLegend(chart) {
  var container = document.querySelector('[data-legend-for="' + chart.getDom().id + '"]');
  if (!container) return;
  var option = chart.getOption();
  var selected = option.legend[0].selected || {};
  var entries = [];
  option.series.forEach(function(series, seriesIndex) {
    if (series.type === 'pie') {
      series.data.forEach(function(item, dataIndex) {
        entries.push({name: item.name, color: chart.getVisual({seriesIndex: seriesIndex, dataIndex: dataIndex}, 'color')});
      });
    } else {
      entries.push({name: series.name, color: chart.getVisual({seriesIndex: seriesIndex}, 'color')});
    }
  });
  container.replaceChildren.apply(container, entries.map(function(entry) {
    var button = document.createElement('button');
    button.type = 'button';
    button.setAttribute('aria-pressed', String(selected[entry.name] !== false));
    button.title = entry.name;
    var swatch = document.createElement('span');
    swatch.className = 'chart-legend-swatch';
    swatch.style.backgroundColor = entry.color;
    button.append(swatch, entry.name);
    button.addEventListener('click', function() {
      chart.dispatchAction({type: 'legendToggleSelect', name: entry.name});
      button.setAttribute('aria-pressed', String(chart.getOption().legend[0].selected[entry.name] !== false));
    });
    return button;
  }));
}

var charts = [];
function initChart(id, option) {
  if (option.yAxis) {
    var axes = Array.isArray(option.yAxis) ? option.yAxis : [option.yAxis];
    axes.forEach(function(axis, index) {
      if (!axis.name) return;
      axis.nameGap = 8;
      axis.nameTextStyle = Object.assign({}, axis.nameTextStyle, {
        align: axis.position === 'right' || index > 0 ? 'right' : 'left'
      });
    });
  }
  var c = echarts.init(document.getElementById(id));
  c.setOption(option);
  renderChartLegend(c);
  charts.push(c);
  return c;
}

var safetyChart = initChart('chartSafety', {
  tooltip: Object.assign({ trigger: 'axis', valueFormatter: function(value) { return value + ' 起'; } }, TIP),
  legend: Object.assign({}, LEGEND),
  grid: { top: 22, bottom: 8, left: 8, right: 8, containLabel: true },
  xAxis: { type: 'category', data: [], axisLabel: Object.assign({}, AX, {hideOverlap: true}), axisLine: { lineStyle: { color: 'rgba(88,140,220,0.3)' } } },
  yAxis: { type: 'value', name: '新增(起)', min: 0, minInterval: 1, nameTextStyle: { color: '#7d9cc9', fontSize: 10 }, axisLabel: AX, splitLine: SPLIT },
  graphic: [{id: 'safety-chart-placeholder', type: 'text', left: 'center', top: 'middle', style: {text: '--', fill: '#9db8e0', fontSize: 18}}],
  series: []
});

function updateDispatchTrend(trend, chart, placeholderId) {
  if (!trend || !trend.available || !Array.isArray(trend.points) || !Array.isArray(trend.areas) ||
      !['day', 'month', 'year'].includes(trend.granularity) ||
      trend.points.some(function(point) {
        return typeof point.date !== 'string' || !/^\d{4}-\d{2}-\d{2}$/.test(point.date) ||
          !Number.isInteger(point.reported) || point.reported < 0;
      }) || trend.areas.some(function(area) {
        return typeof area.code !== 'string' || typeof area.label !== 'string' ||
          !Array.isArray(area.points) || area.points.length !== trend.points.length ||
          area.points.some(function(point, index) {
            return point.date !== trend.points[index].date || !Number.isInteger(point.reported) || point.reported < 0;
          });
      })) {
    console.warn('Unable to load safety trend');
    return;
  }
  var colors = {'Weaving Process': '#34d97e', 'Dyeing Process': '#409cff', 'Finishing Process': '#fac858'};
  var palette = ['#34d97e', '#409cff', '#fac858', '#ff9f43', '#5ed4dd'];
  chart.setOption({
    graphic: [{id: placeholderId, invisible: trend.points.length > 0}],
    legend: {data: trend.areas.map(function(area) { return area.label; })},
    xAxis: {data: trend.points.map(function(point) {
      return point.date.slice(0, trend.granularity === 'year' ? 4 : trend.granularity === 'month' ? 7 : 10);
    })},
    series: trend.areas.map(function(area, index) {
      return {
        id: area.code, name: area.label, type: 'bar', barMaxWidth: 22,
        itemStyle: {color: colors[area.code] || palette[index % palette.length], borderRadius: [3,3,0,0]},
        label: {
          show: trend.points.length <= 14, position: 'top', color: '#d7e6ff', fontSize: 10,
          formatter: function(params) { return params.value === 0 ? '' : String(params.value); }
        },
        data: area.points.map(function(point) { return point.reported; })
      };
    })
  }, {replaceMerge: ['series']});
  renderChartLegend(chart);
}

function clearTrendChart(id, start, end) {
  var element = document.getElementById(id);
  element.dataset.startTime = start;
  element.dataset.endTime = end;
  var chart = echarts.getInstanceByDom(element);
  chart.setOption({
    xAxis: {data: []},
    series: (chart.getOption().series || []).map(function(series) { return {id: series.id, data: []}; }),
    graphic: [{id: 'trend-placeholder', invisible: false}]
  });
}

function updateDpmuTrend(trend) {
  if (!trend || !trend.available || !Array.isArray(trend.points) ||
      !['day', 'month', 'year'].includes(trend.granularity) || trend.points.some(function(point) {
        return typeof point.date !== 'string' || !/^\d{4}-\d{2}-\d{2}$/.test(point.date) ||
          !['production', 'scrap'].every(function(key) {
            return (typeof point[key] === 'string' || typeof point[key] === 'number') &&
              String(point[key]).trim() !== '' && Number.isFinite(Number(point[key]));
          }) || !(point.dpmu === null ||
            ((typeof point.dpmu === 'string' || typeof point.dpmu === 'number') &&
            String(point.dpmu).trim() !== '' && Number.isFinite(Number(point.dpmu))));
      })) {
    console.warn('Unable to load DPMU trend');
    return;
  }
  dpmuChart.setOption({
    graphic: [{id: 'trend-placeholder', invisible: trend.points.some(function(point) { return point.dpmu !== null; })}],
    xAxis: {data: trend.points.map(function(point) {
      return point.date.slice(0, trend.granularity === 'year' ? 4 : trend.granularity === 'month' ? 7 : 10);
    })},
    series: [{id: 'dpmu', data: trend.points.map(function(point) {
      return point.dpmu === null ? null : Number(point.dpmu);
    })}]
  });
}

function updateDemoCharts(start, end) {
  var firstMonth = start.slice(0, 7);
  var lastMonth = end.slice(0, 7);
  var indices = data.months.map(function(month, index) {
    var key = '20' + month.slice(0, 2) + '-' + month.slice(3);
    return key >= firstMonth && key <= lastMonth ? index : -1;
  }).filter(function(index) { return index >= 0; });
  var snapshotMonth = '20' + data.months[data.months.length - 1];
  var hasSnapshot = snapshotMonth >= firstMonth && snapshotMonth <= lastMonth;
  function selected(values) {
    return indices.map(function(index) { return values[index]; });
  }
  function apply(id, option, available) {
    var element = document.getElementById(id);
    element.dataset.startTime = start;
    element.dataset.endTime = end;
    option.graphic = (option.graphic || []).concat([{
      id: 'period-placeholder', type: 'text', left: 'center', top: 'middle', invisible: available,
      style: {text: '--', fill: '#9db8e0', fontSize: 18}
    }]);
    echarts.getInstanceByDom(element).setOption(option);
  }
  apply('chartDelivery', {
    xAxis: {data: selected(data.months)},
    series: [{data: selected(data.output)}, {data: selected(data.otd)}]
  }, indices.length > 0);
  apply('chartPareto', {
    xAxis: {data: hasSnapshot ? data.defectTypes : []},
    series: [{data: hasSnapshot ? data.defectCounts : []}, {data: hasSnapshot ? cumPct : []}]
  }, hasSnapshot);
  apply('chartCost', {
    graphic: [{id: 'cost-total', invisible: !hasSnapshot}],
    series: [{data: hasSnapshot ? data.cost : []}]
  }, hasSnapshot);
}

/* ================= Q 质量：缺陷帕累托 ================= */
initChart('chartPareto', {
  tooltip: Object.assign({ trigger: 'axis' }, TIP, {
    formatter: function(params) {
      if (!Array.isArray(params)) return '';
      var s = params[0].axisValue + '<br/>';
      params.forEach(function(p) {
        if (p.componentType !== 'series' || p.value == null) return;
        if (p.seriesName === '累计占比') s += p.marker + p.seriesName + ': ' + Number(p.value).toFixed(1) + '%<br/>';
        else s += p.marker + p.seriesName + ': ' + Number(p.value).toFixed(0) + ' 件<br/>';
      });
      return s;
    }
  }),
  legend: Object.assign({}, LEGEND),
  grid: { top: 22, bottom: 8, left: 8, right: 8, containLabel: true },
  xAxis: { type: 'category', data: data.defectTypes,
           axisLabel: Object.assign({}, AX, { interval: 0, rotate: isMobile ? 30 : 0 }),
           axisLine: { lineStyle: { color: 'rgba(88,140,220,0.3)' } } },
  yAxis: [
    { type: 'value', name: '缺陷数(件)', nameTextStyle: { color: '#7d9cc9', fontSize: 10 }, axisLabel: AX, splitLine: SPLIT },
    { type: 'value', name: '累计(%)', nameTextStyle: { color: '#7d9cc9', fontSize: 10 }, min: 0, max: 108, axisLabel: AX, splitLine: { show: false } }
  ],
  series: [
    { name: '缺陷数量', type: 'bar', yAxisIndex: 0, barMaxWidth: 26,
      itemStyle: { color: '#409cff', borderRadius: [3,3,0,0] },
      label: { show: true, position: 'top', color: '#9ec5ff', fontSize: 10,
               formatter: function(p) { return Number(p.value).toFixed(0); } },
      data: data.defectCounts },
    { name: '累计占比', type: 'line', yAxisIndex: 1, symbol: 'circle', symbolSize: 5,
      itemStyle: { color: '#fac858' }, lineStyle: { width: 2 },
      label: { show: false },
      markLine: { silent: true, symbol: 'none',
        lineStyle: { color: 'rgba(255,107,107,0.7)', type: 'dashed' },
        label: { formatter: '80%线', color: '#ff9b9b', fontSize: 10, position: 'insideEndTop' },
        data: [{ yAxis: 80 }] },
      data: cumPct }
  ]
});

var dpmuChart = initChart('chartDpmu', {
  tooltip: Object.assign({trigger: 'axis', valueFormatter: function(value) {
    return value == null ? '--' : String(Number(Number(value).toPrecision(6)));
  }}, TIP),
  grid: {top: 22, bottom: 8, left: 8, right: 8, containLabel: true},
  xAxis: {type: 'category', data: [], axisLabel: Object.assign({}, AX, {hideOverlap: true})},
  yAxis: {type: 'value', name: 'DPMU', min: 0, axisLabel: AX, splitLine: SPLIT,
    nameTextStyle: {color: '#7d9cc9', fontSize: 10}},
  graphic: [{id: 'trend-placeholder', type: 'text', left: 'center', top: 'middle', style: {text: '--', fill: '#9db8e0', fontSize: 18}}],
  series: [{id: 'dpmu', name: 'DPMU', type: 'line', connectNulls: false, symbol: 'circle', symbolSize: 6,
    itemStyle: {color: '#409cff'}, lineStyle: {width: 2}, data: []}]
});

/* ================= D 交付：产量 + 准时交付率 ================= */
initChart('chartDelivery', {
  tooltip: Object.assign({ trigger: 'axis' }, TIP, {
    formatter: function(params) {
      if (!Array.isArray(params)) return '';
      var s = params[0].axisValue + '<br/>';
      params.forEach(function(p) {
        if (p.componentType !== 'series' || p.value == null) return;
        if (p.seriesName === '准时交付率') s += p.marker + p.seriesName + ': ' + Number(p.value).toFixed(1) + '%<br/>';
        else s += p.marker + p.seriesName + ': ' + Number(p.value).toFixed(1) + ' 万件<br/>';
      });
      return s;
    }
  }),
  legend: Object.assign({}, LEGEND),
  grid: { top: 22, bottom: 8, left: 8, right: 8, containLabel: true },
  xAxis: { type: 'category', data: data.months,
           axisLabel: AX, axisLine: { lineStyle: { color: 'rgba(88,140,220,0.3)' } } },
  yAxis: [
    { type: 'value', name: '产量(万件)', nameTextStyle: { color: '#7d9cc9', fontSize: 10 }, axisLabel: AX, splitLine: SPLIT },
    { type: 'value', name: 'OTD(%)', nameTextStyle: { color: '#7d9cc9', fontSize: 10 }, min: 90, max: 102, axisLabel: AX, splitLine: { show: false } }
  ],
  series: [
    { name: '月度产量', type: 'bar', yAxisIndex: 0, barMaxWidth: 16,
      itemStyle: { color: '#409cff', borderRadius: [3,3,0,0] },
      label: { show: false },
      data: data.output },
    { name: '准时交付率', type: 'line', yAxisIndex: 1, smooth: true, symbol: 'circle', symbolSize: 5,
      itemStyle: { color: '#fac858' }, lineStyle: { width: 2.5 },
      label: { show: true, position: 'top', color: '#f7d774', fontSize: 10,
               formatter: function(p) { return Number(p.value).toFixed(1); } },
      markLine: { silent: true, symbol: 'none',
        lineStyle: { color: 'rgba(255,107,107,0.7)', type: 'dashed' },
        label: { formatter: '目标 98%', color: '#ff9b9b', fontSize: 10, position: 'insideStartTop' },
        data: [{ yAxis: data.otdTarget }] },
      data: data.otd }
  ]
});

/* ================= C 成本：制造成本构成（环形图） ================= */
var costTotal = data.cost.reduce(function(a,b){ return a + b.value; }, 0);
initChart('chartCost', {
  tooltip: Object.assign({ trigger: 'item' }, TIP, {
    formatter: function(p) {
      if (p.componentType !== 'series') return '';
      return p.name + '<br/>金额: ' + Number(p.value).toFixed(0) + ' 万元<br/>占比: ' + Number(p.percent).toFixed(1) + '%';
    }
  }),
  legend: Object.assign({}, LEGEND),
  graphic: [{
    id: 'cost-total',
    type: 'text', left: 'center', top: 'center',
    style: { text: '总计\n' + costTotal + ' 万元', textAlign: 'center', fill: '#e8f2ff', fontSize: isMobile ? 13 : 16, fontWeight: 600 }
  }],
  color: ['#409cff','#34d97e','#fac858','#ff9f43','#b28dff'],
  series: [{
    name: '成本构成', type: 'pie',
    center: ['50%','50%'],
    radius: ['42%','76%'],
    avoidLabelOverlap: true,
    itemStyle: { borderColor: '#0a1934', borderWidth: 2 },
    label: { position: 'inside', formatter: '{d}%', color: '#fff', fontSize: isMobile ? 10 : 12 },
    labelLine: { show: false },
    data: data.cost
  }]
});

var improvementChart = initChart('chartImprovement', {
  tooltip: Object.assign({trigger: 'axis', valueFormatter: function(value) { return value + ' 起'; }}, TIP),
  legend: Object.assign({}, LEGEND),
  grid: {top: 22, bottom: 8, left: 8, right: 8, containLabel: true},
  xAxis: {type: 'category', data: [], axisLabel: Object.assign({}, AX, {hideOverlap: true})},
  yAxis: {type: 'value', name: '新增(起)', min: 0, minInterval: 1, axisLabel: AX, splitLine: SPLIT,
    nameTextStyle: {color: '#7d9cc9', fontSize: 10}},
  graphic: [{id: 'trend-placeholder', type: 'text', left: 'center', top: 'middle', style: {text: '--', fill: '#9db8e0', fontSize: 18}}],
  series: []
});

/* ================= 自适应 ================= */
window.addEventListener('resize', function() {
  var nowMobile = window.innerWidth <= 768;
  if (nowMobile !== isMobile) { location.reload(); return; }
  charts.forEach(function(c) { c.resize(); });
});

var chartGrid = document.querySelector('.chart-grid');
var chartResizeObserver = new ResizeObserver(function() {
  charts.forEach(function(c) { c.resize(); });
});
chartResizeObserver.observe(chartGrid);
