(function () {
'use strict';

var page = document.querySelector('.dpmu-page');
if (!page) return;
var isMobile = page.clientWidth <= 768;

/* ================= 实时时钟 ================= */
function tickClock() {
  var now = new Date();
  document.getElementById('liveClock').textContent =
    String(now.getHours()).padStart(2,'0') + ':' +
    String(now.getMinutes()).padStart(2,'0') + ':' +
    String(now.getSeconds()).padStart(2,'0');
}
tickClock(); setInterval(tickClock, 1000);

var snapshot = null;
var currentTab = 'weaving';
var defectOptions = [];
var queryButton = document.getElementById('dpmuQuery');
var status = document.getElementById('dpmuStatus');
var busy = false;
var optionsReady = false;
var optionsVersion = 0;
var confirmedTime = null;

function number(value, maximumFractionDigits) {
  return value == null ? '—' : Number(value).toLocaleString('zh-CN', { maximumFractionDigits: maximumFractionDigits == null ? 0 : maximumFractionDigits });
}

function escapeText(value) {
  return echarts.format.encodeHTML(String(value));
}

/* ================= 暗色主题通用配置 ================= */
var AX = { color: '#9db8e0', fontSize: isMobile ? 10 : 11 };
var SPLIT = { lineStyle: { color: 'rgba(88,140,220,0.15)' } };
var TIP = {
  backgroundColor: 'rgba(10,25,52,0.94)',
  borderColor: 'rgba(64,140,255,0.4)',
  textStyle: { color: '#d7e6ff', fontSize: 12 }
};
function baseTitle(text) {
  return { text: text, left: 'center', top: isMobile ? 4 : 6,
           textStyle: { fontSize: isMobile ? 12 : 13, color: '#e8f2ff', fontWeight: 600 } };
}

/* ================= 图表实例管理 ================= */
var chartInstances = [];
var chartDialog = document.getElementById('dpmuChartDialog');
var expandedChart = null;

function disposeCharts() {
  closeExpandedChart();
  chartInstances.forEach(function(c) { c.dispose(); });
  chartInstances = [];
}

function initChart(id, option) {
  var el = document.getElementById(id);
  if (!el) return;
  var chart = echarts.init(el);
  chart.setOption(option);
  var button = el.parentElement.querySelector('.dpmu-chart-expand');
  if (button) button.setAttribute('aria-label', '放大：' + option.title.text);
  chartInstances.push(chart);
  return chart;
}

function restoreExpandedChart() {
  if (!expandedChart || chartDialog.open) return;
  var previous = expandedChart;
  expandedChart = null;
  previous.placeholder.replaceWith(previous.card);
  document.body.classList.remove('dpmu-chart-open');
  var chart = echarts.getInstanceByDom(previous.element);
  if (chart) chart.resize();
  previous.button.focus({ preventScroll: true });
}

function closeExpandedChart() {
  if (chartDialog.open) chartDialog.close();
  restoreExpandedChart();
}

page.querySelectorAll('#chartGrid .chart-container').forEach(function(element) {
  var card = element.parentElement;
  var button = document.createElement('button');
  button.type = 'button';
  button.className = 'dpmu-chart-expand';
  button.title = '放大图表';
  button.setAttribute('aria-label', '放大图表');
  button.setAttribute('aria-haspopup', 'dialog');
  button.setAttribute('aria-controls', 'dpmuChartDialog');
  var icon = document.createElement('img');
  icon.src = page.dataset.expandIcon;
  icon.alt = '';
  icon.width = 16;
  icon.height = 16;
  button.append(icon);
  card.append(button);
  button.addEventListener('click', function() {
    if (chartDialog.open) return;
    var placeholder = document.createElement('div');
    placeholder.className = 'card dpmu-chart-placeholder';
    placeholder.style.height = card.getBoundingClientRect().height + 'px';
    placeholder.style.order = card.style.order;
    placeholder.setAttribute('aria-hidden', 'true');
    expandedChart = { element: element, card: card, placeholder: placeholder, button: button };
    card.replaceWith(placeholder);
    chartDialog.append(card);
    chartDialog.setAttribute('aria-label', button.getAttribute('aria-label').replace('放大：', ''));
    document.body.classList.add('dpmu-chart-open');
    chartDialog.showModal();
    var chart = echarts.getInstanceByDom(element);
    if (chart) chart.resize();
  });
});
chartDialog.querySelector('.dpmu-chart-close').addEventListener('click', closeExpandedChart);
chartDialog.addEventListener('cancel', function(event) {
  event.preventDefault();
  closeExpandedChart();
});
chartDialog.addEventListener('keydown', function(event) {
  if (event.key === 'Escape') {
    event.preventDefault();
    closeExpandedChart();
  }
});
chartDialog.addEventListener('close', restoreExpandedChart);
chartDialog.addEventListener('click', function(event) {
  if (event.target !== chartDialog) return;
  var rect = chartDialog.getBoundingClientRect();
  if (event.clientX < rect.left || event.clientX > rect.right || event.clientY < rect.top || event.clientY > rect.bottom) {
    closeExpandedChart();
  }
});

/* ================= 图表构建函数 ================= */

/* 垂直柱状图 */
function barOpt(title, cats, vals, color, unit) {
  var u = unit || '';
  function formatValue(value) { return number(value, title.indexOf('DPMU') === -1 ? 6 : 0); }
  return {
    title: baseTitle(title),
    tooltip: Object.assign({ trigger: 'axis' }, TIP, {
      formatter: function(params) {
        if (!Array.isArray(params)) return '';
        if (!params.length) return '';
        var s = escapeText(params[0].axisValue) + '<br/>';
        params.forEach(function(p) {
          if (p.componentType !== 'series' || p.value == null) return;
          s += p.marker + escapeText(p.seriesName) + ': ' + formatValue(p.value) + u + '<br/>';
        });
        return s;
      }
    }),
    grid: { top: isMobile ? '16%' : '18%', bottom: '12%', left: '3%', right: '3%', containLabel: true },
    xAxis: { type: 'category', data: cats,
             axisLabel: Object.assign({}, AX, { interval: 0, width: 65, overflow: 'truncate', rotate: cats.length > 6 ? 25 : 0 }),
             axisLine: { lineStyle: { color: 'rgba(88,140,220,0.3)' } } },
    yAxis: { type: 'value', axisLabel: Object.assign({}, AX, { formatter: formatValue }), splitLine: SPLIT },
    series: [{
      name: title.replace(/各|DPMU|趋势|占自身产量/g,'').trim() || 'DPMU',
      type: 'bar', barMaxWidth: 26,
      itemStyle: { color: color || '#409cff', borderRadius: [3,3,0,0] },
      label: { show: true, position: 'top', color: '#9ec5ff', fontSize: 10,
               formatter: function(p) { return formatValue(p.value); } },
      data: vals
    }]
  };
}

/* 水平柱状图 */
function hbarOpt(title, cats, vals, color, unit) {
  var u = unit || '';
  return {
    title: baseTitle(title),
    tooltip: Object.assign({ trigger: 'axis' }, TIP, {
      formatter: function(params) {
        if (!Array.isArray(params)) return '';
        if (!params.length) return '';
        var p = params[0];
        if (p.componentType !== 'series' || p.value == null) return '';
        var text = escapeText(p.name) + '<br/>' + p.marker + 'DPMU: ' + number(p.value) + u;
        if (p.data && p.data.scrap != null) {
          text += '<br/>报废米数: ' + number(p.data.scrap, 6) + ' 米';
        }
        return text;
      }
    }),
    grid: { top: isMobile ? '16%' : '18%', bottom: '6%', left: '3%', right: '22%', containLabel: true },
    xAxis: { type: 'value', axisLabel: Object.assign({}, AX, { formatter: function(value) { return number(value); } }), splitLine: SPLIT },
    yAxis: { type: 'category', data: cats, inverse: true,
             axisLabel: Object.assign({}, AX, { width: 70, overflow: 'truncate' }),
             axisLine: { lineStyle: { color: 'rgba(88,140,220,0.3)' } } },
    series: [{
      name: 'DPMU', type: 'bar', barMaxWidth: 16,
      itemStyle: { color: color || '#409cff', borderRadius: [0,3,3,0] },
      label: { show: true, position: 'right', color: '#9ec5ff', fontSize: 10,
               formatter: function(p) { return number(p.value); } },
      data: vals
    }]
  };
}

/* 折线图 */
function lineOpt(title, months, vals, target, color, unit) {
  var c = color || '#b28dff';
  var u = unit || '';
  var opt = {
    title: baseTitle(title),
    tooltip: Object.assign({ trigger: 'axis' }, TIP, {
      formatter: function(params) {
        if (!Array.isArray(params)) return '';
        if (!params.length) return '';
        var s = escapeText(params[0].axisValue) + '<br/>';
        params.forEach(function(p) {
          if (p.componentType !== 'series' || p.value == null || !isFinite(p.value)) return;
          s += p.marker + escapeText(p.seriesName) + ': ' + number(p.value) + u + '<br/>';
        });
        return s;
      }
    }),
    legend: { show: false },
    grid: { top: isMobile ? '16%' : '18%', bottom: '12%', left: '3%', right: '3%', containLabel: true },
    xAxis: { type: 'category', boundaryGap: false, data: months, axisLabel: AX,
             axisLine: { lineStyle: { color: 'rgba(88,140,220,0.3)' } } },
    yAxis: { type: 'value', axisLabel: Object.assign({}, AX, { formatter: function(value) { return number(value); } }), splitLine: SPLIT },
    series: [{
      name: 'DPMU', type: 'line', smooth: true, symbol: 'circle', symbolSize: 4,
      itemStyle: { color: c }, lineStyle: { width: 2.5 },
      areaStyle: { color: new echarts.graphic.LinearGradient(0,0,0,1,
        [{ offset:0, color: c.replace(')', ',0.3)').replace('rgb','rgba') },
         { offset:1, color: c.replace(')', ',0.02)').replace('rgb','rgba') }]) },
      label: { show: false },
      data: vals
    }]
  };
  if (target != null) {
    opt.series[0].markLine = {
      silent: true, symbol: 'none',
      lineStyle: { color: 'rgba(250,200,88,0.8)', type: 'dashed' },
      label: { formatter: '目标 ' + target, color: '#fac858', fontSize: 10, position: 'insideStartTop' },
      data: [{ yAxis: target }]
    };
  }
  return opt;
}

/* 仪表盘 */
function gaugeOpt(title, value, maxVal) {
  return {
    title: baseTitle(title),
    series: [{
      type: 'gauge',
      startAngle: 200, endAngle: -20,
      min: 0, max: maxVal || 5000,
      splitNumber: 5,
      radius: '78%', center: ['50%','58%'],
      axisLine: {
        lineStyle: {
          width: 18,
          color: [[0.3,'#34d97e'],[0.6,'#fac858'],[1,'#ff6b6b']]
        }
      },
      pointer: { width: 4, length: '55%', itemStyle: { color: '#e8f2ff' } },
      axisTick: { distance: -18, length: 5, lineStyle: { color: 'rgba(157,184,224,0.5)', width: 1 } },
      splitLine: { distance: -22, length: 12, lineStyle: { color: 'rgba(157,184,224,0.5)', width: 2 } },
      axisLabel: { distance: 26, color: '#7d9cc9', fontSize: isMobile ? 9 : 10, formatter: function(value) { return number(value); } },
      anchor: { show: true, size: 10, itemStyle: { color: '#409cff', borderColor: '#e8f2ff', borderWidth: 2 } },
      title: { show: false },
      detail: {
        valueAnimation: false, formatter: function() { return number(value); },
        color: '#e8f2ff', fontSize: isMobile ? 26 : 34, fontWeight: 700,
        offsetCenter: [0, '35%']
      },
      data: [{ value: value == null ? 0 : value }]
    }]
  };
}

function weavingGaugeOpt(value) {
  var threshold = 8600;
  var maximum = Math.max(threshold * 2, Math.ceil((value || 0) / threshold) * threshold);
  var color = value == null ? '#7d9cc9' : value > threshold ? '#ff6b6b' : '#34d97e';
  var option = gaugeOpt('DPMU TOTAL', value, maximum);
  var series = option.series[0];
  series.startAngle = 180;
  series.endAngle = 0;
  series.center = ['50%', '59%'];
  series.radius = '82%';
  series.splitNumber = maximum / threshold;
  series.axisLine.lineStyle.width = 12;
  series.axisLine.lineStyle.color = [[threshold / maximum, '#34d97e'], [1, '#ff6b6b']];
  series.axisTick.show = false;
  series.splitLine.show = false;
  series.axisLabel = {
    distance: 18, color: '#64748b', fontSize: 11,
    formatter: function(tick) { return tick === 0 || tick === maximum ? number(tick) : ''; }
  };
  series.pointer.show = value != null;
  series.pointer.width = 3;
  series.pointer.length = '72%';
  series.pointer.itemStyle.color = color;
  series.anchor.size = 7;
  series.anchor.itemStyle.color = color;
  series.detail.color = color;
  series.detail.fontSize = isMobile ? 32 : 38;
  series.detail.offsetCenter = [0, '27%'];
  series.title = {
    show: true, offsetCenter: [0, '62%'],
    rich: {
      label: { color: '#64748b', fontSize: 12, fontWeight: 400 },
      value: { color: '#334155', fontSize: 16, fontWeight: 700 }
    }
  };
  series.data = [{ value: value == null ? 0 : value, name: '{label|临界值}  {value|8,600}' }];
  return option;
}

/* 带产量标注的柱状图 */
function barWithProdOpt(title, cats, dpmuVals, prodVals, color, prodUnit) {
  var pu = prodUnit || '原始数量';
  return {
    title: baseTitle(title),
    tooltip: Object.assign({ trigger: 'axis' }, TIP, {
      formatter: function(params) {
        if (!Array.isArray(params)) return '';
        if (!params.length) return '';
        var s = escapeText(params[0].axisValue) + '<br/>';
        params.forEach(function(p) {
          if (p.componentType !== 'series' || p.value == null) return;
          s += p.marker + escapeText(p.seriesName) + ': ' + number(p.value, p.seriesName === 'DPMU' ? 0 : 6) + '<br/>';
        });
        return s;
      }
    }),
    legend: { bottom: 0, left: 'center', textStyle: AX, itemWidth: 14 },
    grid: { top: isMobile ? '16%' : '18%', bottom: '18%', left: '3%', right: '3%', containLabel: true },
    xAxis: { type: 'category', data: cats,
             axisLabel: Object.assign({}, AX, { interval: 0, width: 55, overflow: 'truncate', rotate: cats.length > 5 ? 20 : 0 }),
             axisLine: { lineStyle: { color: 'rgba(88,140,220,0.3)' } } },
    yAxis: [
      { type: 'value', name: 'DPMU', nameTextStyle: { color: '#7d9cc9', fontSize: 10 }, axisLabel: Object.assign({}, AX, { formatter: function(value) { return number(value); } }), splitLine: SPLIT },
      { type: 'value', name: '产量(' + pu + ')', nameTextStyle: { color: '#7d9cc9', fontSize: 10 }, axisLabel: AX, splitLine: { show: false } }
    ],
    series: [
      { name: 'DPMU', type: 'bar', yAxisIndex: 0, barMaxWidth: 22,
        itemStyle: { color: color || '#409cff', borderRadius: [3,3,0,0] },
        label: { show: cats.length <= 6, position: 'top', color: '#9ec5ff', fontSize: 10,
                 formatter: function(p) { return number(p.value); } },
        data: dpmuVals },
      { name: '产量(' + pu + ')', type: 'bar', yAxisIndex: 1, barMaxWidth: 22,
        itemStyle: { color: 'rgba(250,200,88,0.5)', borderRadius: [3,3,0,0] },
        label: { show: false },
        data: prodVals }
    ]
  };
}

/* ================= Tab 构建函数 ================= */

function weavingMonthlyOpt(rows) {
  var option = barOpt('月DPMU环比', rows.map(function(row) { return row.name; }),
    rows.map(function(row) { return row.dpmu; }), '#409cff');
  option.series[0].name = '本月';
  option.series[0].label.show = rows.length <= 6;
  option.series.push(Object.assign({}, option.series[0], {
    name: '上月同期', data: rows.map(function(row) { return row.previous_dpmu; }),
    itemStyle: { color: '#34d97e', borderRadius: [3,3,0,0] }
  }));
  option.legend = { show: true, top: 28, left: 'center', textStyle: AX, itemWidth: 14 };
  option.grid.top = 58;
  option.tooltip.formatter = function(params) {
    if (!Array.isArray(params) || !params.length) return '';
    var row = rows[params[0].dataIndex];
    if (!row) return '';
    return escapeText(row.name) + '<br/>本月 DPMU: ' + number(row.dpmu)
      + '<br/>' + escapeText(row.previous_month) + ' DPMU: ' + number(row.previous_dpmu)
      + '<br/>环比: ' + (row.change_percent == null ? '—' : number(row.change_percent, 2) + '%');
  };
  return option;
}

function weavingDailyOpt(rows) {
  var option = lineOpt('每日DPMU趋势', rows.map(function(row) { return row.name; }),
    rows.map(function(row) { return row.dpmu; }), null, '#409cff');
  option.tooltip.formatter = function(params) {
    if (!Array.isArray(params) || !params.length) return '';
    var row = rows[params[0].dataIndex];
    if (!row) return '';
    return escapeText(row.name) + '<br/>DPMU: ' + number(row.dpmu)
      + '<br/>报废数量: ' + number(row.scrap, 6) + ' 米'
      + '<br/>产量: ' + number(row.production, 6) + ' 米';
  };
  option.series[0].smooth = false;
  delete option.series[0].areaStyle;
  if (rows.length > 20) {
    option.dataZoom = [{ type: 'inside' }, { type: 'slider', height: 14, bottom: 0 }];
    option.grid.bottom = 44;
  }
  return option;
}

function weavingProductsOpt(rows) {
  var option = barOpt('各带型DPMU', rows.map(function(row) { return row.name; }),
    rows.map(function(row) { return row.dpmu; }), '#34d97e');
  option.tooltip.formatter = function(params) {
    if (!Array.isArray(params) || !params.length) return '';
    var row = rows[params[0].dataIndex];
    if (!row) return '';
    return escapeText(row.name) + '<br/>DPMU: ' + number(row.dpmu)
      + '<br/>报废米数: ' + number(row.scrap, 6) + ' 米'
      + '<br/>带型产量: ' + number(row.production, 6) + ' 米';
  };
  if (rows.length > 8) {
    option.dataZoom = [{ type: 'inside' }, { type: 'slider', height: 14, bottom: 0, startValue: 0, endValue: 7 }];
    option.grid.bottom = 56;
  }
  return option;
}

function renderCharts(message) {
  disposeCharts();
  var weaving = currentTab === 'weaving';
  var weavingOrder = { chart5: 0, chart2: 1, chart3: 2, chart4: 3, chart8: 4 };
  page.querySelectorAll('#chartGrid > .card').forEach(function(card) {
    var id = card.querySelector('.chart-container').id;
    card.hidden = weaving && weavingOrder[id] == null;
    card.style.order = weaving && weavingOrder[id] != null ? String(weavingOrder[id]) : '';
  });
  if (!snapshot) {
    for (var index = 1; index <= 9; index++) {
      if (weaving && weavingOrder['chart' + index] == null) continue;
      initChart('chart' + index, weaving && index === 2 ? weavingGaugeOpt(null) : { title: baseTitle(message || '待查询') });
    }
    return;
  }
  var d = snapshot;
  var scope = { overview: '总览', weaving: '织造', dyeing: '染色' }[d.filters.tab];
  function topDpmu(rows, count) {
    return rows.slice().sort(function(first, second) {
      if (first.dpmu == null) return second.dpmu == null ? 0 : 1;
      if (second.dpmu == null) return -1;
      return second.dpmu - first.dpmu;
    }).slice(0, count == null ? 10 : count);
  }
  function values(rows, key) { return rows.map(function(row) { return row[key]; }); }
  if (weaving) {
    var weavingDefects = topDpmu(d.weaving_defects);
    var weavingOption = hbarOpt('疵点名称DPMU', values(weavingDefects, 'name'), values(weavingDefects, 'dpmu'), '#fac858');
    weavingOption.series[0].data = weavingDefects.map(function(row) {
      return { value: row.dpmu, scrap: row.scrap };
    });
    initChart('chart5', weavingOption);
    initChart('chart2', weavingGaugeOpt(d.weaving_total.dpmu));
    initChart('chart3', weavingMonthlyOpt(d.weaving_months));
    initChart('chart4', weavingDailyOpt(d.weaving_days));
    initChart('chart8', weavingProductsOpt(topDpmu(d.weaving_products, d.weaving_products.length)));
    return;
  }
  var areas = d.areas.slice(0, 10);
  var lines = topDpmu(d.lines);
  var products = topDpmu(d.products);
  var categories = d.categories.slice(0, 10);
  var defects = topDpmu(d.defects);
  initChart('chart1', barOpt('各区域 DPMU', values(areas, 'name'), values(areas, 'dpmu'), '#409cff'));
  initChart('chart2', gaugeOpt(scope + ' DPMU TOTAL', d.total.dpmu, Math.max(0.1, (d.total.dpmu || 0) * 2)));
  initChart('chart3', lineOpt('各月 DPMU 趋势', values(d.months, 'name'), values(d.months, 'dpmu'), null, '#b28dff'));
  initChart('chart4', hbarOpt('产线 DPMU（前10）', values(lines, 'name'), values(lines, 'dpmu'), '#34d97e'));
  initChart('chart5', hbarOpt('疵点 DPMU（前10）', values(defects, 'name'), values(defects, 'dpmu'), '#fac858'));
  initChart('chart6', barOpt('报废数量（月度）', values(d.months, 'name'), values(d.months, 'scrap'), '#ff6b6b'));
  initChart('chart7', barOpt('产量（月度）', values(d.months, 'name'), values(d.months, 'production'), '#ff9f43'));
  initChart('chart8', barOpt('产品 DPMU（前10）', values(products, 'name'), values(products, 'dpmu'), '#409cff'));
  initChart('chart9', hbarOpt('疵点分类DPMU', values(categories, 'name'), values(categories, 'dpmu'), '#b28dff'));
}

function multiSelect(id, onChange, onComplete) {
  var root = document.getElementById(id);
  var search = root.querySelector('input[type="search"]');
  var list = root.querySelector('.dpmu-multi-options');
  var summary = root.querySelector('summary');
  var selected = new Set();
  var options = [];
  var dirty = false;

  function matching() {
    var term = search.value.trim().toLocaleLowerCase();
    return options.filter(function(value) { return value.toLocaleLowerCase().includes(term); });
  }
  function updateLabel() {
    summary.textContent = selected.size ? '已选 ' + selected.size + ' 项' : '全部';
    summary.title = selected.size ? Array.from(selected).join('、') : '全部';
    root.querySelector('.dpmu-multi-count').textContent = '已选 ' + selected.size + ' / ' + options.length;
  }
  function render() {
    list.replaceChildren();
    var visible = matching();
    visible.forEach(function(value) {
      var label = document.createElement('label');
      label.className = 'dpmu-multi-option';
      var checkbox = document.createElement('input');
      checkbox.type = 'checkbox';
      checkbox.value = value;
      checkbox.checked = selected.has(value);
      var text = document.createElement('span');
      text.textContent = value;
      label.append(checkbox, text);
      checkbox.addEventListener('change', function() {
        if (checkbox.checked) selected.add(value);
        else selected.delete(value);
        dirty = true;
        updateLabel();
        if (onChange) onChange();
      });
      list.append(label);
    });
    if (!visible.length) list.textContent = options.length ? '无匹配项' : '暂无选项';
    updateLabel();
  }
  search.addEventListener('input', render);
  root.querySelector('[data-action="all"]').addEventListener('click', function() {
    matching().forEach(function(value) { selected.add(value); });
    dirty = true;
    render();
    if (onChange) onChange();
  });
  function reset(silent) {
    selected.clear();
    search.value = '';
    render();
    dirty = silent !== true;
    if (silent !== true && onChange) onChange();
  }
  root.querySelector('[data-action="reset"]').addEventListener('click', reset);
  root.querySelector('[data-action="confirm"]').addEventListener('click', function() { root.open = false; });
  root.addEventListener('toggle', function() {
    if (!root.open) {
      if (dirty && onComplete) {
        dirty = false;
        onComplete();
      }
      return;
    }
    page.querySelectorAll('.dpmu-multi').forEach(function(other) {
      if (other !== root) other.open = false;
    });
    search.focus();
  });
  root.addEventListener('keydown', function(event) {
    if (event.key === 'Escape') {
      root.open = false;
      summary.focus();
    }
  });
  return {
    values: function() { return Array.from(selected); },
    commit: function() { dirty = false; root.open = false; },
    setLoading: function(message) {
      list.textContent = message;
      root.querySelectorAll('input, button').forEach(function(control) { control.disabled = true; });
      root.setAttribute('aria-busy', 'true');
    },
    setOptions: function(values) {
      options = Array.from(new Set(values)).sort();
      selected = new Set(Array.from(selected).filter(function(value) { return options.includes(value); }));
      render();
      root.querySelectorAll('input, button').forEach(function(control) { control.disabled = false; });
      root.setAttribute('aria-busy', 'false');
    },
    reset: reset
  };
}

var categorySelect = multiSelect('dpmuCategory', function() {
  optionsReady = false;
  defectSelect.setLoading('请先确认疵点分类');
}, loadOptions);
var defectSelect = multiSelect('dpmuDefect', function() { optionsReady = false; }, loadOptions);

function filterParameters() {
  var start = document.getElementById('dpmuStartTime').value;
  var end = document.getElementById('dpmuEndTime').value;
  if (!confirmedTime || page.querySelector('.dpmu-time-range').classList.contains('is-pending')
      || start !== confirmedTime.start || end !== confirmedTime.end) return null;
  var params = new URLSearchParams({ start_time: confirmedTime.start, end_time: confirmedTime.end, tab: currentTab });
  [['category', categorySelect], ['defect', defectSelect]].forEach(function(pair) {
    pair[1].values().forEach(function(value) { params.append(pair[0], value); });
  });
  return params;
}

document.addEventListener('click', function(event) {
  page.querySelectorAll('.dpmu-multi[open]').forEach(function(root) {
    if (!root.contains(event.target)) root.open = false;
  });
});

async function fetchJSON(url, params) {
  var controller = new AbortController();
  var timer = setTimeout(function() { controller.abort(); }, 60000);
  try {
    var response = await fetch(url + (params ? '?' + params.toString() : ''), {
      signal: controller.signal, credentials: 'same-origin', headers: { Accept: 'application/json' }
    });
    if (response.redirected || !(response.headers.get('Content-Type') || '').includes('application/json')) {
      throw new Error('登录状态或访问权限已变更，请刷新页面。');
    }
    var data = await response.json();
    if (!response.ok) throw new Error(data.error || '查询失败，请重试。');
    return data;
  } finally {
    clearTimeout(timer);
  }
}

async function loadOptions() {
  var version = ++optionsVersion;
  optionsReady = false;
  categorySelect.commit();
  defectSelect.commit();
  var params = filterParameters();
  var filterStatus = document.getElementById('dpmuFilterStatus');
  if (!params) {
    categorySelect.setLoading('请先选择有效时间');
    defectSelect.setLoading('请先选择有效时间');
    filterStatus.textContent = '请先确认时间范围';
    queryButton.disabled = false;
    queryButton.textContent = '查 询';
    queryButton.onclick = query;
    return false;
  }
  queryButton.disabled = true;
  queryButton.textContent = '加载筛选项';
  filterStatus.textContent = '正在查询筛选项…';
  categorySelect.setLoading('加载中');
  defectSelect.setLoading('加载中');
  try {
    var data = await fetchJSON(page.dataset.optionsUrl, params);
    if (version !== optionsVersion) return false;
    defectOptions = data.defects;
    categorySelect.setOptions(data.categories.filter(function(category) { return category !== '过程不合格'; }));
    defectSelect.setOptions(defectOptions.map(function(item) { return item.name; }));
    optionsReady = true;
    filterStatus.textContent = data.defects.length ? '' : '当前条件无疵点记录';
    queryButton.onclick = query;
    queryButton.textContent = '查 询';
    return true;
  } catch (error) {
    if (version !== optionsVersion) return false;
    filterStatus.textContent = error.name === 'AbortError' ? '筛选项加载超时' : error.message;
    categorySelect.setLoading('加载失败，请重试');
    defectSelect.setLoading('加载失败，请重试');
    queryButton.onclick = loadOptions;
    queryButton.textContent = '重试筛选项';
    return false;
  } finally {
    if (version === optionsVersion) queryButton.disabled = busy;
  }
}

async function query() {
  if (busy) return;
  var start = document.getElementById('dpmuStartTime');
  var end = document.getElementById('dpmuEndTime');
  if (!start.reportValidity() || !end.reportValidity()) return;
  if (start.value > end.value) {
    status.textContent = '开始时间不得晚于结束时间';
    return;
  }
  if (!optionsReady && !(await loadOptions())) return;
  var params = filterParameters();
  if (!params) return;
  busy = true;
  queryButton.disabled = true;
  page.querySelectorAll('.tab-btn').forEach(function(button) { button.disabled = true; });
  document.getElementById('chartGrid').setAttribute('aria-busy', 'true');
  status.textContent = '查询中…';
  snapshot = null;
  renderCharts('加载中');
  try {
    snapshot = await fetchJSON(page.dataset.summaryUrl, params);
    renderCharts();
    status.textContent = snapshot.start_time.replace('T', ' ') + ' 至 ' + snapshot.end_time.replace('T', ' ')
      + ' | 产量 ' + number(snapshot.total.production, 6) + ' / 报废 ' + number(snapshot.total.scrap, 6);
    if (!snapshot.total.production && !snapshot.total.scrap) {
      status.textContent += ' | 无数据';
      snapshot = null;
      renderCharts('无数据');
    }
  } catch (error) {
    snapshot = null;
    status.textContent = error.name === 'AbortError' ? '查询超时，请缩小时间范围后重试。' : error.message;
    renderCharts('查询失败');
  } finally {
    busy = false;
    queryButton.disabled = false;
    page.querySelectorAll('.tab-btn').forEach(function(button) { button.disabled = false; });
    document.getElementById('chartGrid').setAttribute('aria-busy', 'false');
  }
}

page.querySelectorAll('.tab-btn').forEach(function(button) {
  button.addEventListener('click', function() {
    if (busy || currentTab === button.dataset.tab) return;
    currentTab = button.dataset.tab;
    page.querySelectorAll('.tab-btn').forEach(function(item) {
      item.classList.toggle('active', item.dataset.tab === currentTab);
      item.setAttribute('aria-pressed', String(item.dataset.tab === currentTab));
    });
    snapshot = null;
    status.textContent = '待查询';
    renderCharts();
    loadOptions();
  });
});
function resetFilters() {
  var today = new Intl.DateTimeFormat('sv-SE', { timeZone: 'Asia/Shanghai' }).format(new Date());
  document.getElementById('dpmuStartTime').value = today.slice(0, 7) + '-01T08:30';
  document.getElementById('dpmuEndTime').value = today + 'T08:30';
  confirmedTime = { start: document.getElementById('dpmuStartTime').value,
    end: document.getElementById('dpmuEndTime').value };
  document.getElementById('dpmuEndTime').setCustomValidity('');
  page.querySelector('.dpmu-time-range').classList.remove('is-pending');
  document.getElementById('dpmuTimeState').textContent = '已确认';
  categorySelect.reset(true);
  defectSelect.reset(true);
  loadOptions();
}
document.getElementById('dpmuReset').addEventListener('click', resetFilters);
document.getElementById('dpmuTimeConfirm').addEventListener('click', async function() {
  var start = document.getElementById('dpmuStartTime');
  var end = document.getElementById('dpmuEndTime');
  end.setCustomValidity('');
  if (!start.reportValidity() || !end.reportValidity()) return;
  if (start.value > end.value) {
    end.setCustomValidity('结束时间不得早于开始时间');
    end.reportValidity();
    return;
  }
  confirmedTime = { start: start.value, end: end.value };
  page.querySelector('.dpmu-time-range').classList.remove('is-pending');
  document.getElementById('dpmuTimeState').textContent = '已确认';
  categorySelect.reset(true);
  defectSelect.reset(true);
  var button = document.getElementById('dpmuTimeConfirm');
  button.disabled = true;
  try {
    await loadOptions();
  } finally {
    button.disabled = false;
  }
});
['dpmuStartTime', 'dpmuEndTime'].forEach(function(id) {
  document.getElementById(id).addEventListener('input', function() {
    document.getElementById('dpmuEndTime').setCustomValidity('');
    ++optionsVersion;
    optionsReady = false;
    categorySelect.commit();
    defectSelect.commit();
    categorySelect.setLoading('请先确认时间');
    defectSelect.setLoading('请先确认时间');
    page.querySelector('.dpmu-time-range').classList.add('is-pending');
    document.getElementById('dpmuTimeState').textContent = '待确认';
    document.getElementById('dpmuFilterStatus').textContent = '时间范围待确认';
    queryButton.disabled = busy;
    queryButton.textContent = '查 询';
    queryButton.onclick = query;
  });
});
resetFilters();
renderCharts();

/* ================= 自适应 ================= */
function resizeCharts() {
  var nowMobile = page.clientWidth <= 768;
  if (nowMobile !== isMobile) {
    isMobile = nowMobile;
    AX.fontSize = isMobile ? 10 : 11;
    renderCharts();
  }
  chartInstances.forEach(function(c) { c.resize(); });
}
var chartResizeObserver = new ResizeObserver(resizeCharts);
chartResizeObserver.observe(document.getElementById('chartGrid'));
window.addEventListener('resize', resizeCharts);
})();
