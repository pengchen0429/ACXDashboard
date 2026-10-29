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

/* ================= 示例数据 ================= */
var DATA = {
  months: ['26-01','26-02','26-03','26-04','26-05','26-06','26-07','26-08','26-09','26-10'],

  overview: {
    beltTypes: ['平带','松紧带','织带','绳带','提花带'],
    beltDPMU: [1200, 1850, 980, 2100, 1560],
    totalDPMU: 1650,
    monthlyTrend: [2100, 1980, 1850, 1920, 1780, 1650, 1720, 1680, 1590, 1650],
    dyeMachines: ['1#染机','2#染机','3#染机','4#染机','5#染机'],
    dyeDPMU: [1800, 1500, 2200, 1650, 1900],
    dyeProd: [12.0, 15.0, 8.0, 13.5, 10.0],
    defectTypes: ['色差','断经','断纬','色斑','跳纱','油污','缩水不良','起毛'],
    defectDPMU: [420, 380, 310, 280, 220, 180, 150, 110],
    scrapMonthly: [120, 98, 85, 92, 78, 65, 72, 68, 55, 60],
    dyeProdMonthly: [45, 48, 42, 46, 50, 47, 52, 49, 53, 51],
    beltProd: [25, 18, 32, 12, 15],
    needleTypes: ['单针','双针'],
    needleDPMU: [1450, 1780],
    needleProd: [55, 47]
  },

  weaving: {
    machines: ['1#织机','2#织机','3#织机','4#织机','5#织机','6#织机','7#织机','8#织机'],
    machineDPMU: [1100, 1350, 980, 1500, 1200, 1680, 1050, 1420],
    totalDPMU: 1280,
    monthlyTrend: [1800, 1650, 1520, 1480, 1380, 1320, 1280, 1250, 1300, 1280],
    machineProd: [8.0, 7.5, 9.2, 6.8, 8.5, 6.2, 9.5, 7.8],
    defectTypes: ['断经','断纬','跳纱','稀密路','边不良','油污','幅宽不良'],
    defectDPMU: [380, 310, 220, 180, 150, 120, 80],
    scrapMonthly: [85, 72, 65, 68, 58, 52, 48, 45, 42, 40],
    prodMonthly: [32, 34, 31, 33, 35, 34, 36, 35, 37, 36],
    beltDPMU: [1100, 1580, 850, 1800, 1350],
    beltProd: [22, 16, 28, 10, 13],
    needleDPMU: [1150, 1480],
    needleProd: [48, 41]
  },

  dyeing: {
    machines: ['1#染机','2#染机','3#染机','4#染机','5#染机'],
    machineDPMU: [1800, 1500, 2200, 1650, 1900],
    totalDPMU: 1820,
    monthlyTrend: [2400, 2200, 2100, 2050, 1950, 1880, 1820, 1780, 1850, 1820],
    machineProd: [12.0, 15.0, 8.0, 13.5, 10.0],
    defectTypes: ['色差','色斑','色花','缸差','缩水不良','手感不良'],
    defectDPMU: [480, 350, 280, 220, 180, 120],
    scrapMonthly: [65, 58, 52, 48, 42, 38, 35, 32, 28, 30],
    prodMonthly: [45, 48, 42, 46, 50, 47, 52, 49, 53, 51],
    beltDPMU: [1500, 2100, 1200, 2400, 1800],
    beltProd: [20, 14, 25, 9, 12],
    colorSystems: ['黑色系','白色系','红色系','蓝色系','绿色系'],
    colorDPMU: [1650, 1920, 2100, 1780, 1550],
    colorProd: [18, 15, 12, 16, 10]
  }
};

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

function disposeCharts() {
  chartInstances.forEach(function(c) { c.dispose(); });
  chartInstances = [];
}

function initChart(id, option) {
  var el = document.getElementById(id);
  if (!el) return;
  var chart = echarts.init(el);
  chart.setOption(option);
  chartInstances.push(chart);
  return chart;
}

/* ================= 图表构建函数 ================= */

