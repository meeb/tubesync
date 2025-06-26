import json
import urllib
from django.core.management.base import BaseCommand, CommandError # noqa
from common.json import JSONEncoder


class Command(BaseCommand):

    help = 'Displays subscription information in JSON to the console'

    def add_arguments(self, parser):
        parser.add_argument('url', type=str)

    def handle(self, *args, **options):
        url = options['url']
        self.stderr.write(f'Showing information for URL: {url}')
        info = dict()
        try:
            request = urllib.request.Request(url)
            with urllib.request.urlopen(request) as response:
                info = json.loads(response.read().decode())
        except urllib.error.HTTPError as e:
            self.stderr.write(e)
        d = json.dumps(info, indent=4, sort_keys=True, cls=JSONEncoder)
        self.stdout.write(d)
        self.stderr.write('Done')

