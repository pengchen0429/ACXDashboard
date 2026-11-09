(function() {
    var root = document.getElementById('productionDetail');
    if (!root) return;
    var site = document.getElementById('productionSite');
    var area = document.getElementById('productionArea');
    var search = document.getElementById('productionSearch');
    var grid = document.getElementById('productionLines');
    var status = document.getElementById('productionStatus');
    var empty = document.getElementById('productionEmpty');
    var template = document.getElementById('productionLineTemplate');
    var snapshot = null;
    var cards = new Map();
    var timer;
    var controller;
    var generation = 0;
    var params = new URLSearchParams(window.location.search);
    if (['ACX', 'CNX'].includes(params.get('site'))) site.value = params.get('site');
    if (Array.from(area.options).some(function(option) { return option.value === params.get('area'); })) area.value = params.get('area');

    function number(value) {
        return Number(value).toLocaleString('zh-CN', { maximumFractionDigits: 3 });
    }

    function render() {
        if (!snapshot) return;
        var query = search.value.trim().toLowerCase();
        var lines = snapshot.lines.filter(function(line) {
            return (!area.value || line.area === area.value) && (!query || line.line.toLowerCase().includes(query));
        });
        var fragment = document.createDocumentFragment();
        lines.forEach(function(line) {
            var key = JSON.stringify([line.line_id, line.line, line.area]);
            var card = cards.get(key);
            if (!card) {
                card = template.content.firstElementChild.cloneNode(true);
                cards.set(key, card);
            }
            card.querySelector('[data-line-name]').textContent = line.line;
            card.querySelector('[data-line-area]').textContent = line.area || '--';
            card.querySelector('[data-line-product]').textContent = line.product || '--';
            card.querySelector('[data-demand-value]').textContent = number(line.demand);
            card.querySelector('[data-actual-value]').textContent = number(line.actual);
            var demand = Number(line.demand);
            var actual = Number(line.actual);
            var scale = Math.max(demand, actual, 1);
            card.querySelector('[data-demand-bar]').style.width = (demand / scale * 100) + '%';
            card.querySelector('[data-actual-bar]').style.width = (actual / scale * 100) + '%';
            card.querySelector('.line-chart').setAttribute('aria-label', 'Demand ' + number(demand) + ' 米，Actual ' + number(actual) + ' 米');
            card.querySelector('[data-line-achievement]').textContent = demand > 0 ? '达成率 ' + number(actual / demand * 100) + '%' : '未设置需求';
            fragment.appendChild(card);
        });
        grid.replaceChildren(fragment);
        empty.hidden = lines.length !== 0;
        document.getElementById('productionCount').textContent = lines.length + ' 条产线';
        document.getElementById('productionPeriod').textContent = snapshot.start_date.slice(0, 10) + ' 08:30 - ' + snapshot.end_date.slice(0, 10) + ' 08:30';
        document.getElementById('productionUpdated').textContent = '更新于 ' + new Date(snapshot.updated_at).toLocaleTimeString('zh-CN', { hour12: false });
        status.textContent = snapshot.stale ? '数据暂未更新，当前显示上次成功数据' : '';
        if (lines.some(function(line) { return !line.product; })) status.textContent += (status.textContent ? ' · ' : '') + '当前产品数据暂不可用';
    }

    function syncUrl() {
        var url = new URL(window.location.href);
        url.searchParams.set('site', site.value);
        if (area.value) url.searchParams.set('area', area.value);
        else url.searchParams.delete('area');
        window.history.replaceState(null, '', url);
    }

    function load() {
        var current = ++generation;
        window.clearTimeout(timer);
        if (controller) controller.abort();
        controller = new AbortController();
        var requestController = controller;
        var timeout = window.setTimeout(function() { requestController.abort(); }, 20000);
        grid.setAttribute('aria-busy', 'true');
        if (!snapshot) status.textContent = '加载中';
        fetch(root.dataset.url + '?site=' + encodeURIComponent(site.value) + '&include_lines=1', { cache: 'no-store', signal: requestController.signal })
            .then(function(response) {
                if (!response.ok) throw new Error('Production request failed');
                return response.json();
            })
            .then(function(data) {
                if (current !== generation) return;
                if (!Array.isArray(data.lines) || data.lines.some(function(line) {
                    return typeof line.line !== 'string' || line.demand == null || line.actual == null ||
                        !Number.isFinite(Number(line.demand)) || !Number.isFinite(Number(line.actual)) || Number(line.demand) < 0 || Number(line.actual) < 0;
                })) throw new Error('Invalid line data');
                snapshot = data;
                render();
            })
            .catch(function() {
                if (current !== generation) return;
                if (snapshot) {
                    snapshot = Object.assign({}, snapshot, { stale: true });
                    render();
                } else {
                    status.textContent = '产量数据暂不可用，请稍后重试';
                    empty.hidden = true;
                }
            })
            .finally(function() {
                window.clearTimeout(timeout);
                if (current !== generation) return;
                grid.setAttribute('aria-busy', 'false');
                timer = window.setTimeout(load, 30000);
            });
    }

    document.getElementById('productionFilters').addEventListener('submit', function(event) { event.preventDefault(); });
    site.addEventListener('change', function() {
        snapshot = null;
        cards.clear();
        grid.replaceChildren();
        empty.hidden = true;
        document.getElementById('productionCount').textContent = '-- 条产线';
        document.getElementById('productionPeriod').textContent = '';
        document.getElementById('productionUpdated').textContent = '';
        syncUrl();
        load();
    });
    area.addEventListener('change', function() { syncUrl(); render(); });
    search.addEventListener('input', render);
    document.getElementById('productionRefresh').addEventListener('click', load);
    load();
})();