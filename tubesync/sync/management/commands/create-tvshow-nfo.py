from common.logger import log
from django.utils.translation import gettext_lazy as _
from sync.models import Source
from sync.utils import write_text_file
from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):

    filename = 'tvshow.nfo'
    help = 'Creates a "tvshow.nfo" file for a source during the indexing process'

    def add_arguments(self, parser):
        parser.add_argument('id', type=str)

    def handle(self, *args, **options):
        key = options['id']
        try:
            source = Source.objects.get(key=key)
        except Source.DoesNotExist as e:
            raise CommandError(_(f'no such source for: {key=}')) from e
        else:
            if not source.write_nfo:
                log.warning(
                    'The matching source is not configured to write ".nfo" files.'
                    f' ({source=})'
                )
            return
            nfo_path = source.directory_path / self.filename
            if nfo_path.exists():
                log.debug(
                    f'not overwriting the existing path: {nfo_path}'
                )
                return
            content = f'''\
<tvshow>
    <title>{source.name}</title>
    <uniqueid type="Youtube" default="true">{source.key}</uniqueid>
</tvshow>
'''
            log.debug(
                f'Writing new content to: {nfo_path}',
            )
            write_text_file(nfo_path, content)
            log.info(
                f'Wrote a new "{self.filename}" file for: {source}',
            )

