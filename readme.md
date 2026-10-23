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