/* SECTION: clock */
(function() {
  function tick() {
    document.getElementById('clock').textContent = new Date().toLocaleString('zh-CN', {
      year:'numeric', month:'2-digit', day:'2-digit', hour:'2-digit', minute:'2-digit', second:'2-digit'
    });
  }
  tick(); setInterval(tick, 1000);
})();

var summary = null;
var summaryFilters = null;
var exporting = false;
var selectWidgets = {};

/* SECTION: multi-select */
var selectState = { Site: ['ACX'], Area: [], Submitter: [], Type: [] };
var selectData = { Site: ['ACX', 'CNX'], Area: [], Submitter: [], Type: [] };
var placeholderText = { Site: '选择站点', Area: '选择区域', Submitter: '选择提交人', Type: '选择类型' };
var filterOptions = null;
var filterOptionsLoading = false;
var filterOptionsError = '';

function applyFilterOptions() {
  if (!filterOptions) return;
  var dimensions = {Area: 'areas', Submitter: 'technicians', Type: 'dispatchtypes'};
  Object.keys(dimensions).forEach(function(name) {
    var values = new Set();
    selectState.Site.forEach(function(site) {
      filterOptions[site][dimensions[name]].forEach(function(value) { values.add(value); });
    });
    selectData[name] = Array.from(values).sort();
    selectState[name] = selectState[name].filter(function(value) { return values.has(value); });
    selectWidgets[name]();
  });
}

async function loadFilterOptions() {
  if (filterOptionsLoading) return;
  filterOptionsLoading = true;
  filterOptionsError = '';
  ['Area', 'Submitter', 'Type'].forEach(function(name) { selectWidgets[name](); });
  var controller = new AbortController();
  var timeout = setTimeout(function() { controller.abort(); }, 60000);
  try {
    var response = await fetch(document.getElementById('dispatchMain').dataset.optionsUrl, {
      signal: controller.signal, headers: {'Accept': 'application/json'}, cache: 'no-store'
    });
    var payload = await response.json();
    if (!response.ok || payload.success !== true) throw new Error(payload.error || '筛选选项加载失败，请重新打开下拉框重试。');
    if (!payload.options || !['ACX', 'CNX'].every(function(site) {
      return payload.options[site] && ['areas', 'technicians', 'dispatchtypes'].every(function(key) {
        return Array.isArray(payload.options[site][key]) && payload.options[site][key].every(function(value) { return typeof value === 'string'; });
      });
    })) throw new Error('筛选选项格式不正确，请重新打开下拉框重试。');
    filterOptions = payload.options;
    applyFilterOptions();
  } catch (error) {
    filterOptionsError = error.name === 'AbortError' ? '筛选选项加载超时，请重新打开下拉框重试。' : error.message;
  } finally {
    clearTimeout(timeout);
    filterOptionsLoading = false;
    ['Area', 'Submitter', 'Type'].forEach(function(name) { selectWidgets[name](); });
  }
}

function closeMultiSelects(exceptName, restoreFocus) {
  Object.keys(selectWidgets).forEach(function(name) {
    if (name !== exceptName) selectWidgets[name].close(restoreFocus);
  });
}

