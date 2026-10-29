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

  function validateRange() {
    endInput.setCustomValidity(startInput.value && endInput.value &&
      startInput.value > endInput.value ? '结束时间不能早于开始时间' : '');
  }

  async function loadSafety() {
    validateRange();
    if (!form.reportValidity()) return;
    if (activeController) activeController.abort();
    var controller = new AbortController();
    activeController = controller;
    var timer = setTimeout(function() { controller.abort(); }, 35000);
    var url = new URL(card.dataset.url, window.location.href);
    url.searchParams.set('start_time', startInput.value);
    url.searchParams.set('end_time', endInput.value);
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
      if (!result.available || !Number.isInteger(result.reported) || result.reported < 0 ||
          !Number.isInteger(result.completed) || result.completed < 0 ||
          !Number.isInteger(result.unclosed) || result.unclosed < 0 ||
          !Array.isArray(result.areas)) {
        throw new Error('Invalid safety response');
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
      reported.textContent = result.reported;
      details.replaceChildren.apply(details, rows);
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
  loadSafety();
})();

var isMobile = window.innerWidth <= 768;

/* ================= 示例数据（可整体替换为真实数据） ================= */
var data = {
  months: ['25-11','25-12','26-01','26-02','26-03','26-04','26-05','26-06','26-07','26-08','26-09','26-10'],
  accidents: [1,0,2,1,0,1,0,0,1,0,0,1],
  hazardFixRate: [92,95,88,94,97,93,98,99,95,98,100,97],
  defectTypes: ['尺寸超差','外观划伤','焊接缺陷','装配错位','包装破损','其他'],
  defectCounts: [42,31,18,12,7,5],
  fpy: [94.2,94.8,93.5,95.1,95.6,95.0,96.2,96.5,95.8,96.8,97.1,97.4],
  fpyTarget: 96.5,
  output: [28.5,30.2,27.8,31.5,33.0,32.4,34.1,33.6,35.2,34.8,36.0,37.2],
  otd: [95.5,94.8,96.2,95.0,96.8,97.1,96.5,97.8,98.0,97.5,98.2,98.6],
  otdTarget: 98,
  cost: [
    { name: '原材料', value: 486 },
    { name: '人工', value: 152 },
    { name: '能源动力', value: 68 },
    { name: '折旧摊销', value: 54 },
    { name: '其他费用', value: 40 }
  ],
  radarActual: [95,97,98.6,88,92],
  radarTarget: [100,96.5,98,95,90]
};

/* 帕累托累计占比 */
var totalDefects = data.defectCounts.reduce(function(a,b){return a+b;}, 0);
var cum = 0;
var cumPct = data.defectCounts.map(function(v){ cum += v; return +(cum / totalDefects * 100).toFixed(1); });

/* ================= 暗色主题通用配置 ================= */
var AX = { color: '#9db8e0', fontSize: isMobile ? 10 : 11 };
var SPLIT = { lineStyle: { color: 'rgba(88,140,220,0.15)' } };
var TIP = {
  backgroundColor: 'rgba(10,25,52,0.94)',
  borderColor: 'rgba(64,140,255,0.4)',
  textStyle: { color: '#d7e6ff', fontSize: 12 }
};
function baseTitle(text) {
  return { text: text, left: 'center', top: isMobile ? 4 : 8,
           textStyle: { fontSize: isMobile ? 13 : 14, color: '#e8f2ff', fontWeight: 600 } };
}

var charts = [];
function initChart(id, option) {
  var c = echarts.init(document.getElementById(id));
  c.setOption(option);
  charts.push(c);
  return c;
}

