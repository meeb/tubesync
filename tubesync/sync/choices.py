from django.db import models
from django.utils.translation import gettext_lazy as _


DOMAINS = dict({
    'youtube': frozenset({
        'youtube.com',
        'm.youtube.com',
        'www.youtube.com',
    }),
})


# as stolen from:
# - https://wiki.sponsor.ajay.app/w/Types
# - https://github.com/yt-dlp/yt-dlp/blob/master/yt_dlp/postprocessor/sponsorblock.py
#
# The spacing is a little odd, it is for easy copy/paste selection.
# Please don't change it.
# Every possible category fits in a string < 128 characters
class SponsorBlock_Category(models.TextChoices):
    SPONSOR = 'sponsor', _( 'Sponsor' )
    INTRO = 'intro', _( 'Intermission/Intro Animation' )
    OUTRO = 'outro', _( 'Endcards/Credits' )
    SELFPROMO = 'selfpromo', _( 'Unpaid/Self Promotion' )
    PREVIEW = 'preview', _( 'Preview/Recap' )
    FILLER = 'filler', _( 'Filler Tangent' )
    INTERACTION = 'interaction', _( 'Interaction Reminder' )
    MUSIC_OFFTOPIC = 'music_offtopic', _( 'Non-Music Section' )


class YouTube_SourceType(models.TextChoices):
    CHANNEL = 'c', _('YouTube channel')
    CHANNEL_ID = 'i', _('YouTube channel ID')
    PLAYLIST = 'p', _('YouTube playlist')


youtube_long_source_types = {
    'youtube-channel': YouTube_SourceType.CHANNEL.value,
    'youtube-channel-id': YouTube_SourceType.CHANNEL_ID.value,
    'youtube-playlist': YouTube_SourceType.PLAYLIST.value,
}


youtube_help = {
    'examples': {
        YouTube_SourceType.CHANNEL.value: 'https://www.youtube.com/google',
        YouTube_SourceType.CHANNEL_ID.value: ('https://www.youtube.com/channel/'
                                        'UCK8sQmJBp8GCxrOtXWBpyEA'),
        YouTube_SourceType.PLAYLIST.value: ('https://www.youtube.com/playlist?list='
                                      'PL590L5WQmH8dpP0RyH5pCfIaDEdt9nk7r'),
    },
    'texts': {
        YouTube_SourceType.CHANNEL.value: _(
            'Enter a YouTube channel URL into the box below. A channel URL will be in '
            'the format of <strong>https://www.youtube.com/CHANNELNAME</strong> '
            'where <strong>CHANNELNAME</strong> is the name of the channel you want '
            'to add.'
        ),
        YouTube_SourceType.CHANNEL_ID.value: _(
            'Enter a YouTube channel URL by channel ID into the box below. A channel '
            'URL by channel ID will be in the format of <strong>'
            'https://www.youtube.com/channel/BiGLoNgUnIqUeId</strong> '
            'where <strong>BiGLoNgUnIqUeId</strong> is the ID of the channel you want '
            'to add.'
        ),
        YouTube_SourceType.PLAYLIST.value: _(
            'Enter a YouTube playlist URL into the box below. A playlist URL will be '
            'in the format of <strong>https://www.youtube.com/playlist?list='
            'BiGLoNgUnIqUeId</strong> where <strong>BiGLoNgUnIqUeId</strong> is the '
            'unique ID of the playlist you want to add.'
        ),
    },
}


youtube_validation_urls = {
    YouTube_SourceType.CHANNEL.value: {
        'scheme': 'https',
        'domains': DOMAINS['youtube'],
        'path_regex': '^\/(c\/)?([^\/]+)(\/videos)?$',
        'path_must_not_match': ('/playlist', '/c/playlist'),
        'qs_args': [],
        'extract_key': ('path_regex', 1),
        'example': 'https://www.youtube.com/SOMECHANNEL'
    },
    YouTube_SourceType.CHANNEL_ID.value: {
        'scheme': 'https',
        'domains': DOMAINS['youtube'],
        'path_regex': '^\/channel\/([^\/]+)(\/videos)?$',
        'path_must_not_match': ('/playlist', '/c/playlist'),
        'qs_args': [],
        'extract_key': ('path_regex', 0),
        'example': 'https://www.youtube.com/channel/CHANNELID'
    },
    YouTube_SourceType.PLAYLIST.value: {
        'scheme': 'https',
        'domains': DOMAINS['youtube'],
        'path_regex': '^\/(playlist|watch)$',
        'path_must_not_match': (),
        'qs_args': ('list',),
        'extract_key': ('qs_args', 'list'),
        'example': 'https://www.youtube.com/playlist?list=PLAYLISTID'
    },
}