/* 垂直柱状图 */
function barOpt(title, cats, vals, color, unit) {
  var u = unit || '';
  return {
    title: baseTitle(title),
    tooltip: Object.assign({ trigger: 'axis' }, TIP, {
      formatter: function(params) {
        if (!Array.isArray(params)) return '';
        var s = params[0].axisValue + '<br/>';
        params.forEach(function(p) {
          if (p.componentType !== 'series' || p.value == null) return;
          s += p.marker + p.seriesName + ': ' + Number(p.value).toFixed(0) + u + '<br/>';
        });
        return s;
      }
    }),
    grid: { top: isMobile ? '16%' : '18%', bottom: '12%', left: '3%', right: '3%', containLabel: true },
    xAxis: { type: 'category', data: cats,
             axisLabel: Object.assign({}, AX, { interval: 0, rotate: cats.length > 6 ? 25 : 0 }),
             axisLine: { lineStyle: { color: 'rgba(88,140,220,0.3)' } } },
    yAxis: { type: 'value', axisLabel: AX, splitLine: SPLIT },
    series: [{
      name: title.replace(/各|DPMU|趋势|占自身产量/g,'').trim() || 'DPMU',
      type: 'bar', barMaxWidth: 26,
      itemStyle: { color: color || '#409cff', borderRadius: [3,3,0,0] },
      label: { show: true, position: 'top', color: '#9ec5ff', fontSize: 10,
               formatter: function(p) { return Number(p.value).toFixed(0); } },
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
        var p = params[0];
        if (p.componentType !== 'series' || p.value == null) return '';
        return p.name + '<br/>' + p.marker + 'DPMU: ' + Number(p.value).toFixed(0) + u;
      }
    }),
    grid: { top: isMobile ? '16%' : '18%', bottom: '6%', left: '3%', right: '10%', containLabel: true },
    xAxis: { type: 'value', axisLabel: AX, splitLine: SPLIT },
    yAxis: { type: 'category', data: cats, inverse: true,
             axisLabel: Object.assign({}, AX, { width: 70, overflow: 'truncate' }),
             axisLine: { lineStyle: { color: 'rgba(88,140,220,0.3)' } } },
    series: [{
      name: 'DPMU', type: 'bar', barMaxWidth: 16,
      itemStyle: { color: color || '#409cff', borderRadius: [0,3,3,0] },
      label: { show: true, position: 'right', color: '#9ec5ff', fontSize: 10,
               formatter: function(p) { return Number(p.value).toFixed(0); } },
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
        var s = params[0].axisValue + '<br/>';
        params.forEach(function(p) {
          if (p.componentType !== 'series' || p.value == null || !isFinite(p.value)) return;
          s += p.marker + p.seriesName + ': ' + Number(p.value).toFixed(0) + u + '<br/>';
        });
        return s;
      }
    }),
    legend: { show: false },
    grid: { top: isMobile ? '16%' : '18%', bottom: '12%', left: '3%', right: '3%', containLabel: true },
    xAxis: { type: 'category', boundaryGap: false, data: months, axisLabel: AX,
             axisLine: { lineStyle: { color: 'rgba(88,140,220,0.3)' } } },
    yAxis: { type: 'value', axisLabel: AX, splitLine: SPLIT },
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
      axisLabel: { distance: 26, color: '#7d9cc9', fontSize: isMobile ? 9 : 10 },
      anchor: { show: true, size: 10, itemStyle: { color: '#409cff', borderColor: '#e8f2ff', borderWidth: 2 } },
      title: { show: false },
      detail: {
        valueAnimation: true, formatter: '{value}',
        color: '#e8f2ff', fontSize: isMobile ? 26 : 34, fontWeight: 700,
        offsetCenter: [0, '35%']
      },
      data: [{ value: value }]
    }]
  };
}