function initMultiSelect(name) {
  var root = document.querySelector('.multi-select[data-name="' + name + '"]');
  var trigger = root.querySelector('.multi-select-trigger');
  var dropdown = root.querySelector('.multi-select-dropdown');
  var searchInput = root.querySelector('.multi-select-search');
  var optionsEl = root.querySelector('.options-list');
  var selectedCount = root.querySelector('.multi-select-count');
  var draft = selectState[name].slice();

  function renderCount() {
    selectedCount.textContent = '已选 ' + draft.length + ' 项';
  }

  function close(restoreFocus) {
    var wasOpen = dropdown.classList.contains('show');
    dropdown.classList.remove('show');
    trigger.classList.remove('open');
    trigger.setAttribute('aria-expanded', 'false');
    draft = selectState[name].slice();
    if (restoreFocus && wasOpen) trigger.focus();
  }

  function renderOptions(filter) {
    filter = (filter || '').toLowerCase();
    optionsEl.replaceChildren();
    selectData[name].forEach(function(item) {
      if (filter && item.toLowerCase().indexOf(filter) === -1) return;
      var sel = draft.indexOf(item) > -1;
      var option = document.createElement('label');
      option.className = 'multi-select-option' + (sel ? ' selected' : '');
      var check = document.createElement('input');
      check.type = 'checkbox';
      check.value = item;
      check.checked = sel;
      check.className = 'option-checkbox';
      var label = document.createElement('span');
      label.className = 'option-label';
      label.textContent = item;
      option.append(check, label);
      optionsEl.appendChild(option);
    });
    if (!optionsEl.children.length) {
      var empty = document.createElement('div');
      empty.className = 'select-empty';
      empty.textContent = name !== 'Site' && filterOptionsLoading ? '正在加载选项…' :
        (name !== 'Site' && filterOptionsError ? filterOptionsError : '无可选项');
      optionsEl.appendChild(empty);
    }
    renderCount();
  }
  function renderTrigger() {
    var sel = selectState[name];
    trigger.replaceChildren();
    trigger.classList.toggle('has-selection', sel.length > 0);
    trigger.title = sel.length ? sel.join('\n') : placeholderText[name];
    trigger.setAttribute('aria-label', placeholderText[name] + (sel.length ? '：' + sel.join('、') : ''));
    var text = document.createElement('span');
    text.className = 'selection-text';
    text.textContent = sel.length ? sel[0] : placeholderText[name];
    trigger.appendChild(text);
    if (sel.length > 1) {
      var count = document.createElement('span');
      count.className = 'selection-count';
      count.textContent = sel.length + ' 项';
      trigger.appendChild(count);
    }
  }
  trigger.addEventListener('click', function() {
    if (dropdown.classList.contains('show')) {
      close(false);
      return;
    }
    closeMultiSelects(name, false);
    draft = selectState[name].slice();
    searchInput.value = '';
    renderOptions('');
    dropdown.classList.add('show');
    trigger.classList.add('open');
    trigger.setAttribute('aria-expanded', 'true');
    searchInput.focus();
    if (name !== 'Site' && !filterOptions && !filterOptionsLoading) loadFilterOptions();
  });
  searchInput.addEventListener('input', function() { renderOptions(this.value); });
  optionsEl.addEventListener('change', function(event) {
    if (!event.target.matches('.option-checkbox')) return;
    var checkbox = event.target;
    draft = draft.filter(function(value) { return value !== checkbox.value; });
    if (checkbox.checked) draft.push(checkbox.value);
    checkbox.closest('.multi-select-option').classList.toggle('selected', checkbox.checked);
    renderCount();
  });
  root.querySelector('.multi-select-reset').addEventListener('click', function() {
    draft = [];
    renderOptions(searchInput.value);
  });
  root.querySelector('.multi-select-confirm').addEventListener('click', function() {
    selectState[name] = draft.slice();
    close(true);
    renderTrigger();
    if (name === 'Site') applyFilterOptions();
  });
  dropdown.id = 'dispatch-select-' + name;
  trigger.setAttribute('aria-controls', dropdown.id);
  searchInput.setAttribute('aria-label', placeholderText[name].replace('选择', '搜索'));
  renderOptions('');
  renderTrigger();
  var refresh = function() {
    if (!dropdown.classList.contains('show')) draft = selectState[name].slice();
    renderOptions(searchInput.value); renderTrigger();
  };
  refresh.close = close;
  return refresh;
}
['Site', 'Area', 'Submitter', 'Type'].forEach(function(name) { selectWidgets[name] = initMultiSelect(name); });
document.addEventListener('click', function(e) {
  if (!e.target.closest('.multi-select')) {
    closeMultiSelects(null, false);
  }
});
document.addEventListener('keydown', function(event) {
  if (event.key === 'Escape') {
    closeMultiSelects(null, true);
  }
});

/* SECTION: query + render */
var charts = {};
var activeRequest;
var queryNumber = 0;

