/* SECTION: clock */
(function() {
  function tick() {
    var now = new Date();
    document.getElementById('clock').textContent = now.toLocaleString('zh-CN', {
      year:'numeric', month:'2-digit', day:'2-digit',
      hour:'2-digit', minute:'2-digit', second:'2-digit'
    });
  }
  tick(); setInterval(tick, 1000);
})();

var FACTORIES = ['ACX', 'CNX'];
var PRODUCTS = [];
var BATCHES = [];
var ALL_DATA = [];
var selectRefresh = {};
var defaultDateFrom = document.getElementById('dateFrom').value;
var defaultDateTo = document.getElementById('dateTo').value;
var requestController;
var requestVersion = 0;
var isLoading = false;
var isExporting = false;

function escapeHtml(value) {
  return String(value).replace(/[&<>"']/g, function(character) {
    return {'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'}[character];
  });
}

/* SECTION: multi-select-component */
var selectStates = { Factory: [], Product: [], Batch: [] };
var selectData = {
  Factory: FACTORIES,
  Product: PRODUCTS,
  Batch: BATCHES
};

function updateLinkedOptions() {
  var records = ALL_DATA.filter(function(row) {
    return !selectStates.Factory.length || selectStates.Factory.includes(row.Factory);
  });
  selectData.Product = Array.from(new Set(records.filter(function(row) {
    return !selectStates.Batch.length || selectStates.Batch.includes(row.BatchCode);
  }).map(function(row) { return row.ProductNO; }).filter(Boolean))).sort();
  selectData.Batch = Array.from(new Set(records.filter(function(row) {
    return !selectStates.Product.length || selectStates.Product.includes(row.ProductNO);
  }).map(function(row) { return row.BatchCode; }).filter(Boolean))).sort();
  Object.keys(selectRefresh).forEach(function(name) { selectRefresh[name](); });
}

function initMultiSelect(name) {
  var trigger = document.getElementById('trigger' + name);
  var dropdown = document.getElementById('dropdown' + name);
  var optionsEl = document.getElementById('options' + name);
  var searchInput = dropdown.querySelector('.multi-select-search');
  var selectAllButton = dropdown.querySelector('[data-select-all]');
  var clearButton = dropdown.querySelector('[data-select-clear]');

  function renderOptions(filter) {
    filter = (filter || '').toLowerCase();
    var html = '';
    var items = selectData[name];
    for (var i = 0; i < items.length; i++) {
      var item = items[i];
      if (filter && item.toLowerCase().indexOf(filter) === -1) continue;
      var sel = selectStates[name].indexOf(item) > -1;
      html += '<div class="multi-select-option' + (sel ? ' selected' : '') + '" data-value="' + escapeHtml(item) + '">';
      html += '<span class="check">' + (sel ? '✓' : '') + '</span>';
      html += '<span>' + escapeHtml(item) + '</span></div>';
    }
    optionsEl.innerHTML = html;
    if (selectAllButton) selectAllButton.disabled = !items.length;
    if (clearButton) clearButton.disabled = !selectStates[name].length;
  }

  function renderTrigger() {
    var sel = selectStates[name];
    if (sel.length === 0) {
      trigger.textContent = name === 'Factory' ? '选择工厂' : (name === 'Product' ? '选择产品编码' : '选择车号');
    } else if (sel.length <= 2) {
      trigger.innerHTML = '';
      for (var i = 0; i < sel.length; i++) {
        var tag = document.createElement('span');
        tag.className = 'tag';
        tag.innerHTML = escapeHtml(sel[i]) + '<span class="tag-remove" data-val="' + escapeHtml(sel[i]) + '">&times;</span>';
        trigger.appendChild(tag);
      }
    } else {
      trigger.innerHTML = '';
      for (var i = 0; i < 2; i++) {
        var tag = document.createElement('span');
        tag.className = 'tag';
        tag.innerHTML = escapeHtml(sel[i]) + '<span class="tag-remove" data-val="' + escapeHtml(sel[i]) + '">&times;</span>';
        trigger.appendChild(tag);
      }
      var more = document.createElement('span');
      more.className = 'tag tag-more';
      more.textContent = '+' + (sel.length - 2);
      trigger.appendChild(more);
    }
  }

  trigger.addEventListener('click', function(e) {
    if (e.target.classList.contains('tag-remove')) {
      var val = e.target.getAttribute('data-val');
      selectStates[name] = selectStates[name].filter(function(v){ return v !== val; });
      updateLinkedOptions();
      return;
    }
    document.querySelectorAll('.multi-select-dropdown.show').forEach(function(d) {
      if (d !== dropdown) d.classList.remove('show');
    });
    dropdown.classList.toggle('show');
    trigger.classList.toggle('open', dropdown.classList.contains('show'));
    if (dropdown.classList.contains('show')) {
      searchInput.value = '';
      renderOptions('');
      setTimeout(function() { searchInput.focus(); }, 50);
    }
  });

  searchInput.addEventListener('input', function() { renderOptions(this.value); });

  if (selectAllButton) {
    selectAllButton.addEventListener('click', function() {
      selectStates[name] = selectData[name].slice();
      updateLinkedOptions();
    });
  }
  if (clearButton) {
    clearButton.addEventListener('click', function() {
      selectStates[name] = [];
      updateLinkedOptions();
    });
  }

  optionsEl.addEventListener('click', function(e) {
    var opt = e.target.closest('.multi-select-option');
    if (!opt) return;
    var val = opt.getAttribute('data-value');
    var idx = selectStates[name].indexOf(val);
    if (idx > -1) {
      selectStates[name].splice(idx, 1);
    } else {
      selectStates[name].push(val);
    }
    updateLinkedOptions();
  });

  renderOptions('');
  renderTrigger();
  selectRefresh[name] = function() {
    renderOptions(searchInput.value);
    renderTrigger();
  };
}

