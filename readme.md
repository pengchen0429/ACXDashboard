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