# Snowflake 区域主数据

- 后续新增或调整 Snowflake 数据源的区域标称、筛选和映射时，先核对 `PRD_MANUFACTURING_DB.G_L2L_CONSUMPTION.VW_AREAS`，不要只从业务明细中推断当前在用区域。
- `SERVER_SITE_NAME` 区分工厂：`china^907371` 为 ACX，`china^928261` 为 CNX；`code` 是区域代码。`active` 当前为文本列，`true` 为在用，`false` 为停用。创建人字段为 `createdby`，`created` 实际是创建时间。
- 公共函数 `common.snowflake.get_active_areas(sites=('ACX', 'CNX'))` 返回按工厂分组的区域代码列表；也支持单厂 `get_active_areas('ACX')` 或多厂列表。只返回在用且非空的代码，并排除 `createdby=superuser` 的区域（比较时忽略大小写及首尾空白，空创建人保留）。代码去除首尾空白、去重并排序；无符合条件的区域时返回该工厂的空列表，查询失败抛出异常。
- 同名区域仍属于各自工厂，关联业务数据时必须同时匹配工厂和区域代码，不能仅按 `code` 跨厂关联。展示名称与数据源原始代码分开维护。
- 已统一接入当前所有 Snowflake 页面：Dispatch 的筛选候选项、KPI、图表与逐条 Excel 导出，以及生产早会的安全、改善 KPI 和趋势。业务记录必须在同一工厂存在符合上述条件的区域主数据；未知区域、停用区域和 `superuser` 创建的区域均不计入，不能通过手动传入区域参数绕过。
- Dispatch 区域候选项直接来自区域主数据，即使该区域没有 Dispatch 记录也保留。提交人及类型候选项只取有效区域下的业务记录。生产早会保留原有织、染、整三个生产区域范围，再应用相同主数据校验；其他非 Snowflake 数据源不变。
- 按本次统一要求，历史查询和 Excel 导出也应用当前区域有效性，因此当前停用或系统创建区域的旧记录不再计入；这不修改任何源记录。SQL 使用按工厂及区域代码关联的 `EXISTS`，主数据重复行不会放大数量。公共 `ACTIVE_AREA_CONDITIONS_SQL` 与 `ACTIVE_DISPATCH_AREA_FILTER_SQL` 共用同一规则；后者要求业务表别名为 `dispatch_source`。

```python
from common.snowflake import get_active_areas

areas_by_site = get_active_areas()
acx_area_codes = get_active_areas('ACX')['ACX']
```

# 产线产量详情

- 点击运营总览的“今日产量”卡片进入 `/dashboard/production/`，模板为 `templates/dashboard/production_detail.html`，继承 `base.html`；入口为原生链接，可通过键盘、右键或新标签页访问。
- 顶部支持工厂 ACX/CNX、区域和产线名称搜索。两厂各有 `Weaving Process`、`Dyeing Process`、`Finishing Process` 三个区域，共六个工厂/区域组合；三个同名选项在 `apps/dashboard/views.py` 的 `PRODUCTION_AREAS` 配置。工厂筛选决定所属工厂，即使某区域当天没有数据仍保留选项，不生成假设备。
- 详情页调用只读接口 `/dashboard/today-production/?site=ACX&include_lines=1`。服务端按当前 08:30 生产日筛选，午夜日报标签归属同日 08:30；按原始 line ID 与区域合并多条日报，使用 Decimal 累加 `demand` 和 `actual`，不合并 LOOM042/043 的 A–D 子线。
- 每个 line 一张卡片，Demand 和 Actual 用两条横向柱展示，卡片内共享 `max(demand, actual)` 尺度，单位与总览一致为米；0 是真实零值，Actual 超过 Demand 时不截断。另显示达成率，Demand 为 0 时显示“未设置需求”。
- 当前日报的 `products` 是产品数量，并非产品名称；产线接口的 `defaultproduct` 也不能代表当前生产产品。尚未取得可靠的当前产品查询数据，卡片的“生产产品”显示 `--`，顶部明确提示，不用数量或默认产品冒充实际产品。需要可用的当前产品查询接口才能补齐该字段。
- 工厂切换重新请求并清空原工厂数据，区域筛选和搜索在本地完成。筛选保留在 URL，搜索只保留在当前页面。每轮请求结束 30 秒后后台刷新，20 秒中止等待；失败保留当前工厂的旧卡片并提示，恢复成功后清除过期提示。卡片节点复用，图条平滑更新，并尊重减少动态效果设置。
- `include_lines=1` 与总览缓存独立，认证只在服务端读取。不调用写入接口 `record_pitch_details`，不执行数据库迁移。
- 回归测试：`.\.venv\Scripts\python.exe manage.py test apps.dashboard.tests.TodayProductionTests apps.l2l.tests --noinput`。

