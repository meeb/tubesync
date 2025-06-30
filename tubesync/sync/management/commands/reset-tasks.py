from django.core.management.base import BaseCommand, CommandError # noqa
from django.db.transaction import atomic
from django.utils.translation import gettext_lazy as _ # noqa
from background_task.models import Task
from django_huey import DJANGO_HUEY
from common.huey import h_q_reset_tasks
from common.logger import log
from sync.models import Source
from sync.tasks import check_source_directory_exists


class Command(BaseCommand):

    help = 'Resets all tasks'

    def handle(self, *args, **options):
        log.info('Resettings all tasks...')
        for queue_name in (DJANGO_HUEY or {}).get('queues', {}):
            h_q_reset_tasks(queue_name)
        with atomic(durable=True):
            # Delete all tasks
            Task.objects.all().delete()
            # Iter all sources, creating new tasks
            for source in Source.objects.all():
                log.info(f'Resetting tasks for source: {source}')
                check_source_directory_exists(str(source.pk))
                # This also chains down to call each Media objects .save() as well
                source.save()

        log.info('Done')