async function doQuery() {
  var currentQuery = ++queryNumber;
  if (activeRequest) activeRequest.abort();
  var controller = new AbortController();
  activeRequest = controller;
  var from = document.getElementById('dateFrom').value;
  var to = document.getElementById('dateTo').value;
  var status = document.getElementById('queryStatus');
  var button = document.getElementById('btnQuery');
  status.classList.remove('is-error');
  if (!selectState.Site.length || !from || !to || from > to) {
    status.textContent = !selectState.Site.length ? '请至少选择一个站点。' : '请选择有效时间范围，开始日期不能晚于结束日期。';
    status.classList.add('is-error');
    summary = null; renderAll(); button.disabled = false;
    document.querySelector('.charts-grid').setAttribute('aria-busy', 'false');
    return;
  }
  var params = new URLSearchParams({start: from, end: to});
  Object.keys(selectState).forEach(function(name) {
    var key = {Site: 'site', Area: 'area', Submitter: 'technician', Type: 'dispatchtype'}[name];
    selectState[name].forEach(function(value) { params.append(key, value); });
  });
  var filters = {
    query: params.toString(), sites: selectState.Site.join(', '), start: from, end: to,
    areas: selectState.Area.join(', ') || '全部',
    submitters: selectState.Submitter.join(', ') || '全部',
    types: selectState.Type.join(', ') || '全部'
  };
  button.disabled = true;
  status.textContent = '正在查询 Snowflake…';
  summary = null;
  renderAll();
  document.querySelector('.charts-grid').setAttribute('aria-busy', 'true');
  var timeout = setTimeout(function() { controller.abort(); }, 120000);
  try {
    var response = await fetch(document.getElementById('dispatchMain').dataset.url + '?' + params, {
      signal: controller.signal, headers: {'Accept': 'application/json'}, cache: 'no-store'
    });
    var payload = await response.json();
    if (!response.ok || payload.success !== true) throw new Error(payload.error || '查询失败，请稍后重试。');
    if (currentQuery !== queryNumber) return;
    if (!payload.stats || !payload.options || !Array.isArray(payload.trend) || !Array.isArray(payload.areas) || !Array.isArray(payload.types)) {
      throw new Error('接口返回的数据格式不正确。');
    }
    summary = payload;
    summaryFilters = filters;
    status.textContent = payload.stats.total ? '已更新 · ' + payload.stats.total + ' 条' : '没有符合筛选条件的数据';
  } catch (error) {
    if (currentQuery !== queryNumber) return;
    summary = null;
    status.textContent = error.name === 'AbortError' ? 'Snowflake 查询超时，请稍后重试或缩小时间范围。' : error.message;
    status.classList.add('is-error');
  } finally {
    clearTimeout(timeout);
    if (currentQuery === queryNumber) {
      button.disabled = false;
      document.querySelector('.charts-grid').setAttribute('aria-busy', 'false');
      renderAll();
    }
  }
}

function doReset() {
  closeMultiSelects(null, false);
  selectState.Site = ['ACX'];
  selectState.Area = []; selectState.Submitter = []; selectState.Type = [];
  document.getElementById('dateFrom').value = document.getElementById('dateFrom').defaultValue;
  document.getElementById('dateTo').value = document.getElementById('dateTo').defaultValue;
  ['Site','Area','Submitter','Type'].forEach(function(n) {
    selectWidgets[n]();
  });
  applyFilterOptions();
}

async function doExport() {
  if (!summary || !summaryFilters || exporting) return;
  var snapshot = {query: summaryFilters.query, filters: summaryFilters};
  var status = document.getElementById('queryStatus');
  var button = document.getElementById('btnExport');
  var controller = new AbortController();
  var timeout = setTimeout(function() { controller.abort(); }, 120000);
  exporting = true;
  button.disabled = true;
  button.textContent = '正在导出…';
  try {
    var response = await fetch(document.getElementById('dispatchMain').dataset.exportUrl, {
      method: 'POST', signal: controller.signal,
      headers: {'Content-Type': 'application/json', 'X-CSRFToken': document.querySelector('#dispatchMain [name="csrfmiddlewaretoken"]').value},
      body: JSON.stringify(snapshot), cache: 'no-store'
    });
    if (!response.ok) {
      var errorPayload;
      try { errorPayload = await response.json(); } catch (error) { errorPayload = {}; }
      throw new Error(errorPayload.error || 'Excel 导出失败，请稍后重试。');
    }
    var url = URL.createObjectURL(await response.blob());
    var link = document.createElement('a');
    link.href = url;
    link.download = 'Dispatch_' + snapshot.filters.sites.replace(/, /g, '-') + '_' + snapshot.filters.start + '_' + snapshot.filters.end + '.xlsx';
    document.body.appendChild(link);
    link.click();
    link.remove();
    setTimeout(function() { URL.revokeObjectURL(url); }, 1000);
  } catch (error) {
    status.textContent = error.name === 'AbortError' ? 'Excel 导出超时，请重试。' : error.message;
    status.classList.add('is-error');
  } finally {
    clearTimeout(timeout);
    exporting = false;
    button.textContent = '\u21e9 导出';
    button.disabled = !summary;
  }
}

