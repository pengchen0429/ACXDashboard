from django.conf import settings
from django.db import migrations, models


def move_page_permissions(apps, schema_editor):
    database = schema_editor.connection.alias
    ContentType = apps.get_model('contenttypes', 'ContentType')
    Permission = apps.get_model('auth', 'Permission')
    Group = apps.get_model('auth', 'Group')
    User = apps.get_model(settings.AUTH_USER_MODEL)
    PageAccess = apps.get_model('accounts', 'PageAccess')
    names = dict(PageAccess._meta.permissions)
    target, _ = ContentType.objects.using(database).get_or_create(
        app_label='accounts', model='pageaccess',
    )
    source = ContentType.objects.using(database).filter(
        app_label='dashboard', model='pageaccess',
    ).first()
    if source is not None:
        for permission in Permission.objects.using(database).filter(content_type=source):
            existing = Permission.objects.using(database).filter(
                content_type=target, codename=permission.codename,
            ).first()
            if existing is None:
                permission.content_type = target
                permission.name = names.get(permission.codename, permission.name)
                permission.save(using=database, update_fields=['content_type', 'name'])
            else:
                for group in Group.objects.using(database).filter(permissions=permission):
                    group.permissions.add(existing)
                for user in User.objects.using(database).filter(user_permissions=permission):
                    user.user_permissions.add(existing)
                permission.delete(using=database)
    for codename, name in names.items():
        Permission.objects.using(database).get_or_create(
            content_type=target, codename=codename, defaults={'name': name},
        )


class Migration(migrations.Migration):
    initial = True

    dependencies = [
        ('dashboard', '0001_initial'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='PageAccess',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
            ],
            options={
                'managed': False,
                'default_permissions': (),
                'verbose_name': 'Page access',
                'permissions': (
                    ('view_dashboard', 'Can view dashboard'),
                    ('view_analytics', 'Can view analytics'),
                    ('view_briefing', 'Can view briefing'),
                    ('view_equipment', 'Can view equipment'),
                    ('view_dpmu', 'Can view dpmu'),
                    ('manage_settings', 'Can manage settings'),
                    ('manage_users', 'Can manage users'),
                ),
            },
        ),
        migrations.RunPython(move_page_permissions),
    ]