# L2L 产量记录写入

`common.l2l_api.record_pitch_details` 调用 `/api/1.0/pitchdetails/record_details/`，这是写入产量记录的接口，不是查询实时产量的接口。默认使用 POST，也可显式传入 `method="GET"`，但 GET 同样会修改 L2L 数据。仅在 Django 服务端调用，认证信息从现有 `L2L_BASE_URL`、`L2L_AUTH`、`L2L_SITE_ACX`、`L2L_SITE_CNX` 配置读取，不要在浏览器脚本中放置密钥。

```python
from common.l2l_api import record_pitch_details

result = record_pitch_details(
	start="2026-11-06 08:30:00",
	end="2026-11-06 09:00:00",
	linecode="LOOM001",
	productcode="SKU001",
	actual="1453.74",
	scrap="2.00",
	operator_count="1.00",
	site="ACX",
	timeout=30,
)
```

- 上述代码会产生真实写入，示例中的产线、产品和数值必须替换为已确认的业务数据。导入模块不会提交记录，只有调用函数时才发送请求。
- `start`、`end` 接受本地时间 `YYYY-MM-DD HH:MM:SS` 或带微秒的 `YYYY-MM-DD HH:MM:SS.ffffff`，结束必须晚于开始。写入使用真实记录时间，不套用日报的午夜日期标签转换。
- `linecode` 与 `line_externalid` 至少提供一个；`productcode` 必填，除非显式使用布尔值 `product_autodetect=True`。
- `actual`、`scrap`、`operator_count` 可传数字或十进制字符串，最多两位小数；省略时不发送该字段，由 L2L 使用文档中的默认值。建议用字符串保留十进制精度。
- 可选参数还有 `unit_of_measure_code`、`comment`、`continue_current_build_sequence`。布尔参数必须传 Python 的 `True` 或 `False`，不要传字符串。默认站点为 ACX，CNX 使用 `site="CNX"`。
- 返回完整 JSON 字典，要求 L2L 响应的 `success` 为 `true`；不将 `data` 限制为列表。本封装不请求 XML 格式。
- 参数错误抛出 `ValueError`；缺少配置、传输失败、非法 JSON 或接口报告失败抛出 `L2LAPIError`，错误信息不会包含认证密钥。
- 不自动重试、不缓存、不查询数据库。发生超时或错误时，不能据此确定服务端未写入；先核对 L2L 记录再决定是否重发，避免重复产量或重复追加评论。
- 定向测试：`.\.venv\Scripts\python.exe manage.py test apps.l2l.tests --noinput`。测试使用模拟 HTTP 响应，不向真实站点写入。

# 运营总览自动刷新与缓存