/* 带产量标注的柱状图 */
function barWithProdOpt(title, cats, dpmuVals, prodVals, color, prodUnit) {
  var pu = prodUnit || '万米';
  return {
    title: baseTitle(title),
    tooltip: Object.assign({ trigger: 'axis' }, TIP, {
      formatter: function(params) {
        if (!Array.isArray(params)) return '';
        var s = params[0].axisValue + '<br/>';
        params.forEach(function(p) {
          if (p.componentType !== 'series' || p.value == null) return;
          s += p.marker + p.seriesName + ': ' + Number(p.value).toFixed(0) + '<br/>';
        });
        return s;
      }
    }),
    legend: { bottom: 0, left: 'center', textStyle: AX, itemWidth: 14 },
    grid: { top: isMobile ? '16%' : '18%', bottom: '18%', left: '3%', right: '3%', containLabel: true },
    xAxis: { type: 'category', data: cats,
             axisLabel: Object.assign({}, AX, { interval: 0, rotate: cats.length > 5 ? 20 : 0 }),
             axisLine: { lineStyle: { color: 'rgba(88,140,220,0.3)' } } },
    yAxis: [
      { type: 'value', name: 'DPMU', nameTextStyle: { color: '#7d9cc9', fontSize: 10 }, axisLabel: AX, splitLine: SPLIT },
      { type: 'value', name: '产量(' + pu + ')', nameTextStyle: { color: '#7d9cc9', fontSize: 10 }, axisLabel: AX, splitLine: { show: false } }
    ],
    series: [
      { name: 'DPMU', type: 'bar', yAxisIndex: 0, barMaxWidth: 22,
        itemStyle: { color: color || '#409cff', borderRadius: [3,3,0,0] },
        label: { show: true, position: 'top', color: '#9ec5ff', fontSize: 10,
                 formatter: function(p) { return Number(p.value).toFixed(0); } },
        data: dpmuVals },
      { name: '产量(' + pu + ')', type: 'bar', yAxisIndex: 1, barMaxWidth: 22,
        itemStyle: { color: 'rgba(250,200,88,0.5)', borderRadius: [3,3,0,0] },
        label: { show: false },
        data: prodVals }
    ]
  };
}

/* ================= Tab 构建函数 ================= */

function buildOverview() {
  var d = DATA.overview;
  initChart('chart1', barOpt('各带型 DPMU', d.beltTypes, d.beltDPMU, '#409cff'));
  initChart('chart2', gaugeOpt('DPMU TOTAL', d.totalDPMU, 5000));
  initChart('chart3', lineOpt('各月 DPMU 趋势', DATA.months, d.monthlyTrend, 1500, '#b28dff'));
  initChart('chart4', hbarOpt('各染机 DPMU 占自身产量', d.dyeMachines, d.dyeDPMU, '#34d97e'));
  initChart('chart5', hbarOpt('各疵点名 DPMU', d.defectTypes, d.defectDPMU, '#fac858'));
  initChart('chart6', barOpt('报废数量（月度）', DATA.months, d.scrapMonthly, '#ff6b6b', ' 件'));
  initChart('chart7', barOpt('染色报产（万米/月）', DATA.months, d.dyeProdMonthly, '#ff9f43', ' 万米'));
  initChart('chart8', barWithProdOpt('各带型 DPMU 占自身产量', d.beltTypes, d.beltDPMU, d.beltProd, '#409cff'));
  initChart('chart9', barWithProdOpt('单双针 DPMU 占自身产量', d.needleTypes, d.needleDPMU, d.needleProd, '#b28dff'));
}

function buildWeaving() {
  var d = DATA.weaving;
  initChart('chart1', barOpt('各织机 DPMU', d.machines, d.machineDPMU, '#409cff'));
  initChart('chart2', gaugeOpt('织造 DPMU TOTAL', d.totalDPMU, 5000));
  initChart('chart3', lineOpt('各月织造 DPMU 趋势', DATA.months, d.monthlyTrend, 1200, '#409cff'));
  initChart('chart4', hbarOpt('各织机 DPMU 占自身产量', d.machines, d.machineDPMU, '#34d97e'));
  initChart('chart5', hbarOpt('织造各疵点 DPMU', d.defectTypes, d.defectDPMU, '#fac858'));
  initChart('chart6', barOpt('织造报废数量（月度）', DATA.months, d.scrapMonthly, '#ff6b6b', ' 件'));
  initChart('chart7', barOpt('织造报产（万米/月）', DATA.months, d.prodMonthly, '#ff9f43', ' 万米'));
  initChart('chart8', barWithProdOpt('各带型 DPMU（织造）', DATA.overview.beltTypes, d.beltDPMU, d.beltProd, '#409cff'));
  initChart('chart9', barWithProdOpt('单双针 DPMU（织造）', DATA.overview.needleTypes, d.needleDPMU, d.needleProd, '#b28dff'));
}

