from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ('dashboard', '0001_initial'),
        ('accounts', '0001_initial'),
    ]

    operations = [
        migrations.DeleteModel(name='PageAccess'),
    ]