- 运营总览每 30 秒自动整页刷新，重新加载 ACX、CNX 的今日产量和今日停机；仅在该页面生效。两张卡片共用每站点的一次日产请求和缓存，分别累加当前 08:30 生产日内的 `actual`、`downtime_minutes`，停机单位为分钟；不增加 L2L 调用次数。
- “各产线今日产量”图也复用同一次日产请求，固定显示 ACX-Weaving、ACX-Dyeing、CNX-Weaving、CNX-Dyeing。按精确 `area` 名称 `Weaving Process`、`Dyeing Process` 分组累加所有记录的 `actual`，单位为米；其他区域（包括 CNX 的 `Finishing Process`）不在四组图内，但仍计入上方全站点总产量。区域无记录返回 0，站点请求失败显示不可用，不伪造为 0。
- “近7日生产趋势”以今天为第七天，每天并列显示 ACX、CNX 的全站点产量（米），按 `start_date` 所属的 08:30 生产日汇总 `actual`。前端在原站点请求增加 `include_trend=1`，后端一次查询七天逐日报告，同时计算今日指标及四组区域产量，仍只有两个站点请求并共享缓存；不传此参数时保持单日查询。横轴即使在 08:30 前仍截至日历上的今天（未开始的生产日为 0），上方今日指标仍显示当前正在进行的生产日。查询失败不伪造零值，使用旧缓存时标记“数据暂未更新”。
- 服务端使用 `dashboard` 文件缓存，按站点配置及 08:30 生产日隔离结果，成功及失败结果均缓存 30 秒。非阻塞系统文件锁确保同一台服务器上的多个工作进程不会同时刷新同一站点；首次加载时遇到其他进程正在查询，会返回 503，由下一次页面刷新重试。
- 上游失败或刷新正在进行时，最多使用最近 5 分钟内的成功结果，并显示“数据暂未更新”；超时无旧值则显示“暂不可用”，不把失败显示为零。悬停站点数据可查看上次成功更新时间。
- 缓存及锁文件默认位于 `.cache/dashboard`、`.cache/dashboard-locks`，服务账号需有目录读写权限；文件缓存目录不可通过 Web 对外开放，也不可允许不可信用户写入。重启服务不清空缓存，不访问业务数据库，不增加 Redis 等服务依赖。
- 此方案面向同机多进程，不提供多服务器之间的缓存及锁协调。部署到多台服务器时，需要同时改用共享缓存和分布式锁，不能只替换缓存后端。若本地配置覆盖 `CACHES`，需保留 `dashboard` 别名及文件缓存配置。

# 早会安全统计

- `/briefing/` 安全 KPI 和安全新增数量柱状图使用 `snowflake` 连接，只读查询 `PRD_MANUFACTURING_DB.G_L2L_CONSUMPTION.VW_DISPATCHES`，不需要模型或迁移。其余 KPI 和另外五张图表仍为示例数据。
- 下方安全图表按配置区域显示分组趋势柱状图，每个时间点并排显示织、染、整三根柱子，固定使用绿色、蓝色、黄色，并提供区域图例；接口同时保留合计趋势。横轴为时间，不显示起止时间文本、整改率折线或百分比轴。按上海日历分组，90 个自然日以内按天、91 至 1096 天按月、更长范围按年汇总，各区域缺失周期分别补 0；首尾周期只计入筛选范围内的数据。图表加载中或失败保留 `--`，成功返回 0 时显示真实零值。
- 顶部时间筛选和“恢复默认”同时控制上方安全 KPI 及下方六张图表。安全 KPI 和安全趋势通过同一次 `/briefing/safety-data/?include_trend=1&start_time=...&end_time=...` 请求更新，后端执行指标聚合与时间趋势两条只读查询；不重新创建图表。趋势失败不会把已成功的 KPI 数据清空。其余五张图表仍为示例：FPY、交付按所选月份与现有示例月份取交集；帕累托、成本、雷达仅有最新示例月份的快照，所选范围不含该月份时清空并显示 `--`，不伪造按日或按分钟的统计。
- 安全卡片顶部为所有配置区域的新增总数，下方按配置顺序逐行显示各区域的新增、完成和未关闭数量；查询按区域分组，无匹配记录的区域补 0。`SAFETY_AREA_LABELS` 可维护显示简称，当前分别为 Weaving、Dyeing、Finishing；新增区域未配置简称时显示原始区域名。
- 页面先渲染，不等待 Snowflake；卡片通过 `GET /briefing/safety-data/` 单独加载。每次请求都查询 Snowflake，不复用原有 60 秒结果缓存，避免“当前未关闭”使用旧快照；失败返回 503。未关闭的截止时刻为本次请求开始时的上海时间，接口通过 `unclosed_as_of` 返回；页面打开、点击“查询”或“恢复默认”时更新，不持续自动刷新。数据源本身的同步延迟仍可能影响实时性。
- 前端等待 35 秒后结束等待；加载中、失败或超时时保留 `--` 占位，不显示状态提示和重试按钮，刷新页面可重新加载。只影响安全卡片，不阻塞页面和图表。连接配置限制登录重试 10 秒、网络重试 15 秒、Socket 等待 10 秒、查询执行 20 秒及排队 10 秒。这些为分阶段限制，并非整个请求的硬性总超时；浏览器终止等待不等于立即取消数据库执行。
- 站点在 `apps/briefing/views.py` 顶部的 `SAFETY_SERVER_SITE_NAMES` 维护，按 `SERVER_SITE_NAME` 筛选，当前为 `china^907371`。区域在相邻的 `SAFETY_AREA_CODES` 维护，当前包含 `Weaving Process`、`Dyeing Process`、`ACX Finishing`；类型在 `SAFETY_DISPATCH_TYPE_CODES` 维护，当前包含 `Safety Jidoka - Unsafe Behaviors`、`Safety Jidoka - Unsafe Conditions`。每行填写一个带引号、逗号结尾的列原始值，即可增加、修改或删除筛选值。记录需同时满足站点、区域和类型列表，各列表内采用“任一匹配”，合并统计总数；任一列表为空时不查询，返回 0。修改后重启服务生效。
- 新增：`reported` 位于所选时间范围内。完成：同一条记录的 `reported` 和 `completed` 都位于该范围内，因此之前开启、本期完成的记录不计入本期完成。未关闭：不受所选时间范围限制，统计全部历史中 `reported` 不晚于本次请求截止时刻，且 `closed` 为空、空白，或关闭时间晚于该截止时刻的记录；已经完成但尚未关闭仍计入。不能用“新增减完成”得到未关闭数。三个指标均按视图行数计数，不按工单 ID 去重。
- 每次打开或刷新页面，时间输入框按上海日历日期默认选择昨天 `08:31` 至今天 `08:30`，不保存上次选择。可修改开始、结束时间后点击“查询”，或点击“恢复默认”恢复本次打开时的默认范围并查询；同步更新安全 KPI 和下方六图，其他示例 KPI 暂无真实时间数据。早于今天 08:31 打开时仍使用该默认窗口，数据可能尚未齐全。
- 接口可传 `start_time`、`end_time`，格式均为 `YYYY-MM-DDTHH:MM`（上海本地时间），例如 `GET /briefing/safety-data/?start_time=2026-10-01T08:31&end_time=2026-10-02T08:30`。两项不传时使用默认窗口；自选时必须同时提供，开始不能晚于结束，否则返回 400，不访问 Snowflake。结束时间包含整分钟，SQL 上界为结束时间加一分钟且不包含该上界；同一分钟的起止时间表示统计该完整分钟。连续查询会终止前端上一请求的等待，防止旧结果覆盖新选择。
- 已核实这些时间列为文本，示例为 `2025-08-07T09:00:55.563`，没有时区标记。默认按上海本地时间解释，需由数据源负责人确认；若实际存储 UTC，可设置环境变量 `SNOWFLAKE_DISPATCH_TIME_ZONE=UTC`，系统转换为上海时间后统计。无法解析或为空的开启、完成时间不计入对应指标；非空但无法解析的关闭时间不会被当作“未关闭”，避免把异常值误算为待关闭。
- `SNOWFLAKE_WAREHOUSE` 默认 `PRD_MANUFACTURING_L2L_WH`，可通过环境变量覆盖。原 `PRD_MANUFACTURING_DB` 是数据库名，不能作为该账号的有效计算仓库。
- 查询失败保留 `--`，不显示为 0；查询成功但无匹配记录显示 0。定向测试：`.\.venv\Scripts\python.exe manage.py test apps.briefing.tests --noinput`。

