(function () {
    'use strict';

    if (!window.echarts) return;

    var colors = {
        '#e0e6ed': '#202b38', '#d7e6ff': '#202b38', '#e8f2ff': '#202b38',
        '#e8f0f3': '#202b38', '#c8d6e5': '#435369', '#a0b4c8': '#526174',
        '#9db8e0': '#637184', '#7d9cc9': '#637184', '#7b8fa3': '#637184',
        '#9ec5ff': '#435369', '#9aadb8': '#637184', '#91a7b3': '#637184',
        '#b3c5cd': '#526174', '#c5d5dd': '#435369', '#c9a8ff': '#7754b3',
        '#aabfc9': '#526174',
        '#f7d774': '#a76b13', '#ff9b9b': '#cc4249', '#fac858': '#d29a35',
        '#efbd68': '#d29a35', '#50d9e8': '#377ec6', '#54dfad': '#249c73',
        '#34d97e': '#249c73', '#00ffa3': '#249c73', '#00d4ff': '#377ec6',
        '#99bafa': '#6e85c7', '#ffaa00': '#d29a35', '#f27b83': '#d35e69',
        '#0a1934': '#ffffff', '#141d25': '#ffffff', '#1a2a3a': '#ffffff',
        '#19262f': '#ffffff', '#344e5b': '#dde3ea', '#3a5068': '#cbd4df',
        '#ffffff04': '#f0f3f7',
        'rgba(10,22,40,0.95)': '#ffffff', 'rgba(10,25,52,0.94)': '#ffffff',
        'rgba(0,212,255,0.2)': '#dde3ea', 'rgba(64,140,255,0.4)': '#dde3ea',
        'rgba(255,255,255,0.08)': '#d5dde7', 'rgba(255,255,255,0.04)': '#e8edf3',
        'rgba(147,179,193,0.08)': '#e8edf3', 'rgba(88,140,220,0.15)': '#e8edf3',
        'rgba(88,140,220,0.3)': '#d5dde7', 'rgba(100,180,255,0.06)': '#e8edf3'
    };
    var colorKeys = {color: true, fill: true, stroke: true, borderColor: true, backgroundColor: true};

    function adaptColors(value) {
        if (!value || typeof value !== 'object') return;
        Object.keys(value).forEach(function (key) {
            var current = value[key];
            if (typeof current === 'string' && (colorKeys[key] || Array.isArray(value))) {
                var replacement = colors[current.toLowerCase().replace(/\s/g, '')];
                if (replacement) value[key] = replacement;
            } else if (current && typeof current === 'object') {
                adaptColors(current);
            }
        });
    }

    window.echarts.registerPreprocessor(function (option) {
        adaptColors(option);
        var tooltips = option.tooltip ? (Array.isArray(option.tooltip) ? option.tooltip : [option.tooltip]) : [];
        tooltips.forEach(function (tooltip) {
            tooltip.backgroundColor = '#ffffff';
            tooltip.borderColor = '#dde3ea';
            tooltip.textStyle = Object.assign({}, tooltip.textStyle, {color: '#202b38'});
            tooltip.extraCssText = 'box-shadow:0 4px 16px #202b3814;border-radius:4px;';
        });
    });
}());