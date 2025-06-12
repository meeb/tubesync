import base64
import binascii
import os
from common.logger import log
from django.utils.translation import gettext_lazy as _
from sync.models import Source
from sync.utils import write_text_file
from django.core.management.base import BaseCommand, CommandError


def validYoutubeID(arg, /):
    arg_str = str(arg).strip()
    valid_beginning = ( arg_str[0:2] in frozenset(('PL','UC','UU',)) )
    # channels end in one of these: A, Q, g, w,
    # playlists are, of course, different.
    valid_ending = (
        ( arg_str[0:2] in frozenset(('PL',)) ) or
        ( arg_str[-1] in frozenset('AQgw') )
    )
    valid_length = len(arg_str) in {18, 24, 26, 34}
    if not ( valid_beginning and valid_ending and valid_length ):
        raise ValueError('not a channel or playlist ID')
    try:
        value = arg_str[2:] + '=='
        if 26 == len(arg_str) and 'UULV' == arg_str[0:4]:
            value = value[2:]
        base64.b64decode(value, altchars='-_', validate=True)
    except binascii.Error as e:
        raise ValueError('not a channel or playlist ID') from e
    return arg_str

_filename = 'tvshow.nfo'
class Command(BaseCommand):

    filename = _filename
    help = f'Creates a "{_filename}" file for a source during the indexing process'

    def add_arguments(self, parser):
        parser.add_argument('id')
        parser.add_argument('channel_id', nargs='?')
        parser.add_argument('--name', default=list(), nargs='*')

    def handle(self, *args, **options):
        channel_id = options['channel_id']
        channel_name = ' '.join(options['name']).strip()
        key = options['id']
        try:
            key = validYoutubeID(key)
        except ValueError as e:
            raise CommandError(_(f'not a valid YouTube ID: {key=}')) from e
        try:
            if channel_id is not None:
                channel_id = validYoutubeID(channel_id)
        except ValueError as e:
            log.exception(f'{e}')
            log.info('Continuing without a channel_id')
            channel_id = None
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
    <studio>{channel_name}</studio>
    <tag>Youtube</tag>
    <tag>{channel_id or ''}</tag>
</tvshow>
'''
            content = os.linesep.join(filter(
                lambda s: s.replace(
                    '<studio></studio>', '',
                ).replace(
                    '<tag></tag>', '',
                ).lstrip(' '),
                content.splitlines(),
            )) + os.linesep
            log.debug(
                f'Writing new content to: {nfo_path}',
            )
            write_text_file(nfo_path, content)
            log.info(
                f'Wrote a new "{self.filename}" file for: {source}',
            )

