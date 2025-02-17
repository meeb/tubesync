import warnings
from xml.etree import ElementTree
import requests
from django.forms import ValidationError
from urllib.parse import urlsplit, urlunsplit, urlencode
from django.utils.translation import gettext_lazy as _
from common.logger import log


class MediaServerError(Exception):
    '''
        Raised when a back-end error occurs.
    '''
    pass


class MediaServer:

    TIMEOUT = 0
    HELP = ''

    def __init__(self, mediaserver_instance):
        self.object = mediaserver_instance

    def validate(self):
        raise NotImplementedError('MediaServer.validate() must be implemented')

    def update(self):
        raise NotImplementedError('MediaServer.update() must be implemented')


class PlexMediaServer(MediaServer):

    TIMEOUT = 5

    HELP = _('<p>To connect your TubeSync sevrer to your Plex Media Server you will '
             'need to enter the details of your Plex server below.</p>'
             '<p>The <strong>host</strong> can be either an IP address or valid hostname.</p>'
             '<p>The <strong>port</strong> number must be between 1 and 65536.</p>'
             '<p>The <strong>token</strong> is a Plex access token to your Plex server. You can find '
             'out how to get a Plex access token <a href="https://support.plex.tv/'
             'articles/204059436-finding-an-authentication-token-x-plex-token/" '
             'target="_blank">here</a>.</p>'
             '<p>The <strong>libraries</strong> is a comma-separated list of Plex '
             'library or section IDs, you can find out how to get your library or '
             'section IDs <a href="https://support.plex.tv/articles/201242707-plex-'
             'media-scanner-via-command-line/#toc-1" target="_blank">here</a> or '
             '<a href="https://www.plexopedia.com/plex-media-server/api/server/libraries/" '
             'target="_blank">here</a></p>.')

    def make_request(self, uri='/', params={}):
        headers = {'User-Agent': 'TubeSync'}
        token = self.object.loaded_options['token']
        params['X-Plex-Token'] = token
        base_parts = urlsplit(self.object.url)
        qs = urlencode(params)
        url = urlunsplit((base_parts.scheme, base_parts.netloc, uri, qs, ''))
        if self.object.verify_https:
            log.debug(f'[plex media server] Making HTTP GET request to: {url}')
            return requests.get(url, headers=headers, verify=True,
                                timeout=self.TIMEOUT)
        else:
            # If not validating SSL, given this is likely going to be for an internal
            # or private network, that Plex issues certs *.hash.plex.direct and that
            # the warning won't ever been sensibly seen in the HTTPS logs, hide it
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                return requests.get(url, headers=headers, verify=False,
                                    timeout=self.TIMEOUT)

    def validate(self):
        '''
            A Plex server requires a host, port, access token and a comma-separated
            list if library IDs.
        '''
        # Check all the required values are present
        if not self.object.host:
            raise ValidationError('Plex Media Server requires a "host"')
        if not self.object.port:
            raise ValidationError('Plex Media Server requires a "port"')
        try:
            port = int(self.object.port)
        except (TypeError, ValueError):
            raise ValidationError('Plex Media Server "port" must be an integer')
        if port < 1 or port > 65535:
            raise ValidationError('Plex Media Server "port" must be between 1 '
                                  'and 65535')
        options = self.object.loaded_options
        if 'token' not in options:
            raise ValidationError('Plex Media Server requires a "token"')
        token = options['token'].strip()
        if 'token' not in options:
            raise ValidationError('Plex Media Server requires a "token"')
        if 'libraries' not in options:
            raise ValidationError('Plex Media Server requires a "libraries"')
        libraries = options['libraries'].strip().split(',')
        for position, library in enumerate(libraries):
            library = library.strip()
            try:
                int(library)
            except (TypeError, ValueError):
                raise ValidationError(f'Plex Media Server library ID "{library}" at '
                                      f'position {position+1} must be an integer')
        # Test the details work by requesting a summary page from the Plex server
        try:
            response = self.make_request('/library/sections')
        except Exception as e:
            raise ValidationError(f'Failed to make a test connection to your Plex '
                                  f'Media Server at "{self.object.host}:'
                                  f'{self.object.port}", the error was "{e}". Check '
                                  'your host and port are correct.') from e
        if response.status_code != 200:
            check_token = ''
            if 400 <= response.status_code < 500:
                check_token = (' A 4XX error could mean your access token is being '
                               'rejected. Check your token is correct.')
            raise ValidationError(f'Your Plex Media Server returned an invalid HTTP '
                                  f'status code, expected 200 but received '
                                  f'{response.status_code}.' + check_token)
        try:
            parsed_response = ElementTree.fromstring(response.content)
        except Exception as e:
            raise ValidationError(f'Your Plex Media Server returned unexpected data, '
                                  f'expected valid XML but parsing it as XML caused '
                                  f'the error "{e}"')
        # Seems we have a valid library sections page, get the library IDs
        remote_libraries = {}
        try:
            for parent in parsed_response.iter('MediaContainer'):
                for d in parent:
                    library_id = d.attrib['key']
                    library_name = d.attrib['title']
                    remote_libraries[library_id] = library_name
        except Exception as e:
            raise ValidationError(f'Your Plex Media Server returned unexpected data, '
                                  f'the XML it returned could not be parsed and the '
                                  f'error was "{e}"')
        # Validate the library IDs
        remote_libraries_desc = []
        for remote_library_id, remote_library_name in remote_libraries.items():
            remote_libraries_desc.append(f'"{remote_library_name}" with ID '
                                         f'"{remote_library_id}"')
        remote_libraries_str = ', '.join(remote_libraries_desc)
        for library_id in libraries:
            library_id = library_id.strip()
            if library_id not in remote_libraries:
                raise ValidationError(f'One or more of your specified library IDs do '
                                      f'not exist on your Plex Media Server. Your '
                                      f'valid libraries are: {remote_libraries_str}')
        # All good!
        return True

    def update(self):
        # For each section / library ID pop off a request to refresh it
        libraries = self.object.loaded_options.get('libraries', '')
        for library_id in libraries.split(','):
            library_id = library_id.strip()
            uri = f'/library/sections/{library_id}/refresh'
            response = self.make_request(uri)
            if response.status_code != 200:
                raise MediaServerError(f'Failed to refresh library "{library_id}" on '
                                       f'Plex server "{self.object.url}", expected a '
                                       f'200 status code but got '
                                       f'{response.status_code}. Check your media '
                                       f'server details.')
        return True