function buildDyeing() {
  var d = DATA.dyeing;
  initChart('chart1', barOpt('各染机 DPMU', d.machines, d.machineDPMU, '#ff9f43'));
  initChart('chart2', gaugeOpt('染色 DPMU TOTAL', d.totalDPMU, 5000));
  initChart('chart3', lineOpt('各月染色 DPMU 趋势', DATA.months, d.monthlyTrend, 1500, '#ff9f43'));
  initChart('chart4', hbarOpt('各染机 DPMU 占自身产量', d.machines, d.machineDPMU, '#34d97e'));
  initChart('chart5', hbarOpt('染色各疵点 DPMU', d.defectTypes, d.defectDPMU, '#fac858'));
  initChart('chart6', barOpt('染色报废数量（月度）', DATA.months, d.scrapMonthly, '#ff6b6b', ' 件'));
  initChart('chart7', barOpt('染色报产（万米/月）', DATA.months, d.prodMonthly, '#ff9f43', ' 万米'));
  initChart('chart8', barWithProdOpt('各带型 DPMU（染色）', DATA.overview.beltTypes, d.beltDPMU, d.beltProd, '#ff9f43'));
  initChart('chart9', barWithProdOpt('各色系 DPMU 占自身产量', d.colorSystems, d.colorDPMU, d.colorProd, '#b28dff'));
}

/* ================= Tab 切换 ================= */
var currentTab = 'overview';
var tabTimer;

function switchTab(tab) {
  if (tab === currentTab && chartInstances.length > 0) return;
  currentTab = tab;

  // 更新按钮样式
  page.querySelectorAll('.tab-btn').forEach(function(btn) {
    btn.classList.toggle('active', btn.dataset.tab === tab);
    btn.setAttribute('aria-pressed', String(btn.dataset.tab === tab));
  });

  // 淡出 → 销毁 → 重建 → 淡入
  var grid = document.getElementById('chartGrid');
  grid.classList.add('fading');
  clearTimeout(tabTimer);
  tabTimer = setTimeout(function() {
    disposeCharts();
    if (tab === 'overview') buildOverview();
    else if (tab === 'weaving') buildWeaving();
    else if (tab === 'dyeing') buildDyeing();
    grid.classList.remove('fading');
  }, 200);
}

/* ================= 初始化 ================= */
page.querySelectorAll('.tab-btn').forEach(function(btn) {
  btn.addEventListener('click', function() {
    switchTab(btn.dataset.tab);
  });
});
document.getElementById('dpmuQuery').addEventListener('click', function() {
  window.alert('\u7b5b\u9009\u529f\u80fd\u9700\u63a5\u5165\u540e\u7aef\u6570\u636e\u6e90\u540e\u751f\u6548');
});
buildOverview();

/* ================= 自适应 ================= */
function resizeCharts() {
  var nowMobile = page.clientWidth <= 768;
  if (nowMobile !== isMobile) {
    isMobile = nowMobile;
    AX.fontSize = isMobile ? 10 : 11;
    clearTimeout(tabTimer);
    disposeCharts();
    if (currentTab === 'overview') buildOverview();
    else if (currentTab === 'weaving') buildWeaving();
    else if (currentTab === 'dyeing') buildDyeing();
    document.getElementById('chartGrid').classList.remove('fading');
  }
  chartInstances.forEach(function(c) { c.resize(); });
}
var chartResizeObserver = new ResizeObserver(resizeCharts);
chartResizeObserver.observe(document.getElementById('chartGrid'));
window.addEventListener('resize', resizeCharts);
})();