# 页面访问权限

权限管理集中在 `apps/accounts`，继续使用 Django 原生 Group / Permission。用户通过所属 Group 获取权限；视图和导航使用相同的权限标识，不按组名写死访问判断。

| 页面 | 权限标识 | 初始授权组 |
| --- | --- | --- |
| 设备管理 `/equipment/` | `accounts.view_equipment` | `manager`、`admin` |
| DPMU `/dpmu/` | `accounts.view_dpmu` | `manager`、`admin` |

- 整理后执行 `python manage.py migrate`：`accounts.0001_initial` 将旧 `dashboard` 页面权限迁至 `accounts`，保留已有组授权和用户单独授权；无重复时保留权限 ID，同名重复时合并授权。`dashboard.0002_remove_pageaccess` 只移除旧模型状态，不删除业务表。已执行的历史迁移不能修改或删除。
- 迁移不会重置已有组权限，也不会重新授予曾在后台撤销的权限。由于同名权限可能合并，该数据迁移不提供自动反向操作；需要降级时先规划备份和恢复方案。
- `apps/accounts/models.py` 的 `PageAccess.Meta.permissions` 是统一权限目录。`managed=False` 表示只承载权限定义，不创建数据表，也不要在 admin 中注册该模型供增删改查。
- `apps/accounts/decorators.py` 提供统一的 `page_permission_required`：自动加 `accounts.` 前缀，统一检查权限。匿名用户按 `visitor` 组的页面权限判断，有权直接访问，无权跳转登录；已登录用户无权返回 403。`apps/accounts/views.py` 和 `urls.py` 管理登录与 POST 退出，保留 `/login/`、`/logout/` 地址和路由名不变。
- 目录中的 `view_dashboard`、`view_analytics`、`view_briefing`、`manage_settings`、`manage_users` 当前仅声明，未自动限制对应页面或授予普通组。这次整理只保持设备管理和 DPMU 的现有控制范围；`manage_users` 不等同于 Django admin 的用户增删改查权限。
- 在 Django 后台进入“认证和授权 → 组 → 目标组 → 权限”，筛选 `accounts` 或 `Page access`，添加或移除 `Can view equipment`、`Can view dpmu` 后保存。新增目录项未授权时默认不能访问已接入检查的页面。
- 初始 `visitor`、`user` 没有设备管理和 DPMU 权限。未登录用户默认使用 `visitor` 组的 `accounts.PageAccess` 权限，导航的 `perms.accounts.*` 与后端判断一致。后台授予 `visitor` 某页面权限即代表向未登录公众开放该页面及受同一权限保护的接口，撤销后从下一次请求起生效；其余页面仍保持原规则。
- `apps/accounts/backends.py` 的 `VisitorPermissionBackend` 只补充匿名用户的业务页面权限，不创建或登录访客账号，不赋予 `is_staff`、超级管理员或 Django admin 模型权限。保留原 `ModelBackend` 作为第一个后端，因此原有登录会话和认证方式不变。已登录用户不会额外继承 `visitor` 权限，除非账号本身属于该组；缺少 `visitor` 组时默认无访客权限，访问过程不自动建组。
- 多组权限及用户直接权限取并集，不存在“拒绝组”覆盖允许组的规则。需要严格按组管理时，不要向用户单独授予页面权限。
- 已启用的超级管理员默认拥有全部权限。名为 `admin` 的 Group 不等同于超级管理员，也不会自动授予 `is_staff` 后台资格；仅有 `is_staff` 也不代表具有业务页面权限。
- 登录保留 Django 的安全 `next` 跳转。默认跳转为管理后台时，非 `is_staff` 用户改为运营首页，后台人员仍使用 `LOGIN_REDIRECT_URL` 配置。
- `SESSION_EXPIRE_AT_BROWSER_CLOSE=True` 使用浏览器会话 Cookie：使用期间保持登录，关闭整个浏览器并丢弃会话 Cookie 后，再次打开按匿名 `visitor` 权限访问。关闭单个标签页不会退出；部分浏览器“恢复上次会话”功能可能保留会话 Cookie。已有持久 Cookie 不会被设置自动删除，首次切换需要先退出再重新登录，或者清除本站 Cookie；服务器重启不会自动清除浏览器登录状态。
- 顶部未登录时显示登录入口，登录后显示账号名和退出按钮；长账号名省略显示，悬停可查看完整名称。退出必须通过带 CSRF 的 POST 请求，清除会话后默认返回运营首页。Django 3.2 的退出视图在 `dispatch` 中处理退出，因此 `accounts/urls.py` 外层使用 `require_POST` 拒绝 GET，不能仅设置 `http_method_names`。
- 设备管理与 DPMU 当前没有独立 HTTP 数据接口；未来新增 API、导出接口时，必须应用相应页面权限或单独定义操作权限，不能仅隐藏按钮。

