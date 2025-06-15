from django.core.management.base import BaseCommand, CommandError # noqa
from django.db.transaction import atomic
from django.utils.translation import gettext_lazy as _
from background_task.models import Task
from common.logger import log
from sync.models import Source
from sync.tasks import check_source_directory_exists


class Command(BaseCommand):

    help = 'Resets all tasks'

    def handle(self, *args, **options):
        log.info('Resettings all tasks...')
        with atomic(durable=True):
            # Delete all tasks
            Task.objects.all().delete()
            # Iter all sources, creating new tasks
            for source in Source.objects.all():
                verbose_name = _('Check download directory exists for source "{}"')
                check_source_directory_exists(
                    str(source.pk),
                    verbose_name=verbose_name.format(source.name),
                )
                # This also chains down to call each Media objects .save() as well
                source.save()

        log.info('Done')
