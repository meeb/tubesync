from django.db import models
from django.utils.translation import gettext_lazy as _

from copy import deepcopy


DOMAINS = dict({
    'youtube': frozenset({
        'youtube.com',
        'm.youtube.com',
        'www.youtube.com',
    }),
})


def Val(*args):
    results = list(
        a.value if isinstance(a, models.enums.Choices) else a for a in args
    )
    return results.pop(0) if 1 == len(results) else (*results,)


class CapChoices(models.IntegerChoices):
    CAP_NOCAP = 0, _('No cap')
    CAP_7DAYS = 604800, _('1 week (7 days)')
    CAP_30DAYS = 2592000, _('1 month (30 days)')
    CAP_90DAYS = 7776000, _('3 months (90 days)')
    CAP_6MONTHS = 15552000, _('6 months (180 days)')
    CAP_1YEAR = 31536000, _('1 year (365 days)')
    CAP_2YEARs = 63072000, _('2 years (730 days)')
    CAP_3YEARs = 94608000, _('3 years (1095 days)')
    CAP_5YEARs = 157680000, _('5 years (1825 days)')
    CAP_10YEARS = 315360000, _('10 years (3650 days)')


class Fallback(models.TextChoices):
    FAIL = 'f', _('Fail, do not download any media')
    NEXT_BEST = 'n', _('Get next best resolution or codec instead')
    NEXT_BEST_HD = 'h', _('Get next best resolution but at least HD')


class FileExtension(models.TextChoices):
    M4A = 'm4a', _('MPEG-4 Part 14 (MP4) Audio Container')
    OGG = 'ogg', _('Ogg Container')
    MKV = 'mkv', _('Matroska Multimedia Container')


class FilterSeconds(models.IntegerChoices):
    MIN = True, _('Minimum Length')
    MAX = False, _('Maximum Length')


class IndexSchedule(models.IntegerChoices):
    EVERY_HOUR = 3600, _('Every hour')
    EVERY_2_HOURS = 7200, _('Every 2 hours')
    EVERY_3_HOURS = 10800, _('Every 3 hours')
    EVERY_4_HOURS = 14400, _('Every 4 hours')
    EVERY_5_HOURS = 18000, _('Every 5 hours')
    EVERY_6_HOURS = 21600, _('Every 6 hours')
    EVERY_12_HOURS = 43200, _('Every 12 hours')
    EVERY_24_HOURS = 86400, _('Every 24 hours')
    EVERY_3_DAYS = 259200, _('Every 3 days')
    EVERY_7_DAYS = 604800, _('Every 7 days')
    NEVER = 0, _('Never')


class MediaServerType(models.TextChoices):
    JELLYFIN = 'j', _('Jellyfin')
    PLEX = 'p', _('Plex')

    @classmethod
    def forms_dict(cls):
        from .forms import (
            JellyfinMediaServerForm,
            PlexMediaServerForm,
        )
        return dict(zip(
            cls.values,
            (
                JellyfinMediaServerForm,
                PlexMediaServerForm,
            ),
        ))

    @classmethod
    def handlers_dict(cls):
        from .mediaservers import (
            JellyfinMediaServer,
            PlexMediaServer,
        )
        return dict(zip(
            cls.values,
            (
                JellyfinMediaServer,
                PlexMediaServer,
            ),
        ))

    @property
    def long_type(self):
        return self.long_types().get(self.value)

    @classmethod
    def long_types(cls):
        d = dict(zip(
            list(map(cls.lower, cls.names)),
            cls.values,
        ))
        rd = dict(zip( d.values(), d.keys() ))
        rd.update(d)
        return rd

    @classmethod
    def members_list(cls):
        return list(cls.__members__.values())


class MediaState(models.TextChoices):
    UNKNOWN = 'unknown'
    SCHEDULED = 'scheduled'
    DOWNLOADING = 'downloading'
    DOWNLOADED = 'downloaded'
    SKIPPED = 'skipped'
    DISABLED_AT_SOURCE = 'source-disabled'
    ERROR = 'error'