## 后续新增 app 和受控页面

1. 创建业务 app（例如 `apps/energy`），确保其 `AppConfig.name = 'apps.energy'`，加入 `INSTALLED_APPS` 并配置业务 URL。业务 app 自身只负责业务功能，无需重复定义 `PageAccess`。
2. 在 `apps/accounts/models.py` 的 `PageAccess.Meta.permissions` 增加 `('view_energy', 'Can view energy')`。统一权限标识仍为 `accounts.view_energy`，不是 `energy.view_energy`；每个 codename 在该目录内必须唯一。
3. 运行 `python manage.py makemigrations accounts`。若新 app 有自己的业务模型，也运行 `python manage.py makemigrations energy`；最后运行 `python manage.py migrate`。新权限会在迁移后自动出现在后台的组权限列表中。
4. 使用下面的统一装饰器保护页面、数据接口和导出接口；未登录时按 `visitor` 组判断，有权直接访问，无权跳转 `/login/?next=...`；已登录无权限返回 403。

```python
from django.shortcuts import render
from apps.accounts.decorators import page_permission_required

@page_permission_required('view_energy')
def energy(request):
	return render(request, 'energy/energy.html')
```

对于类视图，可以在 URL 中使用 `page_permission_required('view_energy')(EnergyView.as_view())`。