initMultiSelect('Factory');
initMultiSelect('Product');
initMultiSelect('Batch');

document.addEventListener('click', function(e) {
  if (!e.target.closest('.multi-select')) {
    document.querySelectorAll('.multi-select-dropdown.show').forEach(function(d) {
      d.classList.remove('show');
    });
    document.querySelectorAll('.multi-select-trigger.open').forEach(function(t) {
      t.classList.remove('open');
    });
  }
});

/* SECTION: query-logic */
var filteredData = ALL_DATA.slice();
var currentPage = 1;
var pageSize = 20;
var sortCol = '';
var sortDir = 'desc';

async function doQuery() {
  var fFrom = document.getElementById('dateFrom').value;
  var fTo = document.getElementById('dateTo').value;
  var selectedProducts = selectStates.Product.slice();
  var selectedBatches = selectStates.Batch.slice();
  var version = ++requestVersion;
  if (requestController) requestController.abort();
  requestController = new AbortController();
  var status = document.getElementById('queryStatus');
  isLoading = true;
  ALL_DATA = [];
  filteredData = [];
  currentPage = 1;
  updateAll();
  setQueryButtons();
  status.textContent = '正在查询...';
  status.dataset.state = 'loading';
  try {
    if (!fFrom || !fTo || fFrom > fTo) throw new Error('请选择有效的日期范围');
    var url = new URL(document.getElementById('copDataMain').dataset.url, location.origin);
    url.searchParams.set('date_from', fFrom);
    url.searchParams.set('date_to', fTo);
    selectStates.Factory.forEach(function(factory) { url.searchParams.append('factory', factory); });
    var response = await fetch(url, {signal: requestController.signal});
    var payload = await response.json();
    if (!response.ok) throw new Error(payload.error || '查询失败，请稍后重试');
    if (version !== requestVersion) return;
    ALL_DATA = payload.records;
    updateLinkedOptions();
    filteredData = ALL_DATA.filter(function(row) {
      return (!selectedProducts.length || selectedProducts.includes(row.ProductNO)) &&
        (!selectedBatches.length || selectedBatches.includes(row.BatchCode));
    });
    if (sortCol) applySortToData();
    status.textContent = filteredData.length ? '查询完成，共 ' + filteredData.length + ' 条' : '暂无符合条件的数据';
    status.dataset.state = 'success';
  } catch (error) {
    if (version !== requestVersion || error.name === 'AbortError') return;
    ALL_DATA = [];
    filteredData = [];
    updateLinkedOptions();
    status.textContent = error instanceof TypeError || error instanceof SyntaxError ? '查询失败，请检查网络后重试' : error.message;
    status.dataset.state = 'error';
  } finally {
    if (version === requestVersion) {
      isLoading = false;
      updateAll();
      setQueryButtons();
    }
  }
}

