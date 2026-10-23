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

/* SECTION: chart-dashboard-trend */
(function() {
	var el = document.getElementById('dashTrend');
	if (!el) return;
	var c = echarts.init(el);
	chartInstances['dashTrend'] = c;
	c.setOption({
		tooltip: { trigger:'axis', backgroundColor:'rgba(10,22,40,0.95)', borderColor:'rgba(0,212,255,0.2)', textStyle:{color:'#e0e6ed',fontSize:12} },
		legend: { bottom:0, left:'center', textStyle:{color:'#6b7b8d',fontSize:11} },
		grid: { top:'10%', bottom:'18%', left:'10%', right:'6%', containLabel:true },
		xAxis: { type:'category', data:['10/08','10/09','10/10','10/11','10/12','10/13','10/14'], boundaryGap:false, axisLine:{lineStyle:{color:'rgba(255,255,255,0.08)'}}, axisLabel:{color:'#6b7b8d',fontSize:11} },
		yAxis: { type:'value', splitLine:{lineStyle:{color:'rgba(255,255,255,0.04)'}}, axisLabel:{color:'#6b7b8d',fontSize:11,formatter:function(v){return (v/1000).toFixed(0)+'k';}} },
		series: [
			{ name:'实际产量', type:'line', smooth:true, data:[11200,12450,11800,13100,12680,12450,12846],
				lineStyle:{color:'#00d4ff',width:2}, itemStyle:{color:'#00d4ff'},
				areaStyle:{color:{type:'linear',x:0,y:0,x2:0,y2:1,colorStops:[{offset:0,color:'rgba(0,212,255,0.25)'},{offset:1,color:'rgba(0,212,255,0.02)'}]}}, symbol:'circle', symbolSize:6 },
			{ name:'目标产量', type:'line', data:[12000,12000,12000,12000,12000,12000,12000],
				lineStyle:{color:'#ffaa00',width:1.5,type:'dashed'}, itemStyle:{color:'#ffaa00'}, symbol:'none' }
		]
	});
})();

/* SECTION: chart-dashboard-lines */
(function() {
	var el = document.getElementById('dashLines');
	if (!el) return;
	var c = echarts.init(el);
	chartInstances['dashLines'] = c;
	c.setOption({
		tooltip: { trigger:'axis', backgroundColor:'rgba(10,22,40,0.95)', borderColor:'rgba(0,212,255,0.2)', textStyle:{color:'#e0e6ed',fontSize:12} },
		grid: { top:'8%', bottom:'8%', left:'12%', right:'8%', containLabel:true },
		xAxis: { type:'value', splitLine:{lineStyle:{color:'rgba(255,255,255,0.04)'}}, axisLabel:{color:'#6b7b8d',fontSize:11} },
		yAxis: { type:'category', data:['E线','D线','C线','B线','A线'], axisLine:{lineStyle:{color:'rgba(255,255,255,0.08)'}}, axisLabel:{color:'#a0b4c8',fontSize:12} },
		series: [{ type:'bar', barWidth:18,
			data:[
				{value:1616,itemStyle:{color:{type:'linear',x:0,y:0,x2:1,y2:0,colorStops:[{offset:0,color:'rgba(244,114,182,0.2)'},{offset:1,color:'#f472b6'}]},borderRadius:[0,4,4,0]}},
				{value:2180,itemStyle:{color:{type:'linear',x:0,y:0,x2:1,y2:0,colorStops:[{offset:0,color:'rgba(167,139,250,0.2)'},{offset:1,color:'#a78bfa'}]},borderRadius:[0,4,4,0]}},
				{value:2650,itemStyle:{color:{type:'linear',x:0,y:0,x2:1,y2:0,colorStops:[{offset:0,color:'rgba(255,170,0,0.2)'},{offset:1,color:'#ffaa00'}]},borderRadius:[0,4,4,0]}},
				{value:2980,itemStyle:{color:{type:'linear',x:0,y:0,x2:1,y2:0,colorStops:[{offset:0,color:'rgba(0,255,163,0.2)'},{offset:1,color:'#00ffa3'}]},borderRadius:[0,4,4,0]}},
				{value:3420,itemStyle:{color:{type:'linear',x:0,y:0,x2:1,y2:0,colorStops:[{offset:0,color:'rgba(0,212,255,0.2)'},{offset:1,color:'#00d4ff'}]},borderRadius:[0,4,4,0]}}
			],
			label:{show:true,position:'right',color:'#a0b4c8',fontSize:11,formatter:function(p){return Number(p.value).toLocaleString();}}
		}]
	});
})();

/* SECTION: chart-dashboard-equip */
(function() {
	var el = document.getElementById('dashEquip');
	if (!el) return;
	var c = echarts.init(el);
	chartInstances['dashEquip'] = c;
	c.setOption({
		tooltip: { backgroundColor:'rgba(10,22,40,0.95)', borderColor:'rgba(0,212,255,0.2)', textStyle:{color:'#e0e6ed',fontSize:12},
			formatter:function(p){return p.name+': '+p.value+' 台 ('+p.percent.toFixed(1)+'%)';} },
		legend: { bottom:0, left:'center', textStyle:{color:'#6b7b8d',fontSize:11} },
		graphic: [{ type:'text', left:'center', top:'38%',
			style:{text:'54\n设备总数', textAlign:'center', fill:'#a0b4c8', fontSize:15, lineHeight:20} }],
		series: [{ type:'pie', radius:['38%','62%'], center:['50%','44%'], avoidLabelOverlap:true,
			label:{show:false}, labelLine:{show:false},
			data:[
				{value:42,name:'运行中',itemStyle:{color:'#00ffa3'}},
				{value:6,name:'待机中',itemStyle:{color:'#00d4ff'}},
				{value:4,name:'维护保养',itemStyle:{color:'#ffaa00'}},
				{value:2,name:'故障停机',itemStyle:{color:'#ff4d4f'}}
			]
		}]
	});
})();

/* SECTION: chart-dashboard-quality */
(function() {
	var el = document.getElementById('dashQuality');
	if (!el) return;
	var c = echarts.init(el);
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

/* SECTION: resize */
window.addEventListener('resize', function() {
	Object.keys(chartInstances).forEach(function(k) {
		if (chartInstances[k] && chartInstances[k].resize) chartInstances[k].resize();
	});
});
