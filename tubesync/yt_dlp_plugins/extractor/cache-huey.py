from datetime import datetime, timezone
from django_huey import get_queue
from pathlib import Path
from sync.choices import Val, TaskQueue
from yt_dlp.extractor.youtube.pot.cache import (
    PoTokenCacheProvider,
    register_preference,
    register_provider
)

from yt_dlp.extractor.youtube.pot.provider import PoTokenRequest


@register_provider
class TubeSyncHueyPCP(PoTokenCacheProvider):
    PROVIDER_VERSION = '0.0.1'
    PROVIDER_NAME = 'TubeSync-huey'
    BUG_REPORT_LOCATION = 'https://github.com/meeb/tubesync/issues'

    def _now(self) -> datetime:
        return datetime.now(timezone.utc)

    def _expires(self, expires_at: int) -> datetime:
        return datetime.utcfromtimestamp(expires_at).astimezone(timezone.utc)

    def _huey_key(self, key: str) -> str:
        return f'{self.huey.name}.youtube-pot.{key}'

    def is_available(self) -> bool:
        """
        Check if the provider is available (e.g. all required dependencies are available)
        This is used to determine if the provider should be used and to provide debug information.

        IMPORTANT: This method SHOULD NOT make any network requests or perform any expensive operations.

        Since this is called multiple times, we recommend caching the result.
        """
        cookie_file = self.ie.get_param('cookiefile')
        if cookie_file is None or not Path(cookie_file).is_file():
            return False
        try:
            huey = get_queue(Val(TaskQueue.LIMIT))
        except Exception as exc:
            self.logger.debug(str(exc))
            pass
        else:
            if huey:
                self.huey = huey
                return True
        return False

    def get(self, key: str):
        self.logger.trace(f'huey-get: {key=}')
        data = self.huey.get(peek=True, key=self._huey_key(key))
        if data is None:
            return None
        expires_at, value = data
        if self._expires(expires_at) < self._now():
            self.logger.trace(f'huey-get: EXPIRED {key=}')
            return None
        return value

    def store(self, key: str, value: str, expires_at: int):
        self.logger.trace(f'huey-store: {expires_at=} {key=}')
        if self._expires(expires_at) > self._now():
            data = (expires_at, value,)
            self.logger.trace(f'huey-store: saving: {self._huey_key(key)}')
            self.huey.put(self._huey_key(key), data)

    def delete(self, key: str):
        self.logger.trace(f'huey-delete: {key=}')
        self.huey.delete(self._huey_key(key))

    def close(self):
        pass


@register_preference(TubeSyncHueyPCP)
def huey_cache_preference(provider: PoTokenCacheProvider, request: PoTokenRequest) -> int:
    return 1000
