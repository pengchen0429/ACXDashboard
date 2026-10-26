from django.db import migrations, models


def assign_page_permissions(apps, schema_editor):
	database = schema_editor.connection.alias
	ContentType = apps.get_model('contenttypes', 'ContentType')
	Permission = apps.get_model('auth', 'Permission')
	Group = apps.get_model('auth', 'Group')
	content_type, _ = ContentType.objects.using(database).get_or_create(
		app_label='dashboard', model='pageaccess'
	)
	permissions = []
	for codename, name in (
		('view_equipment', 'Can view equipment page'),
		('view_dpmu', 'Can view DPMU page'),
	):
		permission, _ = Permission.objects.using(database).get_or_create(
			content_type=content_type, codename=codename,
			defaults={'name': name},
		)
		permissions.append(permission)
	for name in ('manager', 'admin'):
		group, _ = Group.objects.using(database).get_or_create(name=name)
		group.permissions.add(*permissions)


class Migration(migrations.Migration):
	initial = True

	dependencies = [
		('auth', '0012_alter_user_first_name_max_length'),
		('contenttypes', '0002_remove_content_type_name'),
	]

	operations = [
		migrations.CreateModel(
			name='PageAccess',
			fields=[
				('id', models.BigAutoField(primary_key=True, serialize=False)),
			],
			options={
				'managed': False,
				'default_permissions': (),
				'permissions': (
					('view_equipment', 'Can view equipment page'),
					('view_dpmu', 'Can view DPMU page'),
				),
				'verbose_name': 'Page access',
			},
		),
		migrations.RunPython(assign_page_permissions, migrations.RunPython.noop),
	]