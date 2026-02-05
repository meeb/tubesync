from random import random
from django.conf import settings
from django.shortcuts import render
from django.views.generic import View
from django.http import HttpResponse, HttpResponseServerError, HttpResponseRedirect
from django.core.exceptions import PermissionDenied
from django.db import connection
from .utils import get_client_ip
from .context_processors import THEME_COOKIE_NAME


def toggle_theme(request):
    '''
    Toggle between light and dark theme by setting a cookie.
    Redirects back to the referring page or dashboard.
    '''
    current_theme = request.COOKIES.get(THEME_COOKIE_NAME, 'light')
    new_theme = 'dark' if current_theme == 'light' else 'light'
    redirect_url = request.META.get('HTTP_REFERER', '/')
    response = HttpResponseRedirect(redirect_url)
    response.set_cookie(
        THEME_COOKIE_NAME,
        new_theme,
        max_age=365 * 24 * 60 * 60,  # 1 year
        samesite='Lax',
    )
    return response


def error403(request, *args, **kwargs):
    return render(request, 'error403.html', status=403)


def error404(request, *args, **kwargs):
    return render(request, 'error404.html', status=404)


def error500(request, *args, **kwargs):
    return render(request, 'error500.html', status=500)


class HealthCheckView(View):
    '''
        A basic healthcheck view. SELECTs a random int via the database connection
        and verifies it matches. This checks that the application server, django and
        the database connection are all working correctly.
    '''

    ALLOWED_IPS = settings.HEALTHCHECK_ALLOWED_IPS

    def get(self, request, *args, **kwargs):
        if settings.HEALTHCHECK_FIREWALL:
            client_ip = get_client_ip(request)
            if client_ip not in self.ALLOWED_IPS:
                raise PermissionDenied
        randomint = int(random() * (10 ** 10))
        with connection.cursor() as cursor:
            cursor.execute('select {}'.format(randomint))
            row = cursor.fetchone()
        try:
            pong = row[0]
        except IndexError:
            pong = False
        if str(pong) != str(randomint):
            err = 'Failed healtcheck, expected "{}" got "{}"'
            return HttpResponseServerError(err.format(randomint, pong))
        else:
            return HttpResponse('ok')