class SourceResolution(models.TextChoices):
    AUDIO = 'audio', _('Audio only')
    VIDEO_360P = '360p', _('360p (SD)')
    VIDEO_480P = '480p', _('480p (SD)')
    VIDEO_720P = '720p', _('720p (HD)')
    VIDEO_1080P = '1080p', _('1080p (Full HD)')
    VIDEO_1440P = '1440p', _('1440p (2K)')
    VIDEO_2160P = '2160p', _('2160p (4K)')
    VIDEO_4320P = '4320p', _('4320p (8K)')

    @classmethod
    def _integer_mapping(cls):
        int_height = lambda s: int(s[:-1], base=10)
        video = list(filter(lambda s: s.endswith('0p'), cls.values))
        return dict(zip( video, map(int_height, video) ))


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
    CHANNEL_ID = 'i', _('YouTube channel by ID')
    PLAYLIST = 'p', _('YouTube playlist')

    @classmethod
    def _validation_urls(cls):
        defaults = {
            'scheme': 'https',
            'domains': DOMAINS['youtube'],
            'qs_args': [],
        }
        update_and_return = lambda c, d: c.update(d) or c
        return dict(zip(
            cls.values,
            (
                update_and_return(deepcopy(defaults), {
                    'path_regex': r'^\/(c\/)?([^\/]+)(\/videos)?$',
                    'path_must_not_match': ('/playlist', '/c/playlist'),
                    'extract_key': ('path_regex', 1),
                    'example': 'https://www.youtube.com/SOMECHANNEL',
                }),
                update_and_return(deepcopy(defaults), {
                    'path_regex': r'^\/channel\/([^\/]+)(\/videos)?$',
                    'path_must_not_match': ('/playlist', '/c/playlist'),
                    'extract_key': ('path_regex', 0),
                    'example': 'https://www.youtube.com/channel/CHANNELID',
                }),
                update_and_return(deepcopy(defaults), {
                    'path_regex': r'^\/(playlist|watch)$',
                    'path_must_not_match': (),
                    'qs_args': ('list',),
                    'extract_key': ('qs_args', 'list'),
                    'example': 'https://www.youtube.com/playlist?list=PLAYLISTID',
                }),
            ),
        ))

    @classmethod
    def _long_type_mapping(cls):
        return dict(zip(
            (
                'youtube-channel',
                'youtube-channel-id',
                'youtube-playlist',
            ),
            cls.values,
        ))


class YouTube_AudioCodec(models.TextChoices):
    OPUS = 'OPUS', _('OPUS')
    MP4A = 'MP4A', _('MP4A')


class YouTube_VideoCodec(models.TextChoices):
    AV1 = 'AV1', _('AV1')
    VP9 = 'VP9', _('VP9')
    AVC1 = 'AVC1', _('AVC1 (H.264)')


SourceResolutionInteger = SourceResolution._integer_mapping()
youtube_long_source_types = YouTube_SourceType._long_type_mapping()
youtube_validation_urls = YouTube_SourceType._validation_urls()
youtube_help = {
    'examples': dict(zip(
        YouTube_SourceType.values,
        (
            ('https://www.youtube.com/google'),
            ('https://www.youtube.com/channel/'
             'UCK8sQmJBp8GCxrOtXWBpyEA'),
            ('https://www.youtube.com/playlist?list='
             'PL590L5WQmH8dpP0RyH5pCfIaDEdt9nk7r'),
        ),
    )),
    'texts': dict(zip(
        YouTube_SourceType.values,
        (
            _(
                'Enter a YouTube channel URL into the box below. A channel URL will be in '
                'the format of <strong>https://www.youtube.com/CHANNELNAME</strong> '
                'where <strong>CHANNELNAME</strong> is the name of the channel you want '
                'to add.'
            ),
            _(
                'Enter a YouTube channel URL by channel ID into the box below. A channel '
                'URL by channel ID will be in the format of <strong>'
                'https://www.youtube.com/channel/BiGLoNgUnIqUeId</strong> '
                'where <strong>BiGLoNgUnIqUeId</strong> is the ID of the channel you want '
                'to add.'
            ),
            _(
                'Enter a YouTube playlist URL into the box below. A playlist URL will be '
                'in the format of <strong>https://www.youtube.com/playlist?list='
                'BiGLoNgUnIqUeId</strong> where <strong>BiGLoNgUnIqUeId</strong> is the '
                'unique ID of the playlist you want to add.'
            ),
        ),
    )),
}