/* ================= S 安全：事故起数 + 隐患整改率 ================= */
initChart('chartSafety', {
  title: baseTitle('S · 安全事故与隐患整改趋势'),
  tooltip: Object.assign({ trigger: 'axis' }, TIP, {
    formatter: function(params) {
      if (!Array.isArray(params)) return '';
      var s = params[0].axisValue + '<br/>';
      params.forEach(function(p) {
        if (p.componentType !== 'series') return;
        if (p.seriesName === '隐患整改率') s += p.marker + p.seriesName + ': ' + Number(p.value).toFixed(0) + '%<br/>';
        else s += p.marker + p.seriesName + ': ' + Number(p.value).toFixed(0) + ' 起<br/>';
      });
      return s;
    }
  }),
  legend: { bottom: 0, left: 'center', textStyle: AX, itemWidth: 14 },
  grid: { top: isMobile ? '14%' : '16%', bottom: '18%', left: '4%', right: '4%', containLabel: true },
  xAxis: { type: 'category', data: data.months, axisLabel: AX, axisLine: { lineStyle: { color: 'rgba(88,140,220,0.3)' } } },
  yAxis: [
    { type: 'value', name: '事故(起)', nameTextStyle: { color: '#7d9cc9', fontSize: 10 }, minInterval: 1, axisLabel: AX, splitLine: SPLIT },
    { type: 'value', name: '整改率(%)', nameTextStyle: { color: '#7d9cc9', fontSize: 10 }, min: 80, max: 104, axisLabel: AX, splitLine: { show: false } }
  ],
  series: [
    { name: '安全事故起数', type: 'bar', yAxisIndex: 0, barMaxWidth: 16,
      itemStyle: { color: '#34d97e', borderRadius: [3,3,0,0] },
      label: { show: false },
      data: data.accidents },
    { name: '隐患整改率', type: 'line', yAxisIndex: 1, smooth: true, symbol: 'circle', symbolSize: 5,
      itemStyle: { color: '#fac858' }, lineStyle: { width: 2 },
      label: { show: false },
      data: data.hazardFixRate }
  ]
});

