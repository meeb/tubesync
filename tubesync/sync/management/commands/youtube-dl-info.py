import json
from django.core.management.base import BaseCommand, CommandError
from sync.youtube import get_media_info


class Command(BaseCommand):

    help = 'Displays information obtained by youtube-dl in JSON to the console'

    def add_arguments(self, parser):
        parser.add_argument('url', type=str)

    def handle(self, *args, **options):
        url = options['url']
        self.stdout.write(f'Showing information for URL: {url}')
        info = get_media_info(url)
        self.stdout.write(json.dumps(info, indent=4, sort_keys=True))
        self.stdout.write('Done')