function renderStats() {
  var values = summary && summary.stats;
  var fields = {stTotal: 'total', stOpen: 'open', stInwork: 'inwork', stClosed: 'closed', stRate: 'rate'};
  Object.keys(fields).forEach(function(id) {
    document.getElementById(id).textContent = values ? String(values[fields[id]]) + (id === 'stRate' ? '%' : '') : '--';
  });
}

function tooltipStyle() {
  return { renderMode: 'richText', confine: true, backgroundColor: 'rgba(10,22,40,0.95)', borderColor: 'rgba(0,212,255,0.2)', textStyle: { color: '#e0e6ed', fontSize: 12 } };
}

function initChart(id) {
  if (charts[id]) return charts[id];
  var el = document.getElementById(id);
  if (!el) return null;
  charts[id] = echarts.init(el);
  return charts[id];
}

function renderCharts() {
  /* 趋势：按月 提交数 / 关闭数 */
  var trend = summary ? summary.trend : [];
  var dates = trend.map(function(row) { return row.month; });
  var totals = trend.map(function(row) { return row.total; });
  var closeds = trend.map(function(row) { return row.closed; });
  initChart('chartTrend').setOption({
    tooltip: Object.assign({ trigger: 'axis' }, tooltipStyle()),
    legend: { bottom: 0, left: 'center', textStyle: { color: '#6b7b8d', fontSize: 11 } },
    grid: { top: '10%', bottom: '16%', left: '6%', right: '4%', containLabel: true },
    xAxis: { type: 'category', data: dates, axisLine: { lineStyle: { color: 'rgba(255,255,255,0.08)' } }, axisLabel: { color: '#6b7b8d', fontSize: 10, rotate: 30 } },
    yAxis: { type: 'value', minInterval: 1, splitLine: { lineStyle: { color: 'rgba(255,255,255,0.04)' } }, axisLabel: { color: '#6b7b8d', fontSize: 11 } },
    series: [
      { name: '提交', type: 'line', smooth: true, data: totals, lineStyle: { color: '#00d4ff', width: 2 }, itemStyle: { color: '#00d4ff' }, symbol: 'circle', symbolSize: 5,
        areaStyle: { color: { type: 'linear', x: 0, y: 0, x2: 0, y2: 1, colorStops: [{ offset: 0, color: 'rgba(0,212,255,0.22)' }, { offset: 1, color: 'rgba(0,212,255,0.02)' }] } } },
      { name: '已关闭', type: 'line', smooth: true, data: closeds, lineStyle: { color: '#00ffa3', width: 2 }, itemStyle: { color: '#00ffa3' }, symbol: 'circle', symbolSize: 5 }
    ]
  }, true);

  /* 状态分布 */
  var stats = summary ? summary.stats : {open: 0, inwork: 0, closed: 0};
  initChart('chartStatus').setOption({
    tooltip: Object.assign({ formatter: function(p) { return p.name + ': ' + p.value + ' 单 (' + p.percent.toFixed(1) + '%)'; } }, tooltipStyle()),
    legend: { bottom: 0, left: 'center', itemWidth: 10, itemHeight: 8, itemGap: 6, textStyle: { color: '#6b7b8d', fontSize: 10 } },
    series: [{ type: 'pie', stillShowZeroSum: false, radius: ['40%', '65%'], center: ['50%', '44%'], avoidLabelOverlap: true,
      label: { show: false }, labelLine: { show: false },
      data: [
        { value: stats.open, name: 'OPEN', itemStyle: { color: '#ff4d4f' } },
        { value: stats.inwork, name: 'IN WORK', itemStyle: { color: '#ffaa00' } },
        { value: stats.closed, name: 'CLOSED', itemStyle: { color: '#00ffa3' } }
      ]
    }]
  }, true);

  /* 类型分布 */
  var typeRows = summary ? summary.types : [];
  var typeColors = ['#00d4ff','#00ffa3','#ffaa00','#a78bfa','#f472b6'];
  initChart('chartType').setOption({
    baseOption: {
    tooltip: Object.assign({ trigger: 'item' }, tooltipStyle()),
    legend: { type: 'scroll', bottom: 0, itemWidth: 10, itemHeight: 8, pageIconSize: 10,
      textStyle: { color: '#6b7b8d', fontSize: 10, width: 90, overflow: 'truncate' } },
    series: [{ type: 'pie', stillShowZeroSum: false, radius: '62%', center: ['50%', '48%'], avoidLabelOverlap: true,
      labelLayout: { hideOverlap: true },
      label: { show: true, color: '#a0b4c8', fontSize: 11, width: 100, overflow: 'truncate', formatter: '{b}\n{c}单 ({d}%)' },
      labelLine: { lineStyle: { color: 'rgba(255,255,255,0.15)' } },
      data: typeRows.map(function(row, idx) { return { value: row.value, name: row.name, itemStyle: { color: typeColors[idx % typeColors.length] } }; })
    }]
    },
    media: [{ query: { maxWidth: 300 }, option: {
      series: [{ center: ['50%', '42%'], label: { show: false }, labelLine: { show: false } }]
    } }]
  }, true);

  /* 区域堆叠柱状 */
  var areaData = { OPEN: [], 'IN WORK': [], CLOSED: [] };
  var areaRows = summary ? summary.areas : [];
  areaRows.forEach(function(row) {
    Object.keys(areaData).forEach(function(status) { areaData[status].push(row[status]); });
  });
  initChart('chartArea').setOption({
    baseOption: {
    tooltip: Object.assign({ trigger: 'axis' }, tooltipStyle()),
    legend: { bottom: 0, left: 'center', itemWidth: 10, itemHeight: 8, itemGap: 6, textStyle: { color: '#6b7b8d', fontSize: 10 } },
    grid: { top: '10%', bottom: '16%', left: '5%', right: '4%', containLabel: true },
    xAxis: { type: 'category', data: areaRows.map(function(row) { return row.name; }), axisLine: { lineStyle: { color: 'rgba(255,255,255,0.08)' } }, axisLabel: { color: '#a0b4c8', fontSize: 11, interval: 0, width: 100, overflow: 'truncate' } },
    yAxis: { type: 'value', minInterval: 1, splitLine: { lineStyle: { color: 'rgba(255,255,255,0.04)' } }, axisLabel: { color: '#6b7b8d', fontSize: 11 } },
    series: [
      { name: 'OPEN', type: 'bar', stack: 's', barMaxWidth: 20, data: areaData.OPEN, itemStyle: { color: '#ff4d4f' } },
      { name: 'IN WORK', type: 'bar', stack: 's', data: areaData['IN WORK'], itemStyle: { color: '#ffaa00' } },
      { name: 'CLOSED', type: 'bar', stack: 's', data: areaData.CLOSED, itemStyle: { color: '#00ffa3', borderRadius: [4,4,0,0] } }
    ]
    },
    media: [{ query: { maxWidth: 360 }, option: {
      grid: { top: 4, bottom: 22, left: 0, right: 4, containLabel: true },
      xAxis: { type: 'value', data: [], splitNumber: 2, axisLabel: { fontSize: 10, rotate: 0, hideOverlap: true } },
      yAxis: { type: 'category', data: areaRows.map(function(row) { return row.name; }),
        splitLine: { show: false }, axisLabel: { width: 64, overflow: 'truncate', fontSize: 10, interval: 0 } }
    } }]
  }, true);
}

function renderAll() {
  renderStats(); renderCharts();
  document.getElementById('btnExport').disabled = !summary || exporting;
}

document.getElementById('btnQuery').addEventListener('click', doQuery);
document.getElementById('btnReset').addEventListener('click', doReset);
document.getElementById('btnExport').addEventListener('click', doExport);
window.addEventListener('resize', function() {
  Object.keys(charts).forEach(function(k) { if (charts[k]) charts[k].resize(); });
});

renderAll();
loadFilterOptions();

var chartResizeObserver = new ResizeObserver(function(entries) {
  entries.forEach(function(entry) {
    var chart = charts[entry.target.id];
    if (chart) chart.resize();
  });
});
document.querySelectorAll('.dispatch-content .chart-box').forEach(function(element) {
  chartResizeObserver.observe(element);
});