class JellyfinMediaServer(MediaServer):
    TIMEOUT = 5

    HELP = _('<p>To connect your TubeSync server to your Jellyfin Media Server, please enter the details below.</p>'
             '<p>The <strong>host</strong> can be either an IP address or a valid hostname.</p>'
             '<p>The <strong>port</strong> should be between 1 and 65536.</p>'
             '<p>The <strong>token</strong> is required for API access. You can generate a token in your Jellyfin user profile settings.</p>'
             '<p>The <strong>libraries</strong> is a comma-separated list of library IDs in Jellyfin.</p>')

    def make_request(self, uri='/', params={}):
        headers = {
            'User-Agent': 'TubeSync',
            'X-Emby-Token': self.object.loaded_options['token']  # Jellyfin uses the same `X-Emby-Token` header as Emby
        }
        base_url = f"{self.object.url}:{self.object.port}" if self.object.port else self.object.url
        url = f"{base_url}{uri}"
        
        log.debug(f'[jellyfin media server] Making HTTP GET request to: {url}')
        
        return requests.get(url, headers=headers, verify=self.object.verify_https, timeout=self.TIMEOUT)

    def validate(self):
        if not self.object.host:
            raise ValidationError('Jellyfin Media Server requires a "host"')
        if not self.object.port:
            raise ValidationError('Jellyfin Media Server requires a "port"')
        
        try:
            port = int(self.object.port)
            if port < 1 or port > 65535:
                raise ValidationError('Jellyfin Media Server "port" must be between 1 and 65535')
        except (TypeError, ValueError):
            raise ValidationError('Jellyfin Media Server "port" must be an integer')
        
        options = self.object.loaded_options
        if 'token' not in options:
            raise ValidationError('Jellyfin Media Server requires a "token"')
        if 'libraries' not in options:
            raise ValidationError('Jellyfin Media Server requires a "libraries"')
        
        # Test connection and fetch libraries
        try:
            response = self.make_request('/Library/MediaFolders', params={'Recursive': 'true', 'IncludeItemTypes': 'CollectionFolder'})
            if response.status_code != 200:
                raise ValidationError(f'Failed to connect to Jellyfin server: {response.status_code}')
            data = response.json()
            if 'Items' not in data:
                raise ValidationError('Jellyfin Media Server returned unexpected data.')
        except Exception as e:
            raise ValidationError(f'Connection error: {e}')

        # Seems we have a valid library sections page, get the library IDs
        remote_libraries = {}
        try:
            for d in data['Items']:
                library_id = d['Id']
                library_name = d['Name']
                remote_libraries[library_id] = library_name
        except Exception as e:
            raise ValidationError(f'Jellyfin Media Server returned unexpected data, '
                                  f'the JSON it returned could not be parsed and the '
                                  f'error was "{e}"')
        # Validate the library IDs
        remote_libraries_desc = []
        for remote_library_id, remote_library_name in remote_libraries.items():
            remote_libraries_desc.append(f'"{remote_library_name}" with ID '
                                         f'"{remote_library_id}"')
        remote_libraries_str = ', '.join(remote_libraries_desc)
        for library_id in libraries:
            library_id = library_id.strip()
            if library_id not in remote_libraries:
                raise ValidationError(f'One or more of your specified library IDs do '
                                      f'not exist on your Plex Media Server. Your '
                                      f'valid libraries are: {remote_libraries_str}')
        
        return True

    def update(self):
        libraries = self.object.loaded_options.get('libraries', '').split(',')
        for library_id in libraries:
            library_id = library_id.strip()
            uri = f'/Library/{library_id}/Refresh'
            response = self.make_request(uri)
            if response.status_code != 204:  # 204 No Content is expected for successful refresh
                raise MediaServerError(f'Failed to refresh Jellyfin library "{library_id}", status code: {response.status_code}')
        return True