function doReset() {
  selectStates.Factory = [];
  selectStates.Product = [];
  selectStates.Batch = [];
  document.getElementById('dateFrom').value = defaultDateFrom;
  document.getElementById('dateTo').value = defaultDateTo;
  ['Factory','Product','Batch'].forEach(function(n) {
    document.getElementById('dropdown' + n).querySelector('.multi-select-search').value = '';
    document.getElementById('dropdown' + n).classList.remove('show');
    document.getElementById('trigger' + n).classList.remove('open');
    selectRefresh[n]();
  });
  sortCol = '';
  sortDir = 'desc';
  document.querySelectorAll('#dataTable th').forEach(function(th) { th.classList.remove('sorted'); });
  return doQuery();
}

function setQueryButtons() {
  document.getElementById('btnQuery').disabled = isLoading;
  document.getElementById('btnExport').disabled = isLoading || isExporting || !filteredData.length;
  document.getElementById('btnCopy').disabled = isLoading || !filteredData.length;
  document.querySelector('.copdata-content').setAttribute('aria-busy', String(isLoading));
}

document.getElementById('btnQuery').addEventListener('click', doQuery);
document.getElementById('btnReset').addEventListener('click', doReset);

/* SECTION: sort */
function applySortToData() {
  filteredData.sort(function(a, b) {
    var va = a[sortCol], vb = b[sortCol];
    if (va == null) return vb == null ? 0 : 1;
    if (vb == null) return -1;
    if (typeof va === 'number') {
      return sortDir === 'asc' ? va - vb : vb - va;
    }
    va = String(va); vb = String(vb);
    return sortDir === 'asc' ? va.localeCompare(vb) : vb.localeCompare(va);
  });
}

document.querySelectorAll('#dataTable th[data-col]').forEach(function(th) {
  th.addEventListener('click', function() {
    var col = th.getAttribute('data-col');
    if (col === 'index') return;
    if (sortCol === col) {
      sortDir = sortDir === 'asc' ? 'desc' : 'asc';
    } else {
      sortCol = col;
      sortDir = 'desc';
    }
    document.querySelectorAll('#dataTable th').forEach(function(h){ h.classList.remove('sorted'); });
    th.classList.add('sorted');
    th.querySelector('.sort-icon').textContent = sortDir === 'asc' ? '↑' : '↓';
    applySortToData();
    renderTable();
  });
});

/* SECTION: render-table */
function renderTable() {
  var tbody = document.getElementById('tableBody');
  var start = (currentPage - 1) * pageSize;
  var end = Math.min(start + pageSize, filteredData.length);
  var page = filteredData.slice(start, end);
  var keys = ['BegDate','Factory','ProductNO','BatchCode','decVal4','decVal1','decVal2','decVal7','decVal8','decVal9','decVal12','decVal29','decVal19','decVal20','decVal21'];
  tbody.replaceChildren();
  page.forEach(function(row, index) {
    var tableRow = document.createElement('tr');
    var numberCell = document.createElement('td');
    numberCell.textContent = start + index + 1;
    tableRow.appendChild(numberCell);
    keys.forEach(function(key) {
      var cell = document.createElement('td');
      cell.textContent = row[key] == null ? '-' : row[key];
      if (key.startsWith('decVal')) cell.className = 'val-cell';
      tableRow.appendChild(cell);
    });
    tbody.appendChild(tableRow);
  });
  if (!page.length) {
    var emptyRow = document.createElement('tr');
    var emptyCell = document.createElement('td');
    emptyCell.colSpan = 16;
    emptyCell.textContent = isLoading ? '正在查询...' : '暂无数据';
    emptyRow.appendChild(emptyCell);
    tbody.appendChild(emptyRow);
  }
  document.getElementById('tableCount').textContent = '显示 ' + (filteredData.length ? start + 1 : 0) + '-' + end + ' / 共 ' + filteredData.length + ' 条';
  document.getElementById('pageInfo').textContent = '共 ' + filteredData.length + ' 条记录';
  renderPagination();
}

