(function () {
var page = document.querySelector('.equipment-page');
if (!page) return;
var isMobile = window.innerWidth <= 768;

/* ================= 实时时钟 ================= */
function tickClock() {
  var now = new Date();
  var hh = String(now.getHours()).padStart(2,'0');
  var mm = String(now.getMinutes()).padStart(2,'0');
  var ss = String(now.getSeconds()).padStart(2,'0');
  document.getElementById('liveClock').textContent = hh + ':' + mm + ':' + ss;
}
tickClock();
setInterval(tickClock, 1000);

/* ================= 示例数据 ================= */
var data = {
  months: ['25-11','25-12','26-01','26-02','26-03','26-04','26-05','26-06','26-07','26-08','26-09','26-10'],
  status: [
    { name: '运行', value: 96 },
    { name: '待机', value: 12 },
    { name: '维保中', value: 8 },
    { name: '故障停机', value: 12 }
  ],
  oee: [78.2, 79.5, 80.1, 81.8, 82.4, 83.0, 83.7, 84.2, 84.8, 85.0, 85.3, 85.3],
  oeeTarget: 85,
  faultTypes: ['机械磨损','电气故障','传感器异常','软件故障','过热报警','其他'],
  faultCounts: [38, 28, 22, 18, 12, 7],
  mtbf: [360, 370, 380, 390, 395, 400, 405, 410, 412, 415, 418, 420],
  mttr: [3.8, 3.6, 3.5, 3.4, 3.3, 3.2, 3.1, 3.0, 3.0, 2.9, 2.9, 2.8],
  energyLines: ['A线-冲压','B线-焊接','C线-涂装','D线-总装'],
  energyElec: [4200, 3800, 2600, 1850],
  energyGas: [300, 280, 520, 150],
  energyAir: [680, 520, 380, 220],
  maintMonths: ['05月','06月','07月','08月','09月','10月'],
  maintPlan: [42, 45, 48, 50, 52, 55],
  maintDone: [40, 44, 47, 49, 52, 53]
};

/* 帕累托累计占比 */
var totalFaults = data.faultCounts.reduce(function(a,b){return a+b;}, 0);
var cum = 0;
var cumPct = data.faultCounts.map(function(v){ cum += v; return +(cum / totalFaults * 100).toFixed(1); });

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

/* ================= 1. 设备状态分布（环形图）================= */
var statusTotal = data.status.reduce(function(a,b){return a+b.value;}, 0);
initChart('chartStatus', {
  title: baseTitle('设备状态分布'),
  tooltip: Object.assign({ trigger: 'item' }, TIP, {
    formatter: function(p) {
      if (p.componentType !== 'series') return '';
      return p.name + '<br/>数量: ' + Number(p.value).toFixed(0) + ' 台<br/>占比: ' + Number(p.percent).toFixed(1) + '%';
    }
  }),
  legend: isMobile
    ? { orient: 'horizontal', bottom: 0, left: 'center', textStyle: AX, itemWidth: 12 }
    : { orient: 'vertical', right: '4%', top: 'center', textStyle: AX, itemWidth: 12 },
  graphic: [{
    type: 'text', left: isMobile ? '38%' : '32%', top: 'center',
    style: { text: '总计\n' + statusTotal + ' 台', textAlign: 'center', fill: '#e8f2ff',
             fontSize: isMobile ? 14 : 18, fontWeight: 600 }
  }],
  color: ['#34d97e','#7d9cc9','#fac858','#ff6b6b'],
  series: [{
    name: '设备状态', type: 'pie',
    center: isMobile ? ['38%','46%'] : ['32%','55%'],
    radius: isMobile ? ['26%','48%'] : ['40%','66%'],
    avoidLabelOverlap: true,
    itemStyle: { borderColor: '#0a1934', borderWidth: 2 },
    label: { position: 'inside', formatter: '{d}%', color: '#fff', fontSize: isMobile ? 10 : 12 },
    labelLine: { show: false },
    data: data.status
  }]
});

/* ================= 2. OEE 趋势 ================= */
initChart('chartOEE', {
  title: baseTitle('设备综合效率 OEE 月度趋势'),
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
  yAxis: { type: 'value', name: 'OEE(%)', nameTextStyle: { color: '#7d9cc9', fontSize: 10 },
           min: 75, max: 90, axisLabel: AX, splitLine: SPLIT },
  series: [{
    name: 'OEE', type: 'line', smooth: true, symbol: 'circle', symbolSize: 5,
    itemStyle: { color: '#b28dff' }, lineStyle: { width: 2.5 },
    areaStyle: { color: new echarts.graphic.LinearGradient(0,0,0,1,
      [{ offset:0, color:'rgba(178,141,255,0.3)' }, { offset:1, color:'rgba(178,141,255,0.02)' }]) },
    label: { show: true, position: 'top', color: '#c9a8ff', fontSize: 10,
             formatter: function(p) { return Number(p.value).toFixed(1); } },
    markLine: { silent: true, symbol: 'none',
      lineStyle: { color: 'rgba(250,200,88,0.8)', type: 'dashed' },
      label: { formatter: '目标 85%', color: '#fac858', fontSize: 10, position: 'insideStartTop' },
      data: [{ yAxis: data.oeeTarget }] },
    data: data.oee
  }]
});

/* ================= 3. 故障类型帕累托 ================= */
initChart('chartPareto', {
  title: baseTitle('故障类型帕累托分析（近 12 月）'),
  tooltip: Object.assign({ trigger: 'axis' }, TIP, {
    formatter: function(params) {
      if (!Array.isArray(params)) return '';
      var s = params[0].axisValue + '<br/>';
      params.forEach(function(p) {
        if (p.componentType !== 'series' || p.value == null) return;
        if (p.seriesName === '累计占比') s += p.marker + p.seriesName + ': ' + Number(p.value).toFixed(1) + '%<br/>';
        else s += p.marker + p.seriesName + ': ' + Number(p.value).toFixed(0) + ' 次<br/>';
      });
      return s;
    }
  }),
  legend: { bottom: 0, left: 'center', textStyle: AX, itemWidth: 14 },
  grid: { top: isMobile ? '14%' : '16%', bottom: '18%', left: '4%', right: '4%', containLabel: true },
  xAxis: { type: 'category', data: data.faultTypes,
           axisLabel: Object.assign({}, AX, { interval: 0, rotate: isMobile ? 30 : 0 }),
           axisLine: { lineStyle: { color: 'rgba(88,140,220,0.3)' } } },
  yAxis: [
    { type: 'value', name: '次数', nameTextStyle: { color: '#7d9cc9', fontSize: 10 }, axisLabel: AX, splitLine: SPLIT },
    { type: 'value', name: '累计(%)', nameTextStyle: { color: '#7d9cc9', fontSize: 10 }, min: 0, max: 108, axisLabel: AX, splitLine: { show: false } }
  ],
  series: [
    { name: '故障次数', type: 'bar', yAxisIndex: 0, barMaxWidth: 28,
      itemStyle: { color: new echarts.graphic.LinearGradient(0,0,0,1,
        [{ offset:0, color:'#409cff' }, { offset:1, color:'rgba(64,156,255,0.3)' }]),
        borderRadius: [3,3,0,0] },
      label: { show: true, position: 'top', color: '#9ec5ff', fontSize: 10,
               formatter: function(p){ return Number(p.value).toFixed(0); } },
      data: data.faultCounts },
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

/* ================= 4. MTBF / MTTR 趋势（双轴）================= */
initChart('chartMTBF', {
  title: baseTitle('MTBF 与 MTTR 月度趋势'),
  tooltip: Object.assign({ trigger: 'axis' }, TIP, {
    formatter: function(params) {
      if (!Array.isArray(params)) return '';
      var s = params[0].axisValue + '<br/>';
      params.forEach(function(p) {
        if (p.componentType !== 'series' || p.value == null) return;
        if (p.seriesName === 'MTBF') s += p.marker + p.seriesName + ': ' + Number(p.value).toFixed(0) + ' h<br/>';
        else s += p.marker + p.seriesName + ': ' + Number(p.value).toFixed(1) + ' h<br/>';
      });
      return s;
    }
  }),
  legend: { bottom: 0, left: 'center', textStyle: AX, itemWidth: 14 },
  grid: { top: isMobile ? '14%' : '16%', bottom: '18%', left: '4%', right: '4%', containLabel: true },
  xAxis: { type: 'category', data: data.months,
           axisLabel: AX, axisLine: { lineStyle: { color: 'rgba(88,140,220,0.3)' } } },
  yAxis: [
    { type: 'value', name: 'MTBF(h)', nameTextStyle: { color: '#7d9cc9', fontSize: 10 }, axisLabel: AX, splitLine: SPLIT },
    { type: 'value', name: 'MTTR(h)', nameTextStyle: { color: '#7d9cc9', fontSize: 10 }, min: 0, max: 5,
      axisLabel: AX, splitLine: { show: false } }
  ],
  series: [
    { name: 'MTBF', type: 'bar', yAxisIndex: 0, barMaxWidth: 16,
      itemStyle: { color: '#34d97e', borderRadius: [3,3,0,0] },
      label: { show: false },
      data: data.mtbf },
    { name: 'MTTR', type: 'line', yAxisIndex: 1, smooth: true, symbol: 'circle', symbolSize: 5,
      itemStyle: { color: '#ff6b6b' }, lineStyle: { width: 2.5 },
      label: { show: true, position: 'bottom', color: '#ff9b9b', fontSize: 10,
               formatter: function(p){ return Number(p.value).toFixed(1); } },
      data: data.mttr }
  ]
});

/* ================= 5. 产线能耗分布（堆叠柱）================= */
initChart('chartEnergy', {
  title: baseTitle('10 月各产线能耗分布（kWh）'),
  tooltip: Object.assign({ trigger: 'axis', axisPointer: { type: 'shadow' } }, TIP, {
    formatter: function(params) {
      if (!Array.isArray(params)) return '';
      var s = params[0].axisValue + '<br/>';
      var total = 0;
      params.forEach(function(p) {
        if (p.componentType !== 'series' || p.value == null) return;
        s += p.marker + p.seriesName + ': ' + Number(p.value).toFixed(0) + ' kWh<br/>';
        total += Number(p.value);
      });
      s += '<b>合计: ' + total.toFixed(0) + ' kWh</b>';
      return s;
    }
  }),
  legend: { bottom: 0, left: 'center', textStyle: AX, itemWidth: 14 },
  grid: { top: isMobile ? '14%' : '16%', bottom: '18%', left: '4%', right: '4%', containLabel: true },
  xAxis: { type: 'category', data: data.energyLines,
           axisLabel: Object.assign({}, AX, { interval: 0, rotate: isMobile ? 20 : 0 }),
           axisLine: { lineStyle: { color: 'rgba(88,140,220,0.3)' } } },
  yAxis: { type: 'value', name: 'kWh', nameTextStyle: { color: '#7d9cc9', fontSize: 10 },
           axisLabel: AX, splitLine: SPLIT },
  series: [
    { name: '电力', type: 'bar', stack: 'energy', barMaxWidth: 32,
      itemStyle: { color: '#409cff', borderRadius: [0,0,0,0] },
      data: data.energyElec },
    { name: '燃气', type: 'bar', stack: 'energy',
      itemStyle: { color: '#fac858' },
      data: data.energyGas },
    { name: '压缩空气', type: 'bar', stack: 'energy',
      itemStyle: { color: '#34d97e', borderRadius: [3,3,0,0] },
      data: data.energyAir }
  ]
});

/* ================= 6. 月度保养任务完成情况 ================= */
initChart('chartMaint', {
  title: baseTitle('月度保养任务：计划 vs 完成'),
  tooltip: Object.assign({ trigger: 'axis' }, TIP, {
    formatter: function(params) {
      if (!Array.isArray(params)) return '';
      var s = params[0].axisValue + '<br/>';
      params.forEach(function(p) {
        if (p.componentType !== 'series' || p.value == null) return;
        s += p.marker + p.seriesName + ': ' + Number(p.value).toFixed(0) + ' 项<br/>';
      });
      return s;
    }
  }),
  legend: { bottom: 0, left: 'center', textStyle: AX, itemWidth: 14 },
  grid: { top: isMobile ? '14%' : '16%', bottom: '18%', left: '4%', right: '4%', containLabel: true },
  xAxis: { type: 'category', data: data.maintMonths,
           axisLabel: AX, axisLine: { lineStyle: { color: 'rgba(88,140,220,0.3)' } } },
  yAxis: { type: 'value', name: '任务数', nameTextStyle: { color: '#7d9cc9', fontSize: 10 },
           minInterval: 1, axisLabel: AX, splitLine: SPLIT },
  series: [
    { name: '计划任务', type: 'bar', barMaxWidth: 18, barGap: '30%',
      itemStyle: { color: 'rgba(64,156,255,0.55)', borderRadius: [3,3,0,0],
                   borderColor: '#409cff', borderWidth: 1 },
      label: { show: false },
      data: data.maintPlan },
    { name: '已完成', type: 'bar', barMaxWidth: 18,
      itemStyle: { color: '#34d97e', borderRadius: [3,3,0,0] },
      label: { show: true, position: 'top', color: '#7be8ab', fontSize: 10,
               formatter: function(p){ return Number(p.value).toFixed(0); } },
      data: data.maintDone }
  ]
});

/* ================= 自适应 ================= */
window.addEventListener('resize', function() {
  var nowMobile = window.innerWidth <= 768;
  if (nowMobile !== isMobile) { location.reload(); return; }
  charts.forEach(function(c) { c.resize(); });
});
var chartResizeObserver = new ResizeObserver(function() {
  charts.forEach(function(c) { c.resize(); });
});
chartResizeObserver.observe(page.querySelector('.chart-grid'));
})();