5. 在导航中使用对应权限条件：

```django
{% if perms.accounts.view_energy %}
<a class="nav-item" href="{% url 'energy' %}">能耗管理</a>
{% endif %}
```

6. 在后台给目标 Group 分配 `accounts | Page access | Can view energy` 并保存。新权限默认不授予任何普通组，也不会自动给 `manager`、`admin`；权限变更不需要修改装饰器或组名判断。
7. 增加有权、无权、匿名、直接 URL 和接口测试。现有访问矩阵与登录退出回归测试保留在 `apps/dashboard/tests.py`，跨应用授权迁移测试位于 `apps/accounts/tests.py`。给旧页面新增访问限制时，先分配权限再启用检查，避免用户被意外锁在页面之外。

默认数据库是 SQL Server，本地账号可能没有创建测试数据库的权限。仅验证认证、模板及权限时，可使用临时 SQLite 内存数据库，不修改业务数据库：

```powershell
@'
import os
import sys
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
from django.conf import settings
settings.DATABASES = {'default': {'ENGINE': 'django.db.backends.sqlite3', 'NAME': ':memory:'}}
import django
django.setup()
from django.test.runner import DiscoverRunner
failures = DiscoverRunner(verbosity=1, interactive=False).run_tests([
	'apps.accounts.tests', 'apps.dashboard.tests', 'apps.equipment.tests.EquipmentPageTests',
])
sys.exit(bool(failures))
'@ | .\.venv\Scripts\python.exe -
```

该测试不验证 SQL Server 特有行为，也不会创建或修改真实用户。

# 质检数据接口

`GET /analytics/data/?start_date=2026-10-04&end_date=2026-10-15&page=1&page_size=100`

- 数据库连接：Django `DATABASES['mesaq']`，只执行 SELECT，不需要新增模型或迁移。
- 时间选择器对应 `tabDefaultRec.BegDate`。参数支持 `YYYY-MM-DDTHH:mm`（本地时间，无时区），包含起始时间和结束时间整分钟，例如结束 `14:30` 的查询上界为 `< 14:31`。兼容 `YYYY-MM-DD`，日期参数包含当天；不传日期时默认最近 30 天。
- 分钟筛选示例：`GET /analytics/data/?start_date=2026-10-15T08:00&end_date=2026-10-15T17:30`。
- 分页：`page` 默认 1，`page_size` 默认 100，最大 1000；按 `BegDate`、`ID` 倒序。
- 返回：`records`、`total`、`page`、`page_size`、`pages`、`start_date`、`end_date`。
- 保留原 SQL 的全部字段；日期文本列命名为 `RecordDate`，`BegDate` 为原始日期时间。
- 字段映射：`CodeType` 条码类型，`cDefine4` 车次号，`TmpCode` 产品条码，`ProductNO` 产品编号，`ProductName` 产品名称，`equipName` 设备名称，`OrgName` 班组，`MyCode` 疵点名称，`SumNum` 批次产量，`intVal1` 报废数量，`Remark` 疵点分类，`cDefine10` 报废分类（来自 `tabDefaultRec.cDefine10`）。
- Decimal 数值在 JSON 中以字符串返回以保留精度，空值返回 `null`。
- 非法参数返回 HTTP 400；数据库读取失败返回 HTTP 503；非 GET 请求返回 HTTP 405。
- 当前明细接口返回分页数据；质检页面全部十张图已接入真实聚合数据，统一按所选时间查询。

## 每日质检与报废趋势

`GET /analytics/daily-trend/?start_date=2026-10-04T00:00&end_date=2026-10-15T23:59`

- 沿用明细查询的关联表及 `BegDate` 时间范围，按日期聚合全部匹配记录，不受分页限制。
- `days` 每项包含 `date`（日期）、`records`（记录数）、`scrap`（`intVal1` 报废数量之和）；无记录日期补零，空报废数量按零处理。Decimal 仍以字符串返回。
- 起止参数格式与明细接口一致，包含结束整分钟；最长支持 3660 天。
- 该接口仍保留供单独读取每日趋势；页面改用下方统一统计接口，同时刷新全部图表。
- 无记录显示空数据提示，查询失败清除旧图并允许重试；非法参数返回 400，数据库不可用返回 503，非 GET 返回 405。

