from django.db import migrations


def seed(apps, schema_editor):
    PlatformSettings = apps.get_model("platform", "PlatformSettings")
    if not PlatformSettings.objects.exists():
        PlatformSettings.objects.create(mode="test")


def unseed(apps, schema_editor):
    apps.get_model("platform", "PlatformSettings").objects.all().delete()


class Migration(migrations.Migration):

    dependencies = [
        ("platform", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(seed, unseed),
    ]
