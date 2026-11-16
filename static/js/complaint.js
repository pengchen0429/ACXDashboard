(function() {
/* SECTION: clock */
(function() {
  function tick() {
    document.getElementById('clock').textContent = new Date().toLocaleString('zh-CN', {
      year:'numeric', month:'2-digit', day:'2-digit', hour:'2-digit', minute:'2-digit', second:'2-digit'
    });
  }
  tick(); setInterval(tick, 1000);
})();

/* SECTION: constants */
var TYPE_OPTIONS = Array.from(document.getElementById('fmType').options).map(function(option) { return option.value; }).filter(Boolean);
var LEVEL_OPTIONS = Array.from(document.getElementById('fmLevel').options).map(function(option) { return option.value; }).filter(Boolean);
var TYPES = TYPE_OPTIONS.slice();
var LEVELS = LEVEL_OPTIONS.slice();
var STATUSES = ['待处理', '处理中', '已解决', '已关闭'];
var pageRoot = document.querySelector('.complaint-page');
var allData = [];
var permissions = { add: pageRoot.dataset.canAdd === 'true', change: pageRoot.dataset.canChange === 'true', delete: pageRoot.dataset.canDelete === 'true' };
var busy = false;
var exporting = false;
var pendingImages = [];
var hasLoadedData = false;
var COLUMNS = [
  ['no', '编号', 'fmId'], ['area', '区域', 'fmArea'], ['reported_at', '时间', 'fmDate'],
  ['customer', '客户', 'fmCustomer'], ['complaint_type', '投诉等级', 'fmLevel'],
  ['webbing_type', '带型', 'fmProduct'], ['complaint', '投诉点', 'fmSummary'],
  ['classification', '分类', 'fmType'], ['defect_pictures', '投诉图片', 'fmPictures'],
  ['root_cause', '根本原因', 'fmRootCause'], ['corrective_action', '纠正措施', 'fmAction'],
  ['res', '责任人', 'fmHandler'], ['completion_time', '完成时间', 'fmCompletion'],
  ['state', '状态', 'fmStatus'], ['remark', '备注', 'fmDetail']
];

function esc(s) {
  return String(s == null ? '' : s)
    .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;').replace(/'/g, '&#39;');
}

function recordUrl(id) {
  return pageRoot.dataset.recordUrl.replace('/0/', '/' + encodeURIComponent(id) + '/');
}

async function requestData(url, options) {
  var controller = new AbortController();
  var timer = setTimeout(function() { controller.abort(); }, 20000);
  try {
    var response = await fetch(url, Object.assign({}, options, {
      credentials: 'same-origin', signal: controller.signal,
      headers: Object.assign(options && options.body instanceof FormData ? {} : { 'Content-Type': 'application/json' }, { 'X-CSRFToken': pageRoot.dataset.csrfToken })
    }));
    var data = await response.json().catch(function() { return {}; });
    if (!response.ok) {
      var error = new Error(data.error || '请求失败（' + response.status + '）');
      error.fields = data.fields;
      throw error;
    }
    return data;
  } catch (error) {
    if (error.name === 'AbortError') throw new Error('请求超时，请重试');
    throw error;
  } finally {
    clearTimeout(timer);
  }
}

function normalizeRecord(record) {
  var days = record.date && record.completion_time ? (Date.parse(record.completion_time) - Date.parse(record.date)) / 86400000 : null;
  return Object.assign({}, record, {
    id: String(record.no), reported_at: record.date || '', date: (record.date || '').slice(0, 10),
    type: record.classification || '未填写', level: record.complaint_type || '未填写',
    status: record.state || '未填写', days: days !== null && Number.isFinite(days) && days >= 0 ? days : null
  });
}

function setBusy(value) {
  busy = value;
  document.querySelectorAll('.filter-bar input, .filter-bar .multi-select button').forEach(function(control) { control.disabled = value; });
  document.querySelectorAll('#formModal input, #formModal select, #formModal textarea, #formModal button').forEach(function(control) { control.disabled = value; });
  document.getElementById('btnAddImage').disabled = value || !(editingId ? permissions.change : permissions.add);
  document.getElementById('btnQuery').disabled = value;
  document.getElementById('btnReset').disabled = value;
  document.getElementById('btnAdd').disabled = value || !permissions.add;
  document.getElementById('btnAdd').title = permissions.add ? '' : '需要新增客户投诉权限';
  document.getElementById('btnExport').disabled = value || exporting || !hasLoadedData || !filtered.length;
  document.getElementById('btnSave').disabled = value || !(editingId ? permissions.change : permissions.add);
  document.getElementById('btnDetailEdit').disabled = value || !permissions.change;
  document.querySelectorAll('#tblBody button[data-act]').forEach(function(button) {
    var action = button.dataset.act;
    button.disabled = action !== 'view' && (value || !(action === 'edit' ? permissions.change : permissions.delete));
  });
}

function setStatus(message) {
  var status = document.getElementById('dataStatus');
  status.textContent = message;
  status.classList.toggle('is-error', message.indexOf('失败') >= 0);
  status.hidden = !message;
}

function refreshFilterOptions() {
  TYPES = Array.from(new Set(TYPE_OPTIONS.concat(allData.map(function(record) { return record.type; }))));
  LEVELS = Array.from(new Set(LEVEL_OPTIONS.concat(allData.map(function(record) { return record.level; }))));
  STATUSES = Array.from(new Set(['待处理', '处理中', '已解决', '已关闭'].concat(allData.map(function(record) { return record.status; }))));
  [['statusOptions', STATUSES]].forEach(function(pair) {
    document.getElementById(pair[0]).innerHTML = pair[1].filter(function(value) { return value !== '未填写'; }).map(function(value) {
      return '<option value="' + esc(value) + '"></option>';
    }).join('');
  });
  [typeFilter, levelFilter, statusFilter].forEach(function(filter) { filter.render(); });
}

async function loadRecords() {
  if (busy) return;
  var query = {
    from: document.getElementById('fDateFrom').value,
    to: document.getElementById('fDateTo').value,
    types: typeFilter.values.slice(), levels: levelFilter.values.slice(), statuses: statusFilter.values.slice()
  };
  if (query.from && query.to && query.from > query.to) { setStatus('开始时间不能晚于结束时间'); return; }
  setBusy(true);
  setStatus('正在加载投诉数据…');
  try {
    var result = await requestData(pageRoot.dataset.recordsUrl);
    if (!Array.isArray(result.records)) throw new Error('投诉数据格式不正确');
    allData = result.records.map(normalizeRecord);
    permissions = result.permissions || { add: false, change: false, delete: false };
    hasLoadedData = true;
    appliedFilters = query;
    refreshFilterOptions();
    applyFilters();
    setStatus('');
  } catch (error) {
    setStatus('加载失败：' + error.message + (hasLoadedData ? '，仍显示上次加载的数据。' : ''));
    if (!hasLoadedData) {
      document.getElementById('emptyTip').textContent = '投诉数据加载失败，请点击查询重试';
      ['stTotal', 'stPending', 'stWorking', 'stClosed', 'stAvg', 'stSevere'].forEach(function(id) {
        document.getElementById(id).textContent = '—';
      });
    }
  } finally {
    setBusy(false);
  }
}

/* SECTION: filter component */
function createMultiSelect(id, options, placeholder) {
  var root = document.getElementById(id);
  var trigger = root.querySelector('.multi-select-trigger');
  var dropdown = root.querySelector('.multi-select-dropdown');
  var optionsEl = root.querySelector('.options-list');
  var filter = { values: [] };
  var tools = document.createElement('div');
  tools.className = 'multi-select-tools';
  ['全选', '清空'].forEach(function(label, index) {
    var button = document.createElement('button');
    button.type = 'button';
    button.className = 'btn btn-secondary btn-mini';
    button.textContent = label;
    button.addEventListener('click', function() {
      filter.values = index === 0 ? options().slice() : [];
      filter.render();
    });
    tools.appendChild(button);
  });
  dropdown.insertBefore(tools, optionsEl);
  function close() {
    dropdown.classList.remove('show');
    trigger.setAttribute('aria-expanded', 'false');
    trigger.classList.remove('open');
  }
  filter.render = function() {
    var values = options();
    filter.values = filter.values.filter(function(value) { return values.indexOf(value) >= 0; });
    optionsEl.innerHTML = values.map(function(value) {
      var selected = filter.values.indexOf(value) >= 0;
      return '<label class="multi-select-option' + (selected ? ' selected' : '') + '"><input type="checkbox" value="' + esc(value) + '"' + (selected ? ' checked' : '') + (busy ? ' disabled' : '') + '><span>' + esc(value) + '</span></label>';
    }).join('');
    trigger.textContent = filter.values.length ? filter.values.join('、') : placeholder;
    trigger.title = trigger.textContent;
  };
  filter.reset = function() { filter.values = []; filter.render(); close(); };
  trigger.addEventListener('click', function() {
    dropdown.classList.toggle('show');
    trigger.classList.toggle('open', dropdown.classList.contains('show'));
    trigger.setAttribute('aria-expanded', String(dropdown.classList.contains('show')));
  });
  optionsEl.addEventListener('change', function(event) {
    var checkbox = event.target.closest('input[type="checkbox"]');
    if (!checkbox || busy) return;
    filter.values = filter.values.filter(function(value) { return value !== checkbox.value; });
    if (checkbox.checked) filter.values.push(checkbox.value);
    filter.render();
  });
  document.addEventListener('click', function(event) {
    if (!root.contains(event.target)) close();
  });
  root.addEventListener('keydown', function(event) { if (event.key === 'Escape') { close(); trigger.focus(); } });
  filter.render();
  return filter;
}
var typeFilter = createMultiSelect('msType', function() { return TYPES; }, '全部分类');
var levelFilter = createMultiSelect('msLevel', function() { return LEVELS; }, '全部等级');
var statusFilter = createMultiSelect('msStatus', function() { return STATUSES; }, '全部状态');

/* SECTION: query state */
var filtered = [];
var currentPage = 1;
var pageSize = 10;
var appliedFilters = { from: '', to: '', types: [], levels: [], statuses: [] };

function resetDateRange() {
  var today = new Intl.DateTimeFormat('sv-SE', {
    timeZone: 'Asia/Shanghai', year: 'numeric', month: '2-digit', day: '2-digit'
  }).format(new Date());
  document.getElementById('fDateFrom').value = today.slice(0, 4) + '-01-01T08:30';
  document.getElementById('fDateTo').value = today + 'T08:30';
}

function applyFilters() {
  var from = appliedFilters.from;
  var to = appliedFilters.to;
  var fromTime = from ? Date.parse(from + '+08:00') : null;
  var toTime = to ? Date.parse(to + '+08:00') : null;
  filtered = allData.filter(function(r) {
    if (appliedFilters.types.length && appliedFilters.types.indexOf(r.type) === -1) return false;
    if (appliedFilters.levels.length && appliedFilters.levels.indexOf(r.level) === -1) return false;
    if (appliedFilters.statuses.length && appliedFilters.statuses.indexOf(r.status) === -1) return false;
    var reportedTime = Date.parse(r.reported_at);
    if ((from || to) && !Number.isFinite(reportedTime)) return false;
    if (from && reportedTime < fromTime) return false;
    if (to && reportedTime > toTime) return false;
    return true;
  });
  filtered.sort(function(a, b) { return b.reported_at.localeCompare(a.reported_at) || b.id.length - a.id.length || b.id.localeCompare(a.id); });
  currentPage = 1;
  renderAll();
}

/* SECTION: render stats */
function renderStats() {
  if (!hasLoadedData) {
    ['stTotal', 'stPending', 'stWorking', 'stClosed', 'stAvg', 'stSevere'].forEach(function(id) { document.getElementById(id).textContent = '—'; });
    return;
  }
  var pending = 0, working = 0, closed = 0, severeOpen = 0, sumDays = 0, cntDays = 0;
  filtered.forEach(function(r) {
    if (r.status === '待处理') pending++;
    else if (r.status === '处理中') working++;
    else if (r.status === '已解决' || r.status === '已关闭') { closed++; if (r.days != null) { sumDays += r.days; cntDays++; } }
    if (r.level === '严重' && (r.status === '待处理' || r.status === '处理中')) severeOpen++;
  });
  document.getElementById('stTotal').textContent = filtered.length;
  document.getElementById('stPending').textContent = pending;
  document.getElementById('stWorking').textContent = working;
  document.getElementById('stClosed').textContent = closed;
  document.getElementById('stAvg').textContent = cntDays ? (sumDays / cntDays).toFixed(1) : '—';
  document.getElementById('stSevere').textContent = severeOpen;
}

/* SECTION: charts */
var charts = {};
var COLORS = { cyan:'#00d4ff', green:'#00ffa3', orange:'#ffaa00', purple:'#a78bfa', pink:'#f472b6', red:'#ff4d4f' };

function tip() {
  return { backgroundColor: 'rgba(10,22,40,0.95)', borderColor: 'rgba(0,212,255,0.2)', textStyle: { color: '#e0e6ed', fontSize: 12 } };
}
function chart(id) {
  if (charts[id]) return charts[id];
  var el = document.getElementById(id);
  if (!el || !window.echarts) return null;
  charts[id] = echarts.init(el);
  return charts[id];
}

function renderCharts() {
  /* trend by month */
  var monthMap = {};
  filtered.forEach(function(r) {
    if (!r.date) return;
    var m = r.date.slice(0, 7);
    if (!monthMap[m]) monthMap[m] = { total: 0, severe: 0 };
    monthMap[m].total++;
    if (r.level === '严重') monthMap[m].severe++;
  });
  var months = Object.keys(monthMap).sort();
  var totals = months.map(function(m) { return monthMap[m].total; });
  var severs = months.map(function(m) { return monthMap[m].severe; });
  var c1 = chart('chartTrend');
  if (c1) c1.setOption({
    tooltip: Object.assign({ trigger: 'axis' }, tip()),
    legend: { bottom: 0, left: 'center', textStyle: { color: '#6b7b8d', fontSize: 11 } },
    grid: { top: '12%', bottom: '18%', left: '8%', right: '6%', containLabel: true },
    xAxis: { type: 'category', data: months, axisLine: { lineStyle: { color: 'rgba(255,255,255,0.08)' } }, axisLabel: { color: '#6b7b8d', fontSize: 11 } },
    yAxis: { type: 'value', minInterval: 1, splitLine: { lineStyle: { color: 'rgba(255,255,255,0.04)' } }, axisLabel: { color: '#6b7b8d', fontSize: 11 } },
    series: [
      { name: '投诉件数', type: 'bar', barWidth: 22, data: totals,
        itemStyle: { color: { type: 'linear', x: 0, y: 0, x2: 0, y2: 1, colorStops: [{ offset: 0, color: COLORS.cyan }, { offset: 1, color: 'rgba(0,212,255,0.15)' }] }, borderRadius: [4,4,0,0] },
        label: { show: true, position: 'top', color: '#a0b4c8', fontSize: 11 } },
      { name: '严重投诉', type: 'line', smooth: true, data: severs, lineStyle: { color: COLORS.red, width: 2 }, itemStyle: { color: COLORS.red }, symbol: 'circle', symbolSize: 6 }
    ]
  }, true);

  /* type pie */
  var typeCnt = TYPES.map(function(t) { return 0; });
  filtered.forEach(function(r) {
    var i = TYPES.indexOf(r.type);
    if (i > -1) typeCnt[i]++;
  });
  var pal = [COLORS.cyan, COLORS.green, COLORS.orange, COLORS.purple, COLORS.pink, '#3b82f6'];
  var c2 = chart('chartType');
  if (c2) c2.setOption({
    tooltip: Object.assign({ formatter: function(p) { return esc(p.name) + ': ' + p.value + ' 件 (' + p.percent.toFixed(1) + '%)'; } }, tip()),
    legend: { bottom: 0, left: 'center', textStyle: { color: '#6b7b8d', fontSize: 11 } },
    series: [{ type: 'pie', radius: ['38%', '62%'], center: ['50%', '44%'], avoidLabelOverlap: true,
      label: { show: false }, labelLine: { show: false },
      data: TYPES.map(function(t, i) { return { value: typeCnt[i], name: t, itemStyle: { color: pal[i % pal.length] } }; })
    }]
  }, true);

  /* level x status stacked */
  var matrix = Object.create(null);
  LEVELS.forEach(function(l) { matrix[l] = Object.create(null); STATUSES.forEach(function(s) { matrix[l][s] = 0; }); });
  filtered.forEach(function(r) { if (matrix[r.level]) matrix[r.level][r.status]++; });
  var statusColors = [COLORS.red, COLORS.orange, COLORS.cyan, COLORS.green];
  var c3 = chart('chartLevel');
  if (c3) c3.setOption({
    tooltip: Object.assign({ trigger: 'axis' }, tip()),
    legend: { bottom: 0, left: 'center', textStyle: { color: '#6b7b8d', fontSize: 11 } },
    grid: { top: '12%', bottom: '18%', left: '8%', right: '6%', containLabel: true },
    xAxis: { type: 'category', data: LEVELS, axisLine: { lineStyle: { color: 'rgba(255,255,255,0.08)' } }, axisLabel: { color: '#a0b4c8', fontSize: 12 } },
    yAxis: { type: 'value', minInterval: 1, splitLine: { lineStyle: { color: 'rgba(255,255,255,0.04)' } }, axisLabel: { color: '#6b7b8d', fontSize: 11 } },
    series: STATUSES.map(function(s, si) {
      return { name: s, type: 'bar', stack: 's', barWidth: 34,
        data: LEVELS.map(function(l) { return matrix[l][s]; }),
        itemStyle: { color: statusColors[si % statusColors.length], borderRadius: si === STATUSES.length - 1 ? [4,4,0,0] : 0 } };
    })
  }, true);
}

/* SECTION: render table */
function pictureUrl(reference) {
  var name = reference.split(/[\\/]/).pop();
  if (/^(?:[a-z]:[\\/]|[\\/])/i.test(reference) && /^[0-9a-f]{32}\.(jpg|png|gif|webp)$/.test(name)) {
    return pageRoot.dataset.imagesUrl + name + '/';
  }
  try {
    var url = new URL(reference, window.location.origin);
    if (/^https?:$/.test(url.protocol) && (/^https?:\/\//i.test(reference) || reference.charAt(0) === '/')) return url.href;
  } catch (error) {}
  return null;
}

function renderValue(record, key, detailed) {
  var value = record[key];
  if (value === null || value === undefined || value === '') return '—';
  if (key === 'reported_at' || key === 'completion_time') return esc(String(value).replace('T', ' ').slice(0, 19));
  if (key === 'defect_pictures') {
    return String(value).split(/\r?\n/).map(function(reference) { return reference.trim(); }).filter(Boolean).map(function(reference, index) {
      var url = pictureUrl(reference);
      if (url) return '<a href="' + esc(url) + '" title="' + esc(reference) + '" target="_blank" rel="noopener noreferrer">图片 ' + (index + 1) + '</a>';
      return esc(reference);
    }).join(' ');
  }
  if (key === 'complaint_type') return '<span class="badge badge-level-' + esc(value) + '">' + esc(value) + '</span>';
  if (key === 'state') return '<span class="badge badge-status-' + STATUSES.indexOf(value) + '">' + esc(value) + '</span>';
  return detailed ? esc(value).replace(/\r?\n/g, '<br>') : esc(value);
}

function renderTable() {
  var body = document.getElementById('tblBody');
  var tip = document.getElementById('emptyTip');
  var wrap = document.getElementById('tblWrapper');
  var start = (currentPage - 1) * pageSize;
  var rows = filtered.slice(start, start + pageSize);
  document.getElementById('tblCount').textContent = '第 ' + (rows.length ? start + 1 : 0) + '-' + (start + rows.length) + ' 条 / 共 ' + filtered.length + ' 条';
  document.getElementById('pageInfo').textContent = '共 ' + filtered.length + ' 条记录';
  tip.textContent = hasLoadedData ? '没有符合筛选条件的投诉记录' : '暂无查询结果';
  if (filtered.length === 0) { body.innerHTML = ''; wrap.style.display = ''; tip.style.display = 'block'; renderPagination(); return; }
  wrap.style.display = ''; tip.style.display = 'none';
  var html = '';
  rows.forEach(function(r) {
    html += '<tr>' + COLUMNS.map(function(column) {
      return '<td class="summary-cell" title="' + esc(r[column[0]]) + '">' + renderValue(r, column[0], false) + '</td>';
    }).join('') +
      '<td class="actions-cell">' +
        '<button class="btn btn-secondary btn-mini" data-act="view" data-id="' + esc(r.id) + '">详情</button> ' +
        '<button class="btn btn-primary btn-mini" data-act="edit" data-id="' + esc(r.id) + '"' + (busy || !permissions.change ? ' disabled' : '') + ' title="' + (permissions.change ? '编辑投诉' : '需要修改客户投诉权限') + '">编辑</button> ' +
        '<button class="btn btn-danger btn-mini" data-act="del" data-id="' + esc(r.id) + '"' + (busy || !permissions.delete ? ' disabled' : '') + ' title="' + (permissions.delete ? '删除投诉' : '需要删除客户投诉权限') + '">删除</button>' +
      '</td></tr>';
  });
  body.innerHTML = html;
  renderPagination();
}

function renderPagination() {
  var totalPages = Math.max(1, Math.ceil(filtered.length / pageSize));
  var container = document.getElementById('pageBtns');
  var html = '';
  html += '<button class="page-btn" ' + (currentPage <= 1 ? 'disabled' : '') + ' data-page="' + (currentPage - 1) + '">‹</button>';
  var s = Math.max(1, currentPage - 2), e = Math.min(totalPages, currentPage + 2);
  if (s > 1) html += '<button class="page-btn" data-page="1">1</button>';
  if (s > 2) html += '<span style="color:var(--text-muted);line-height:34px;">…</span>';
  for (var p = s; p <= e; p++) html += '<button class="page-btn' + (p === currentPage ? ' active' : '') + '" data-page="' + p + '">' + p + '</button>';
  if (e < totalPages - 1) html += '<span style="color:var(--text-muted);line-height:34px;">…</span>';
  if (e < totalPages) html += '<button class="page-btn" data-page="' + totalPages + '">' + totalPages + '</button>';
  html += '<button class="page-btn" ' + (currentPage >= totalPages ? 'disabled' : '') + ' data-page="' + (currentPage + 1) + '">›</button>';
  container.innerHTML = html;
}

document.getElementById('pageBtns').addEventListener('click', function(e) {
  var btn = e.target.closest('.page-btn');
  if (!btn || btn.disabled) return;
  currentPage = parseInt(btn.getAttribute('data-page'), 10);
  renderTable();
});

function renderAll() { renderStats(); if (hasLoadedData) renderCharts(); renderTable(); setBusy(busy); }

/* SECTION: modal helpers */
function openModal(name) { document.getElementById(name).classList.add('show'); }
function closeModal(name) {
  if (name === 'formModal' && busy) return;
  document.getElementById(name).classList.remove('show');
  if (name === 'formModal') clearPendingImages();
}
document.addEventListener('click', function(e) {
  var c = e.target.closest('[data-close]');
  if (c) closeModal(c.getAttribute('data-close'));
  if (e.target.classList.contains('modal-overlay')) closeModal(e.target.id);
});

/* SECTION: add / edit */
var editingId = null;

function clearPendingImages() {
  pendingImages.forEach(function(image) { URL.revokeObjectURL(image.url); });
  pendingImages = [];
  document.getElementById('fmImageFiles').value = '';
  document.getElementById('imagePreviews').replaceChildren();
}

function renderImagePreviews() {
  var container = document.getElementById('imagePreviews');
  container.replaceChildren();
  var saved = document.getElementById('fmPictures').value.split(/\r?\n/).map(function(reference) { return reference.trim(); }).filter(Boolean).map(function(reference) {
    var url = pictureUrl(reference);
    return url ? { url: url, name: '已保存图片' } : null;
  }).filter(Boolean);
  saved.concat(pendingImages).forEach(function(item) {
    var figure = document.createElement('figure');
    figure.className = 'image-preview';
    var image = document.createElement('img');
    image.src = item.url;
    image.alt = item.name;
    image.addEventListener('error', function() { image.hidden = true; });
    figure.appendChild(image);
    var caption = document.createElement('figcaption');
    caption.textContent = item.name;
    figure.appendChild(caption);
    if (item.file) {
      var remove = document.createElement('button');
      remove.type = 'button';
      remove.className = 'image-remove';
      remove.textContent = '×';
      remove.title = '移除图片';
      remove.setAttribute('aria-label', '移除图片 ' + item.name);
      remove.addEventListener('click', function() {
        if (busy) return;
        URL.revokeObjectURL(item.url);
        pendingImages = pendingImages.filter(function(image) { return image !== item; });
        renderImagePreviews();
      });
      figure.appendChild(remove);
    }
    container.appendChild(figure);
  });
}

document.getElementById('btnAddImage').addEventListener('click', function() { document.getElementById('fmImageFiles').click(); });
document.getElementById('fmPictures').addEventListener('input', renderImagePreviews);
document.getElementById('fmImageFiles').addEventListener('change', function(event) {
  var files = Array.from(event.target.files);
  event.target.value = '';
  if (busy) return;
  var status = document.getElementById('formStatus');
  status.textContent = '';
  if (pendingImages.length + files.length > 10) { status.textContent = '一次最多添加 10 张新图片'; return; }
  if (files.some(function(file) { return !/\.(jpe?g|png|gif|webp)$/i.test(file.name); })) {
    status.textContent = '仅支持 JPG、PNG、GIF、WebP 图片'; return;
  }
  if (files.some(function(file) { return file.size > 10 * 1024 * 1024; })) { status.textContent = '每张图片不能超过 10MB'; return; }
  files.forEach(function(file) { pendingImages.push({ file: file, url: URL.createObjectURL(file), name: file.name }); });
  renderImagePreviews();
});

function openForm(record) {
  if (busy || !(record ? permissions.change : permissions.add)) return;
  clearPendingImages();
  document.getElementById('formStatus').textContent = '';
  editingId = record ? record.id : null;
  document.getElementById('formTitle').textContent = record ? '编辑投诉 · ' + record.id : '新增投诉';
  COLUMNS.forEach(function(column) {
    var value = record ? record[column[0]] : '';
    if (column[0] === 'no' && !record) value = '(保存后自动生成)';
    if (column[0] === 'state' && !record) value = '待处理';
    var input = document.getElementById(column[2]);
    if (column[0] === 'reported_at' || column[0] === 'completion_time') {
      input.dataset.originalValue = value || '';
      input.value = value ? value.replace(/(?:Z|[+-]\d{2}:\d{2})$/, '').slice(0, 23) : '';
      input.dataset.displayValue = input.value;
    } else {
      input.value = value == null ? '' : value;
      if (input.tagName === 'SELECT') input.dataset.legacyValue = value && input.value !== value ? value : '';
    }
  });
  renderImagePreviews();
  setBusy(false);
  openModal('formModal');
}

document.getElementById('btnAdd').addEventListener('click', function() { openForm(null); });

document.getElementById('btnSave').addEventListener('click', async function() {
  if (busy || !(editingId ? permissions.change : permissions.add)) return;
  var formStatus = document.getElementById('formStatus');
  formStatus.textContent = '';
  var invalidChoice = COLUMNS.find(function(column) {
    var input = document.getElementById(column[2]);
    return input.tagName === 'SELECT' && input.dataset.legacyValue && !input.value;
  });
  if (invalidChoice) { formStatus.textContent = invalidChoice[1] + '原值不在可选范围内，请重新选择'; return; }
  var payload = {};
  COLUMNS.slice(1).forEach(function(column) {
    var input = document.getElementById(column[2]);
    var value = input.value;
    if ((column[0] === 'reported_at' || column[0] === 'completion_time') && value === input.dataset.displayValue) {
      value = input.dataset.originalValue;
    }
    payload[column[0] === 'reported_at' ? 'date' : column[0]] = value;
  });
  setBusy(true);
  try {
    if (pendingImages.length) {
      formStatus.textContent = '正在上传图片…';
      var formData = new FormData();
      pendingImages.forEach(function(image) { formData.append('images', image.file); });
      var upload = await requestData(pageRoot.dataset.imagesUrl, { method: 'POST', body: formData });
      if (!Array.isArray(upload.images) || upload.images.length !== pendingImages.length || upload.images.some(function(image) { return typeof image.path !== 'string' || !image.path; })) throw new Error('图片上传结果不完整，请重试');
      payload.defect_pictures = [payload.defect_pictures].concat(upload.images.map(function(image) { return image.path; })).filter(Boolean).join('\n');
      document.getElementById('fmPictures').value = payload.defect_pictures;
      clearPendingImages();
      renderImagePreviews();
      formStatus.textContent = '';
    }
    var result = await requestData(editingId ? recordUrl(editingId) : pageRoot.dataset.recordsUrl, {
      method: editingId ? 'PUT' : 'POST', body: JSON.stringify(payload)
    });
    setBusy(false);
    closeModal('formModal');
    if (hasLoadedData) {
      var saved = normalizeRecord(result.record);
      allData = allData.filter(function(record) { return record.id !== saved.id; }).concat([saved]);
      refreshFilterOptions();
      applyFilters();
    }
  } catch (error) {
    var messages = [];
    if (error.fields) Object.keys(error.fields).forEach(function(key) {
      var column = COLUMNS.find(function(item) { return (item[0] === 'reported_at' ? 'date' : item[0]) === key; });
      messages.push((column ? column[1] : key) + '：' + error.fields[key].map(function(item) { return item.message; }).join('；'));
    });
    formStatus.textContent = messages.length ? messages.join('；') : error.message;
  } finally {
    setBusy(false);
  }
});

/* SECTION: detail */
var detailId = null;
function openDetail(id) {
  var r = allData.find(function(x) { return x.id === id; });
  if (!r) return;
  detailId = id;
  var html = '';
  COLUMNS.forEach(function(column) {
    var full = ['complaint', 'defect_pictures', 'root_cause', 'corrective_action', 'remark'].indexOf(column[0]) >= 0;
    html += '<div class="detail-item' + (full ? ' full' : '') + '">' +
      '<span class="detail-key">' + column[1] + '</span>' +
      '<span class="detail-val">' + renderValue(r, column[0], true) + '</span></div>';
  });
  document.getElementById('detailGrid').innerHTML = html;
  openModal('detailModal');
}
document.getElementById('btnDetailEdit').addEventListener('click', function() {
  closeModal('detailModal');
  var r = allData.find(function(x) { return x.id === detailId; });
  if (r) openForm(r);
});

/* SECTION: table actions */
document.getElementById('tblBody').addEventListener('click', async function(e) {
  var btn = e.target.closest('button[data-act]');
  if (!btn || btn.disabled) return;
  var id = btn.getAttribute('data-id');
  var act = btn.getAttribute('data-act');
  var r = allData.find(function(x) { return x.id === id; });
  if (!r) return;
  if (act === 'view') openDetail(id);
  else if (act === 'edit') openForm(r);
  else if (act === 'del') {
    if (busy || !permissions.delete) return;
    if (!confirm('确认删除投诉单 ' + id + ' ？')) return;
    setBusy(true);
    try {
      await requestData(recordUrl(id), { method: 'DELETE' });
      setBusy(false);
      allData = allData.filter(function(record) { return record.id !== id; });
      refreshFilterOptions();
      applyFilters();
    } catch (error) {
      setStatus('删除失败：' + error.message);
    } finally {
      setBusy(false);
    }
  }
});

/* SECTION: filter events */
document.getElementById('btnQuery').addEventListener('click', loadRecords);
document.getElementById('btnReset').addEventListener('click', function() {
  resetDateRange();
  [typeFilter, levelFilter, statusFilter].forEach(function(filter) { filter.reset(); });
});

/* SECTION: export */
document.getElementById('btnExport').addEventListener('click', async function() {
  if (busy || exporting || !filtered.length) return;
  var records = filtered.map(function(record) {
    var data = {};
    COLUMNS.forEach(function(column) { data[column[0] === 'reported_at' ? 'date' : column[0]] = record[column[0]]; });
    return data;
  });
  var button = document.getElementById('btnExport');
  var originalLabel = button.textContent;
  var controller = new AbortController();
  var timer = setTimeout(function() { controller.abort(); }, 120000);
  exporting = true;
  button.textContent = '正在打包…';
  setBusy(busy);
  try {
    var response = await fetch(pageRoot.dataset.exportUrl, {
      method: 'POST', credentials: 'same-origin', signal: controller.signal,
      headers: { 'Content-Type': 'application/json', 'X-CSRFToken': pageRoot.dataset.csrfToken },
      body: JSON.stringify({ records: records })
    });
    if (!response.ok) {
      var error = await response.json().catch(function() { return {}; });
      throw new Error(error.error || '导出请求失败（' + response.status + '）');
    }
    if (!(response.headers.get('Content-Type') || '').includes('application/zip')) throw new Error('导出响应无效，请确认登录状态后重试');
    var blob = await response.blob();
    var url = URL.createObjectURL(blob);
    var link = document.createElement('a');
    link.href = url;
    link.download = '客户投诉_' + new Date().toISOString().slice(0, 10) + '.zip';
    link.click();
    setTimeout(function() { URL.revokeObjectURL(url); }, 1000);
  } catch (error) {
    alert('导出失败：' + (error.name === 'AbortError' ? '打包超时，请缩小查询范围后重试' : error.message));
  } finally {
    clearTimeout(timer);
    exporting = false;
    button.textContent = originalLabel;
    setBusy(busy);
  }
});

/* SECTION: resize */
window.addEventListener('resize', function() {
  Object.keys(charts).forEach(function(k) { if (charts[k]) charts[k].resize(); });
});

/* SECTION: init */
resetDateRange();
refreshFilterOptions();
renderAll();
})();