## 全部图表统计

`GET /analytics/statistics/?start_date=2026-10-15T08:00&end_date=2026-10-15T09:30`

- 复用明细关联表和 `BegDate` 范围，一次只读聚合查询生成全部统计，不受明细分页限制；时间格式、结束分钟包含规则和 3660 天限制与每日趋势相同。
- 返回 `total`、`days`、`category_trend` 和八个分布数组；分布项为 `name`、`value`，`value` 均为质检记录数，并非报废米数。
- `categories`、`category_trend`：`tabGramCode.Remark` 疵点分类；每日分类数据补零。
- `defects`：`tabGramCode.MyCode` 疵点名称 TOP 10；`teams`：`OrgName` 班组分布。
- `devices`：`equipName` 设备 TOP 10；`inspectors`：大写 `ChkManNo` 检验员 TOP 10。
- `barcodes`：`CodeType` 条码类型；`scrap_categories`：`tabDefaultRec.cDefine10` 报废分类，独立于疵点分类。
- `products`：`ProductNO` 产品编号 TOP 10。TOP 10 按记录数降序、同数按名称排序；其余分布保留全部类别。空值或空白名称归为 `Unspecified`。
- 页面加载、时间修改及“查询”按钮统一刷新十张图；新请求取消旧请求，成功查询的时间保留在地址中。空范围和查询失败均在各图显示状态，避免旧图误导。

验证命令：`python manage.py test apps.analytics.tests --verbosity 2`。测试使用模拟连接，不会创建或修改业务数据库。

## PLC 设备采集

使用项目虚拟环境安装依赖后，执行一次采集：

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe manage.py collect_machine_data --machine-id 1
```

- 从默认数据库读取启用的 `machine` 及关联的 `machine_tag`，通过 OMRON FINS/UDP（9600 端口）只读访问 PLC；不向 PLC 写值。
- 支持 D 区单字 `INT`（有符号）、`UINT/WORD`（无符号）、`BCD`（四位压缩十进制），解码后乘以 `scale`。其他地址或类型明确报错，不猜测解释方式。
- `PLAN_QTY`、`PROD_QTY`（兼容 `PRODUCTION_QTY`）、`OK_QTY`、`NG_QTY`、`CYCLE_TIME` 分别对应 `machine_data` 的计划、产量、良品、不良品、节拍字段。
- 每台设备全部已配置点位读取成功后，事务插入一条完整配置快照；未配置字段保持数据库默认值，`collect_time` 由数据库生成。超时或任一点读取失败时，不插入该设备的部分数据。多台设备分别提交，已成功提交的设备不会因后续设备失败而回滚。
- 加 `--dry-run` 只读预览，不写数据库；省略 `--machine-id` 采集全部启用且配置了点位的设备。
- 默认 FINS 源节点取本机出站网卡 IP 最后一段，目标节点取 PLC IP 最后一段；现场配置不同时，通过 `--source-node` 和 `--destination-node` 指定。
- 不加 `--watch` 时执行一轮；加 `--watch` 后按每台设备的 `machine.polling_interval`（秒，必须大于零）持续采集并追加快照，首次立即采集。周期从上次采集完成后开始计算，失败也等待相同周期再重试，不补写失败期间的数据。
- 轮询每秒重新读取设备启用状态和周期配置，无需重启命令；同一进程顺序采集各设备，通信耗时可能使实际写入间隔延长。不要为同一设备同时启动多个轮询进程，以免重复入库。

持续采集所有已启用设备（`Ctrl+C` 停止）：

```powershell
.\.venv\Scripts\python.exe manage.py collect_machine_data --watch
```

只持续采集设备 1，可追加 `--machine-id 1`；只测试通信而不入库，可追加 `--dry-run`。命令不会随 Django Web 服务自动启动。

验证命令：`.\.venv\Scripts\python.exe manage.py test apps.equipment.tests --verbosity 2`。测试模拟 PLC 和数据库，不会写入业务数据。

mt数据库账号密码
用户名：admin
密码：ACXDashboard@TaiCang2026!