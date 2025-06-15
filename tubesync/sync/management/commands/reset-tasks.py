from django.core.management.base import BaseCommand, CommandError # noqa
from django.db.transaction import atomic
from django.utils.translation import gettext_lazy as _ # noqa
from background_task.models import Task
from common.logger import log
from sync.models import Source
from sync.tasks import index_source_task, check_source_directory_exists


class Command(BaseCommand):

    help = 'Resets all tasks'

    def handle(self, *args, **options):
        log.info('Resettings all tasks...')
        with atomic(durable=True):
            # Delete all tasks
            Task.objects.all().delete()
            # Iter all sources, creating new tasks
            for source in Source.objects.all():
                check_source_directory_exists(str(source.pk))
                # Recreate the initial indexing task
                log.info(f'Resetting tasks for source: {source}')
                verbose_name = _('Index media from source "{}"')
                index_source_task(
                    str(source.pk),
                    repeat=source.index_schedule,
                    schedule=source.task_run_at_dt,
                    verbose_name=verbose_name.format(source.name),
                )
                # This also chains down to call each Media objects .save() as well
                source.save()

        log.info('Done')
