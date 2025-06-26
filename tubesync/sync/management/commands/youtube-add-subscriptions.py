import json
import urllib
from django.core.management.base import BaseCommand, CommandError # noqa
from common.json import JSONEncoder
from sync.models import Source


class Command(BaseCommand):

    help = 'Displays subscription information in JSON to the console'

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
        self.stderr.write('Done')

