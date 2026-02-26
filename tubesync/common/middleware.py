from django.conf import settings
from basicauth.middleware import BasicAuthMiddleware as BaseBasicAuthMiddleware


class BasicAuthMiddleware(BaseBasicAuthMiddleware):

    def process_request(self, request):
        bypass_uris = getattr(settings, 'BASICAUTH_ALWAYS_ALLOW_URIS', [])
        if request.path in bypass_uris:
            return None
        return super().process_request(request)
