from django.core.management.base import BaseCommand, CommandError
from background_task.models import Task
from sync.models import Source


from common.logger import log


class Command(BaseCommand):

    help = 'Resets all tasks'

    def handle(self, *args, **options):
        log.info('Resettings all tasks...')
        # Delete all tasks
        Task.objects.all().delete()
        # Iter all tasks
        for source in Source.objects.all():
            # Recreate the initial indexing task
            verbose_name = _('Index media from source "{}"')
            index_source_task(
                str(source.pk),
                repeat=source.index_schedule,
                queue=str(source.pk),
                priority=5,
                verbose_name=verbose_name.format(source.name)
            )
            # This also chains down to call each Media objects .save() as well
            source.save()
        log.info('Done')
