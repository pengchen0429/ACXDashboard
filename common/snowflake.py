import sqlparse

from django.db import connections


SNOWFLAKE_SITE_NAMES = {
	'ACX': 'china^907371',
	'CNX': 'china^928261',
}


ACTIVE_AREA_CONDITIONS_SQL = '''LOWER(TRIM("active")) = 'true'
	AND COALESCE(LOWER(TRIM("createdby")), '') <> 'superuser'
	AND NULLIF(TRIM("code"), '') IS NOT NULL'''

ACTIVE_DISPATCH_AREA_FILTER_SQL = f'''EXISTS (
	SELECT 1 FROM PRD_MANUFACTURING_DB.G_L2L_CONSUMPTION.VW_AREAS
	WHERE "SERVER_SITE_NAME" = dispatch_source."SERVER_SITE_NAME"
		AND TRIM("code") = TRIM(dispatch_source."areacode")
		AND {ACTIVE_AREA_CONDITIONS_SQL}
)'''


def _validate_select(sql):
	"""校验查询为单条 SELECT，允许 WITH 查询；实际只读权限由数据库角色保证。"""
	if not isinstance(sql, str) or not sql.strip():
		raise ValueError('sql must be a non-empty SELECT statement')
	statements = sqlparse.parse(sql)
	if len(statements) != 1:
		raise ValueError('Only one SELECT statement is allowed')
	statement = statements[0]
	operation = statement.get_type()
	if operation == 'UNKNOWN' and statement.token_first(skip_cm=True).normalized == 'WITH':
		operation = next((token.normalized for token in statement.tokens
			if token.ttype in sqlparse.tokens.DML), 'UNKNOWN')
	if operation != 'SELECT':
		raise ValueError('Only one SELECT statement is allowed')


def fetch_all(sql, params=None):
	"""从 Snowflake 读取全部查询结果，返回字典列表，无记录时返回空列表。

	使用 Django 配置中的 snowflake 连接，不需要传入账号或密钥。
	SQL 仅允许单条 SELECT（包括 WITH），筛选值必须通过 %s 占位符和
	params 列表或元组传入，不应拼接进 SQL。字典键保留查询列名的大小写，
	日期和数值保留驱动返回的类型。查询异常直接向调用方抛出，不伪装为空数据。
	大量数据优先在 SQL 中使用 COUNT、GROUP BY 聚合，避免读取全部明细。
	"""
	_validate_select(sql)
	with connections['snowflake'].cursor() as cursor:
		cursor.execute(sql, params)
		columns = [column[0] for column in cursor.description]
		return [dict(zip(columns, row)) for row in cursor.fetchall()]


def fetch_one(sql, params=None):
	"""从 Snowflake 读取第一条结果并返回字典，无记录时返回 None。

	连接、参数绑定和异常处理与 fetch_all 相同，适合 COUNT 等单行统计。
	本函数不会自动在 SQL 中添加 LIMIT；读取明细时应自行设置查询范围。
	"""
	_validate_select(sql)
	with connections['snowflake'].cursor() as cursor:
		cursor.execute(sql, params)
		row = cursor.fetchone()
		if row is None:
			return None
		columns = [column[0] for column in cursor.description]
		return dict(zip(columns, row))


def get_active_areas(sites=('ACX', 'CNX')):
	"""返回各工厂在用区域代码，如 {'ACX': ['Weaving Process'], 'CNX': []}。

	sites 接受工厂名称或名称列表，默认读取两厂。区域以 VW_AREAS.code 为准，
	只包含 active=true 且 createdby 非 superuser 的非空代码；创建人比较
	忽略大小写和首尾空白，空创建人保留。区域代码去除首尾空白、去重并排序。
	后续 Snowflake 区域筛选、标称和映射应先核对此主数据。当前 Dispatch、早会
	及其历史查询和导出均按本规则过滤，不修改源记录。查询失败直接抛出异常。
	"""
	if isinstance(sites, str):
		sites = (sites,)
	if not isinstance(sites, (list, tuple)) or not sites or any(
		not isinstance(site, str) or site not in SNOWFLAKE_SITE_NAMES for site in sites):
		raise ValueError('sites must contain ACX or CNX')
	sites = tuple(dict.fromkeys(sites))
	server_sites = {SNOWFLAKE_SITE_NAMES[site]: site for site in sites}
	placeholders = ', '.join(['%s'] * len(server_sites))
	rows = fetch_all(f'''
SELECT DISTINCT "SERVER_SITE_NAME" AS "server_site_name", TRIM("code") AS "area"
FROM PRD_MANUFACTURING_DB.G_L2L_CONSUMPTION.VW_AREAS
WHERE "SERVER_SITE_NAME" IN ({placeholders})
	AND {ACTIVE_AREA_CONDITIONS_SQL}
ORDER BY "server_site_name", "area"
''', list(server_sites))
	areas = {site: [] for site in sites}
	for row in rows:
		areas[server_sites[row['server_site_name']]].append(row['area'])
	return areas