/* ================= Q 质量：缺陷帕累托 ================= */
initChart('chartPareto', {
  title: baseTitle('Q · 本月缺陷类型帕累托分析'),
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
  legend: { bottom: 0, left: 'center', textStyle: AX, itemWidth: 14 },
  grid: { top: isMobile ? '14%' : '16%', bottom: '18%', left: '4%', right: '4%', containLabel: true },
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

/* ================= Q 质量：一次合格率趋势 ================= */
initChart('chartFpy', {
  title: baseTitle('Q · 一次合格率（FPY）月度趋势'),
  tooltip: Object.assign({ trigger: 'axis' }, TIP, {
    formatter: function(params) {
      if (!Array.isArray(params)) return '';
      var s = params[0].axisValue + '<br/>';
      params.forEach(function(p) {
        if (p.componentType !== 'series' || p.value == null || !isFinite(p.value)) return;
        s += p.marker + p.seriesName + ': ' + Number(p.value).toFixed(1) + '%<br/>';
      });
      return s;
    }
  }),
  legend: { bottom: 0, left: 'center', textStyle: AX, itemWidth: 14 },
  grid: { top: isMobile ? '14%' : '16%', bottom: '18%', left: '4%', right: '4%', containLabel: true },
  xAxis: { type: 'category', boundaryGap: false, data: data.months,
           axisLabel: AX, axisLine: { lineStyle: { color: 'rgba(88,140,220,0.3)' } } },
  yAxis: { type: 'value', name: 'FPY(%)', nameTextStyle: { color: '#7d9cc9', fontSize: 10 },
           min: 92, max: 99, axisLabel: AX, splitLine: SPLIT },
  series: [
    { name: '一次合格率', type: 'line', smooth: true, symbol: 'circle', symbolSize: 5,
      itemStyle: { color: '#34d97e' }, lineStyle: { width: 2.5 },
      areaStyle: { color: new echarts.graphic.LinearGradient(0, 0, 0, 1,
        [{ offset: 0, color: 'rgba(52,217,126,0.35)' }, { offset: 1, color: 'rgba(52,217,126,0.02)' }]) },
      label: { show: true, position: 'top', color: '#7be8ab', fontSize: 10,
               formatter: function(p) { return Number(p.value).toFixed(1); } },
      markLine: { silent: true, symbol: 'none',
        lineStyle: { color: 'rgba(250,200,88,0.8)', type: 'dashed' },
        label: { formatter: '目标 96.5%', color: '#fac858', fontSize: 10, position: 'insideStartTop' },
        data: [{ yAxis: data.fpyTarget }] },
      data: data.fpy }
  ]
});

/* ================= D 交付：产量 + 准时交付率 ================= */
initChart('chartDelivery', {
  title: baseTitle('D · 月度产量与准时交付率'),
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
  legend: { bottom: 0, left: 'center', textStyle: AX, itemWidth: 14 },
  grid: { top: isMobile ? '14%' : '16%', bottom: '18%', left: '4%', right: '4%', containLabel: true },
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
  title: baseTitle('C · 本月制造成本构成'),
  tooltip: Object.assign({ trigger: 'item' }, TIP, {
    formatter: function(p) {
      if (p.componentType !== 'series') return '';
      return p.name + '<br/>金额: ' + Number(p.value).toFixed(0) + ' 万元<br/>占比: ' + Number(p.percent).toFixed(1) + '%';
    }
  }),
  legend: isMobile
    ? { orient: 'horizontal', bottom: 0, left: 'center', textStyle: AX, itemWidth: 12 }
    : { orient: 'vertical', right: '4%', top: 'center', textStyle: AX, itemWidth: 12 },
  graphic: [{
    type: 'text', left: isMobile ? '38%' : '32%', top: 'center',
    style: { text: '总计\n' + costTotal + ' 万元', textAlign: 'center', fill: '#e8f2ff', fontSize: isMobile ? 13 : 16, fontWeight: 600 }
  }],
  color: ['#409cff','#34d97e','#fac858','#ff9f43','#b28dff'],
  series: [{
    name: '成本构成', type: 'pie',
    center: isMobile ? ['38%','46%'] : ['32%','55%'],
    radius: isMobile ? ['26%','48%'] : ['40%','66%'],
    avoidLabelOverlap: true,
    itemStyle: { borderColor: '#0a1934', borderWidth: 2 },
    label: { position: 'inside', formatter: '{d}%', color: '#fff', fontSize: isMobile ? 10 : 12 },
    labelLine: { show: false },
    data: data.cost
  }]
});

/* ================= M 士气 + 综合：SQDCM 五维雷达 ================= */
initChart('chartRadar', {
  title: baseTitle('M · SQDCM 五维综合达成雷达'),
  tooltip: Object.assign({}, TIP),
  legend: { bottom: 0, left: 'center', textStyle: AX, itemWidth: 14 },
  radar: {
    center: ['50%', isMobile ? '52%' : '55%'],
    radius: isMobile ? '55%' : '62%',
    indicator: [
      { name: '安全\nSafety', max: 100 },
      { name: '质量\nQuality', max: 100 },
      { name: '交付\nDelivery', max: 100 },
      { name: '成本\nCost', max: 100 },
      { name: '士气\nMorale', max: 100 }
    ],
    axisName: { color: '#9db8e0', fontSize: isMobile ? 10 : 12 },
    splitLine: { lineStyle: { color: 'rgba(88,140,220,0.25)' } },
    splitArea: { areaStyle: { color: ['rgba(30,60,110,0.12)','rgba(20,45,90,0.2)'] } },
    axisLine: { lineStyle: { color: 'rgba(88,140,220,0.3)' } }
  },
  series: [{
    type: 'radar',
    symbolSize: 4,
    data: [
      { name: '本月实际', value: data.radarActual,
        itemStyle: { color: '#409cff' }, lineStyle: { width: 2, color: '#409cff' },
        areaStyle: { color: 'rgba(64,156,255,0.25)' } },
      { name: '月度目标', value: data.radarTarget,
        itemStyle: { color: '#fac858' }, lineStyle: { width: 2, color: '#fac858', type: 'dashed' },
        areaStyle: { color: 'rgba(250,200,88,0.12)' } }
    ]
  }]
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
