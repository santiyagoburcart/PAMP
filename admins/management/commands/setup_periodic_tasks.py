from django.core.management.base import BaseCommand
from django.conf import settings
from django_celery_beat.models import PeriodicTask, IntervalSchedule
import json


class Command(BaseCommand):
    help = 'Set up Celery Beat periodic tasks for panel sync'

    def handle(self, *args, **kwargs):
        interval_minutes = settings.PANEL_SYNC_INTERVAL_MINUTES

        schedule, _ = IntervalSchedule.objects.get_or_create(
            every=interval_minutes,
            period=IntervalSchedule.MINUTES,
        )

        task, created = PeriodicTask.objects.update_or_create(
            name='Sync Panel Admins',
            defaults={
                'task': 'admins.tasks.sync_panel_admins',
                'interval': schedule,
                'args': json.dumps([]),
                'enabled': True,
            },
        )

        action = 'Created' if created else 'Updated'
        self.stdout.write(
            self.style.SUCCESS(
                f"{action} periodic task: sync every {interval_minutes} minutes."
            )
        )