function renderPagination() {
  var totalPages = Math.ceil(filteredData.length / pageSize);
  var container = document.getElementById('pageBtns');
  var html = '';

  html += '<button class="page-btn" ' + (currentPage <= 1 ? 'disabled' : '') + ' data-page="' + (currentPage - 1) + '">‹</button>';

  var startPage = Math.max(1, currentPage - 2);
  var endPage = Math.min(totalPages, currentPage + 2);

  if (startPage > 1) {
    html += '<button class="page-btn" data-page="1">1</button>';
    if (startPage > 2) html += '<span style="color:var(--text-muted);line-height:36px;">…</span>';
  }

  for (var p = startPage; p <= endPage; p++) {
    html += '<button class="page-btn' + (p === currentPage ? ' active' : '') + '" data-page="' + p + '">' + p + '</button>';
  }

  if (endPage < totalPages) {
    if (endPage < totalPages - 1) html += '<span style="color:var(--text-muted);line-height:36px;">…</span>';
    html += '<button class="page-btn" data-page="' + totalPages + '">' + totalPages + '</button>';
  }

  html += '<button class="page-btn" ' + (currentPage >= totalPages ? 'disabled' : '') + ' data-page="' + (currentPage + 1) + '">›</button>';

  container.innerHTML = html;
}

document.getElementById('pageBtns').addEventListener('click', function(e) {
  var btn = e.target.closest('.page-btn');
  if (!btn || btn.disabled) return;
  currentPage = parseInt(btn.getAttribute('data-page'));
  renderTable();
});

/* SECTION: update-stats */
function updateStats() {
  document.getElementById('statCount').textContent = filteredData.length;

  if (filteredData.length === 0) {
    document.getElementById('statStrength').textContent = '-';
    document.getElementById('statWidth').textContent = '-';
    document.getElementById('statThickness').textContent = '-';
    return;
  }

  [['statStrength', 'decVal4', 1], ['statWidth', 'decVal1', 2], ['statThickness', 'decVal2', 3]].forEach(function(metric) {
    var value = averageValue(filteredData, metric[1]);
    document.getElementById(metric[0]).textContent = value === null ? '-' : value.toFixed(metric[2]);
  });
}

function averageValue(records, key) {
  var values = records.map(function(row) { return row[key]; }).filter(Number.isFinite);
  return values.length ? values.reduce(function(sum, value) { return sum + value; }, 0) / values.length : null;
}

/* SECTION: update-charts */
var chartStrength, chartColor;

