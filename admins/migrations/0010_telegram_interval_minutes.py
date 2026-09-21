from django.db import migrations, models


def hours_to_minutes(apps, schema_editor):
    TelegramConfig = apps.get_model('admins', 'TelegramConfig')
    for cfg in TelegramConfig.objects.all():
        cfg.backup_interval_minutes = max(5, cfg.backup_interval_hours * 60)
        cfg.save(update_fields=['backup_interval_minutes'])


def minutes_to_hours(apps, schema_editor):
    TelegramConfig = apps.get_model('admins', 'TelegramConfig')
    for cfg in TelegramConfig.objects.all():
        cfg.backup_interval_hours = max(1, cfg.backup_interval_minutes // 60)
        cfg.save(update_fields=['backup_interval_hours'])


class Migration(migrations.Migration):

    dependencies = [
        ('admins', '0009_admingroup'),
    ]

    operations = [
        migrations.AddField(
            model_name='telegramconfig',
            name='backup_interval_minutes',
            field=models.PositiveIntegerField(default=60),
        ),
        migrations.RunPython(hours_to_minutes, minutes_to_hours),
        migrations.RemoveField(
            model_name='telegramconfig',
            name='backup_interval_hours',
        ),
    ]
