import json
import urllib
from django.core.management.base import BaseCommand, CommandError # noqa
from common.json import JSONEncoder
from sync.choices import Val, YouTube_SourceType # noqa
from sync.models import Source


class Command(BaseCommand):

    help = 'Adds sources for any new subscription information'

    def add_arguments(self, parser):
        parser.add_argument('url', type=str)

    def handle(self, *args, **options):
        url = options['url']
        existing_sources = set()
        for source in Source.objects.all().only('uuid', 'key'):
            existing_sources.add(source.key)
        self.stderr.write(f'Showing information for URL: {url}')
        info = dict()
        try:
            request = urllib.request.Request(url)
            with urllib.request.urlopen(request) as response:
                info = json.loads(response.read().decode())
        except urllib.error.HTTPError as e:
            self.stderr.write(e)
        subscriptions = info.get('subscriptions', [])
        keys = ('channelId', 'title',)
        sources = [
            {
                k:v for k,v in s.get('snippet', {}).items() \
                if k in keys
            } for s in subscriptions \
            if s.get('snippet', {}).get(keys[0]) not in existing_sources
        ]
        d = json.dumps(sources, indent=4, sort_keys=True, cls=JSONEncoder)
        self.stdout.write(d)
        source_objs = [
            Source(key=s[keys[0]], name=s[keys[1]]) for s in sources
        ]
        for source in source_objs:
            source.source_type = YouTube_SourceType.CHANNEL_ID
            source.copy_channel_images = True
            source.directory = source.slugname
            source.embed_thumbnail = True
            source.enable_sponsorblock = False
            source.prefer_60fps = False
            source.write_json = True
            source.write_subtitles = True
            source.save()
            self.stderr.write(f'Added a new source: {source.name}')
        self.stderr.write('Done')