function updateCharts() {
  if (!chartStrength) chartStrength = echarts.init(document.getElementById('chartStrength'));
  if (!chartColor) chartColor = echarts.init(document.getElementById('chartColor'));

  // Group by date for strength trend
  var dateMap = {};
  for (var i = 0; i < filteredData.length; i++) {
    var d = filteredData[i].BegDate.slice(0, 10);
    if (!dateMap[d]) dateMap[d] = [];
    dateMap[d].push(filteredData[i]);
  }
  var dates = Object.keys(dateMap).sort();
  var avgStrength = [], avgWidth = [];
  for (var i = 0; i < dates.length; i++) {
    var arr = dateMap[dates[i]];
    var strength = averageValue(arr, 'decVal4');
    var width = averageValue(arr, 'decVal1');
    avgStrength.push(strength === null ? null : +strength.toFixed(1));
    avgWidth.push(width === null ? null : +width.toFixed(2));
  }

  chartStrength.setOption({
    tooltip: { trigger: 'axis', backgroundColor: 'rgba(10,22,40,0.95)', borderColor: 'rgba(0,212,255,0.2)', textStyle: { color: '#e0e6ed', fontSize: 12 } },
    legend: { bottom: 0, left: 'center', textStyle: { color: '#6b7b8d', fontSize: 11 } },
    grid: { top: '10%', bottom: '18%', left: '8%', right: '8%', containLabel: true },
    xAxis: { type: 'category', data: dates, axisLine: { lineStyle: { color: 'rgba(255,255,255,0.08)' } }, axisLabel: { color: '#6b7b8d', fontSize: 10, rotate: 30 } },
    yAxis: [
      { type: 'value', name: '强力(N)', nameTextStyle: { color: '#6b7b8d' }, splitLine: { lineStyle: { color: 'rgba(255,255,255,0.04)' } }, axisLabel: { color: '#6b7b8d', fontSize: 11 } },
      { type: 'value', name: '宽度(mm)', nameTextStyle: { color: '#6b7b8d' }, splitLine: { show: false }, axisLabel: { color: '#6b7b8d', fontSize: 11 } }
    ],
    series: [
      { name: '平均强力', type: 'line', smooth: true, data: avgStrength, lineStyle: { color: '#00d4ff', width: 2 }, itemStyle: { color: '#00d4ff' },
        areaStyle: { color: { type: 'linear', x: 0, y: 0, x2: 0, y2: 1, colorStops: [{ offset: 0, color: 'rgba(0,212,255,0.2)' }, { offset: 1, color: 'rgba(0,212,255,0.02)' }] } }, symbol: 'circle', symbolSize: 4 },
      { name: '平均宽度', type: 'line', smooth: true, yAxisIndex: 1, data: avgWidth, lineStyle: { color: '#00ffa3', width: 2 }, itemStyle: { color: '#00ffa3' }, symbol: 'circle', symbolSize: 4 }
    ]
  });

  // Color delta distribution
  var dl = [], da = [], db = [], labels = [];
  var recent = filteredData.slice(0, 50);
  for (var i = 0; i < recent.length; i++) {
    labels.push(recent[i].BatchCode);
    dl.push(recent[i].decVal19);
    da.push(recent[i].decVal20);
    db.push(recent[i].decVal21);
  }

  chartColor.setOption({
    tooltip: { trigger: 'axis', backgroundColor: 'rgba(10,22,40,0.95)', borderColor: 'rgba(0,212,255,0.2)', textStyle: { color: '#e0e6ed', fontSize: 12 } },
    legend: { bottom: 0, left: 'center', textStyle: { color: '#6b7b8d', fontSize: 11 } },
    grid: { top: '10%', bottom: '18%', left: '8%', right: '4%', containLabel: true },
    xAxis: { type: 'category', data: labels, axisLine: { lineStyle: { color: 'rgba(255,255,255,0.08)' } }, axisLabel: { color: '#6b7b8d', fontSize: 9, rotate: 45, interval: 4 } },
    yAxis: { type: 'value', splitLine: { lineStyle: { color: 'rgba(255,255,255,0.04)' } }, axisLabel: { color: '#6b7b8d', fontSize: 11 } },
    series: [
      { name: 'ΔL', type: 'bar', data: dl, barMaxWidth: 10, itemStyle: { color: '#00d4ff', borderRadius: [2,2,0,0] } },
      { name: 'ΔA', type: 'bar', data: da, barMaxWidth: 10, itemStyle: { color: '#00ffa3', borderRadius: [2,2,0,0] } },
      { name: 'ΔB', type: 'bar', data: db, barMaxWidth: 10, itemStyle: { color: '#ffaa00', borderRadius: [2,2,0,0] } }
    ]
  });
}

/* SECTION: update-all */
function updateAll() {
  updateStats();
  updateCharts();
  renderTable();
}

