from common.utils import getenv
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
from yt_dlp.extractor.youtube.pot.cache import (
    PoTokenCacheProvider,
    register_preference,
    register_provider
)

from yt_dlp.extractor.youtube.pot.provider import PoTokenRequest


@register_provider
class TubeSyncFileSystemPCP(PoTokenCacheProvider):  # Provider class name must end with "PCP"
    PROVIDER_VERSION = '0.0.1'
    # Define a unique display name for the provider
    PROVIDER_NAME = 'TubeSync-fs'
    BUG_REPORT_LOCATION = 'https://github.com/meeb/tubesync/issues'

    def _make_filename(self, key: str, expires_at: int) -> str:
        result = sha256(key.encode(), usedforsecurity=False)
        return f'{expires_at or "*"}-{result.hexdigest()}'
        
    def is_available(self) -> bool:
        """
        Check if the provider is available (e.g. all required dependencies are available)
        This is used to determine if the provider should be used and to provide debug information.

        IMPORTANT: This method SHOULD NOT make any network requests or perform any expensive operations.

        Since this is called multiple times, we recommend caching the result.
        """
        cache_home = getenv('XDG_CACHE_HOME')
        if not cache_home:
            return False
        directory = Path(cache_home) / 'yt-dlp/youtube-pot'
        if directory.exists() and directory.is_dir():
            self._storage_directory = directory
            return True
        return False

    def get(self, key: str):
        # ℹ️ Similar to PO Token Providers, Cache Providers and Cache Spec Providers 
        # are passed down extractor args matching key youtubepot-<PROVIDER_KEY>.
        # some_setting = self._configuration_arg('some_setting', default=['default_value'])[0]
        found = None
        now = datetime.utcnow().astimezone(timezone.utc)
        files = Path(self._storage_directory).glob(self._make_filename(key, 0))
        for file in files:
            if not file.is_file():
                continue
            try:
                expires_at = int(file.name.partition('-')[0])
            except ValueError:
                continue
            else:
                expired = datetime.utcfromtimestamp(expires_at).astimezone(timezone.utc)
                if expired < now:
                    file.unlink()
                else:
                    found = file

        return None if found is None else found.read_bytes().decode()

    def store(self, key: str, value: str, expires_at: int):
        # ⚠ expires_at MUST be respected. 
        # Cache entries should not be returned if they have expired.
        dst = Path(self._storage_directory) / self._make_filename(key, expires_at)
        now = datetime.utcnow().astimezone(timezone.utc)
        expires = datetime.utcfromtimestamp(expires_at).astimezone(timezone.utc)
        if expires > now:
            dst.write_bytes(value.encode())

    def delete(self, key: str):
        files = Path(self._storage_directory).glob(self._make_filename(key, 0))
        for file in files:
            if not file.is_file():
                continue
            file.unlink()

    def close(self):
        # Optional close hook, called when the YoutubeDL instance is closed.
        pass

# If there are multiple PO Token Cache Providers available, you can 
# define a preference function to increase/decrease the priority of providers. 

# IMPORTANT: Providers should be in preference of cache lookup time. 
# For example, a memory cache should have a higher preference than a disk cache. 

# VERY IMPORTANT: yt-dlp has a built-in memory cache with a priority of 10000. 
# Your cache provider should be lower than this.


@register_preference(TubeSyncFileSystemPCP)
def filesystem_cache_preference(provider: PoTokenCacheProvider, request: PoTokenRequest) -> int:
    return 10