/* SECTION: export */
document.getElementById('btnExport').addEventListener('click', async function() {
  if (filteredData.length === 0) { alert('没有数据可导出'); return; }
  if (isExporting) return;
  var headers = ['送检时间','工厂','产品编码','车号','强力(N)','宽度(mm)','厚度(mm)','干摩','湿摩','颜色','甲醇(mg/kg)','延伸率11.12KN(%)','ΔL','ΔA','ΔB'];
  var keys = ['BegDate','Factory','ProductNO','BatchCode','decVal4','decVal1','decVal2','decVal7','decVal8','decVal9','decVal12','decVal29','decVal19','decVal20','decVal21'];
  var records = filteredData.slice();
  var button = document.getElementById('btnExport');
  var originalLabel = button.textContent;
  isExporting = true;
  button.textContent = '正在导出...';
  setQueryButtons();
  try {
    var workbook = new ExcelJS.Workbook();
    var sheet = workbook.addWorksheet('COP检测数据', {
      views: [{state: 'frozen', ySplit: 1}]
    });
    sheet.columns = headers.map(function(header, index) {
      return {header: header, key: keys[index], width: index === 0 ? 22 : (index < 4 ? 20 : 18)};
    });
    records.forEach(function(record) {
      sheet.addRow(keys.map(function(key, index) {
        var value = record[key];
        return index < 4 ? String(value == null ? '' : value) : (value == null ? null : value);
      }));
    });
    sheet.getRow(1).font = {bold: true, color: {argb: 'FFFFFFFF'}};
    sheet.getRow(1).fill = {type: 'pattern', pattern: 'solid', fgColor: {argb: 'FF2463C5'}};
    sheet.autoFilter = {from: {row: 1, column: 1}, to: {row: 1, column: keys.length}};
    var buffer = await workbook.xlsx.writeBuffer();
    var blob = new Blob([buffer], {type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'});
    var url = URL.createObjectURL(blob);
    var link = document.createElement('a');
    link.href = url;
    link.download = 'COP数据_' + new Date().toISOString().slice(0, 10) + '.xlsx';
    document.body.appendChild(link);
    link.click();
    link.remove();
    setTimeout(function() { URL.revokeObjectURL(url); }, 1000);
  } catch (error) {
    var status = document.getElementById('queryStatus');
    status.textContent = 'Excel导出失败，请稍后重试或缩小查询范围';
    status.dataset.state = 'error';
  } finally {
    isExporting = false;
    button.textContent = originalLabel;
    setQueryButtons();
  }
});

/* SECTION: copy */
document.getElementById('btnCopy').addEventListener('click', function() {
  var headers = ['送检时间','工厂','产品编码','车号','强力','宽度','厚度','干摩','湿摩','颜色','甲醇','延伸率','ΔL','ΔA','ΔB'];
  var keys = ['BegDate','Factory','ProductNO','BatchCode','decVal4','decVal1','decVal2','decVal7','decVal8','decVal9','decVal12','decVal29','decVal19','decVal20','decVal21'];
  var text = headers.join('\t') + '\n';
  for (var i = 0; i < filteredData.length; i++) {
    var row = [];
    for (var j = 0; j < keys.length; j++) {
      row.push(filteredData[i][keys[j]]);
    }
    text += row.join('\t') + '\n';
  }
  if (!navigator.clipboard) {
    document.getElementById('queryStatus').textContent = '当前浏览器不支持复制，请使用导出';
    return;
  }
  navigator.clipboard.writeText(text).then(function() {
    var btn = document.getElementById('btnCopy');
    btn.textContent = '✓ 已复制';
    setTimeout(function() { btn.textContent = '📋 复制'; }, 2000);
  }).catch(function() {
    document.getElementById('queryStatus').textContent = '复制失败，请检查剪贴板权限或使用导出';
  });
});

/* SECTION: resize */
window.addEventListener('resize', function() {
  if (chartStrength) chartStrength.resize();
  if (chartColor) chartColor.resize();
});

var chartObserver = new ResizeObserver(function() {
  if (chartStrength) chartStrength.resize();
  if (chartColor) chartColor.resize();
});
document.querySelectorAll('.chart-box').forEach(function(element) { chartObserver.observe(element); });

/* SECTION: init */
doQuery();
