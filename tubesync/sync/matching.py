'''
    Match functions take a single Media object instance as its only argument and return
    two boolean values. The first value is if the match was exact or "best fit", the
    second argument is the ID of the format that was matched.
'''


from django.conf import settings
from common.utils import multi_key_sort, resolve_priority_order
from .choices import Val, Fallback


english_language_codes = resolve_priority_order(
    getattr(
        settings,
        'ENGLISH_LANGUAGE_CODE_ORDER',
        settings.DEFAULT_ENGLISH_LCO,
    ),
    settings.DEFAULT_ENGLISH_LCO,
)
min_height = getattr(settings, 'VIDEO_HEIGHT_CUTOFF', 360)
fallback_hd_cutoff = getattr(settings, 'VIDEO_HEIGHT_IS_HD', 500)


def get_fallback_id(by_fmt_id, /, by_language = {}, *, exact = False, fallback_id = False):
    assert isinstance(by_fmt_id, dict), type(by_fmt_id)
    assert isinstance(by_language, dict), type(by_language)
    assert exact in (True, False,), 'invalid value for exact'

    # prefer default
    if 'default' in by_fmt_id and 'id' in by_fmt_id['default']:
        return exact, by_fmt_id['default']['id']

    # try for English
    for lc in english_language_codes:
        if lc in by_language:
            return exact, by_language[lc]

    # use the fallback ID or report no results by default
    if fallback_id or (exact is False and fallback_id is False):
        return exact, fallback_id


def get_best_combined_format(media):
    '''
        Attempts to see if there is a single, combined audio and video format that
        exactly matches the source requirements. This is used over separate audio
        and video formats if possible. Combined formats are the easiest to check
        for as they must exactly match the source profile be be valid.
    '''
    matches = set()
    by_fmt_id = dict()
    by_language = dict()
    for fmt in media.iter_formats():
        # Check height matches
        if media.source.source_resolution_height != fmt['height']:
            continue
        # Check the video codec matches
        if media.source.source_vcodec != fmt['vcodec']:
            continue
        # Check the audio codec matches
        if media.source.source_acodec != fmt['acodec']:
            continue
        # if the source prefers 60fps, check for it
        if media.source.prefer_60fps:
            if not fmt['is_60fps']:
                continue
        # If the source prefers HDR, check for it
        if media.source.prefer_hdr:
            if not fmt['is_hdr']:
                continue
        # If we reach here, we have a combined match!
        matches.add(fmt['id'])
        by_fmt_id[fmt['id']] = fmt
        by_language[fmt['language_code']] = fmt['id']
        if 'format_note' in fmt and '(default)' in fmt['format_note']:
            by_fmt_id['default'] = fmt

    # nothing matched, return early
    if not matches:
        return False, False

    # use any available matching format
    return get_fallback_id(by_fmt_id, by_language, exact=True, fallback_id=matches.pop())


def get_best_audio_format(media):
    '''
        Finds the best match for the source required audio format. If the source
        has a 'fallback' of fail this can return no match.
    '''
    # Reverse order all audio-only formats
    audio_formats = set()
    by_fmt_acodec = dict()
    by_fmt_id = dict()
    by_language = dict()
    for fmt in media.iter_formats():
        # If the format has a video stream, skip it
        if fmt['vcodec'] is not None:
            continue
        if not fmt['acodec']:
            continue
        audio_formats.add(fmt['id'])
        by_fmt_id[fmt['id']] = fmt
        by_fmt_acodec[fmt['acodec']] = fmt['id']
        by_language[fmt['language_code']] = fmt['id']
        if 'format_note' in fmt and '(default)' in fmt['format_note']:
            by_fmt_id['default'] = fmt
    if not audio_formats:
        # Media has no audio formats at all
        return False, False
    # Find the first audio format with a matching codec
    if (fmt_id := by_fmt_acodec.get(media.source.source_acodec)) is not None:
        # Matched!
        return True, fmt_id
    # No codecs matched
    if not media.source.can_fallback:
        # Can't fallback
        return False, False

    # Can fallback, find the next non-matching codec
    return get_fallback_id(by_fmt_id, by_language, exact=False, fallback_id=audio_formats.pop())


def get_best_video_format(media):
    '''
        Finds the best match for the source required video format. If the source
        has a 'fallback' of fail this can return no match. Resolution is treated
        as the most important factor to match. This is pretty verbose due to the
        'soft' matching requirements for prefer_hdr and prefer_60fps.
    '''
    # Check if the source wants audio only, fast path to return
    if media.source.is_audio:
        return False, False
    source_resolution = media.source.source_resolution.strip().upper()
    source_resolution_height = media.source.source_resolution_height
    source_vcodec = media.source.source_vcodec
    can_switch_codecs = (
        media.source.can_fallback and
        media.source.fallback != Val(Fallback.REQUIRE_CODEC)
    )
    def matched_resolution(fmt):
        if fmt['format'] == source_resolution:
            return True
        elif fmt['height'] == source_resolution_height:
            return True
        return False
    # Filter video-only formats by resolution that matches the source
    video_formats = []
    sort_keys = [('height', False), ('vcodec', True), ('vbr', False)] # key, reverse
    for fmt in media.iter_formats():
        # If the format has an audio stream, skip it
        if fmt['acodec'] is not None:
            continue
        if not fmt['vcodec']:
            continue
        # Disqualify AI-upscaled "super resolution" formats
        # ID: 248-sr , 1080p, AI-upscaled, TV (1920x1080), fps:25, video:VP9 @1409.292k
        # ID: 399-sr , 1080p, AI-upscaled, TV (1920x1080), fps:25, video:AV1 @1155.505k
        # https://github.com/meeb/tubesync/issues/1357
        if '-sr' in fmt['id']:
            continue
        if any(key[0] not in fmt for key in sort_keys):
            continue
        accept_codec = (
            matched_resolution(fmt) and
            (can_switch_codecs or (source_vcodec == fmt['vcodec']))
        )
        if accept_codec:
            video_formats.append(fmt)
    # Check we matched some streams
    if not video_formats:
        # No streams match the requested resolution, see if we can fallback
        if not media.source.can_fallback:
            # Can't fallback
            return False, False
        # Find the next-best format matches by height
        for fmt in media.iter_formats():
            # If the format has an audio stream, skip it
            if fmt['acodec'] is not None:
                continue
            # Disqualify AI-upscaled "super resolution" formats
            # See above for more details.
            if '-sr' in fmt['id']:
                continue
            accept_height = (
                fmt['height'] >= min_height and
                fmt['height'] <= source_resolution_height
            )
            if accept_height:
                video_formats.append(fmt)
    if not video_formats:
        # Still no matches
        return False, False
    video_formats = multi_key_sort(video_formats, sort_keys, True)
    exact_match, best_match = None, None
    # Of our filtered video formats, check for resolution + codec + hdr + fps match
    if media.source.prefer_60fps and media.source.prefer_hdr:
        for fmt in video_formats:
            # Check for an exact match
            if (matched_resolution(fmt) and
                source_vcodec == fmt['vcodec'] and 
                fmt['is_hdr'] and
                fmt['is_60fps']):
                # Exact match
                exact_match, best_match = True, fmt
                break
        if media.source.can_fallback:
            if not best_match and can_switch_codecs:
                for fmt in video_formats:
                    # Check for a resolution, hdr and fps match but drop the codec
                    if (matched_resolution(fmt) and 
                        fmt['is_hdr'] and fmt['is_60fps']):
                        # Close match
                        exact_match, best_match = False, fmt
                        break
            if not best_match:
                for fmt in video_formats:
                    # Check for a codec, hdr and fps match but drop the resolution
                    if (source_vcodec == fmt['vcodec'] and 
                        fmt['is_hdr'] and fmt['is_60fps']):
                        # Close match
                        exact_match, best_match = False, fmt
                        break
            if not best_match:
                for fmt in video_formats:
                    # Check for resolution, codec and 60fps match
                    if (matched_resolution(fmt) and
                        source_vcodec == fmt['vcodec'] and
                        fmt['is_60fps']):
                        exact_match, best_match = False, fmt
                        break
            if not best_match and can_switch_codecs:
                for fmt in video_formats:
                    # Check for resolution and hdr match
                    if (matched_resolution(fmt) and
                        fmt['is_hdr']):
                        exact_match, best_match = False, fmt
                        break
            if not best_match and can_switch_codecs:
                for fmt in video_formats:
                    # Check for resolution and 60fps match
                    if (matched_resolution(fmt) and
                        fmt['is_60fps']):
                        exact_match, best_match = False, fmt
                        break
            if not best_match:
                for fmt in video_formats:
                    # Check for resolution, codec and hdr match
                    if (matched_resolution(fmt) and
                        source_vcodec == fmt['vcodec'] and
                        fmt['is_hdr']):
                        exact_match, best_match = False, fmt
                        break
            if not best_match:
                for fmt in video_formats:
                    # Check for resolution and codec
                    if (matched_resolution(fmt) and
                        source_vcodec == fmt['vcodec']):
                        exact_match, best_match = False, fmt
                        break
            if not best_match and can_switch_codecs:
                for fmt in video_formats:
                    # Check for resolution
                    if matched_resolution(fmt):
                        exact_match, best_match = False, fmt
                        break
            if not best_match:
                for fmt in video_formats:
                    # Check for codec
                    if (source_vcodec == fmt['vcodec']):
                        exact_match, best_match = False, fmt
                        break
            if not best_match and can_switch_codecs:
                # Match the highest resolution
                exact_match, best_match = False, video_formats[0]
    # Check for resolution + codec + fps match
    if media.source.prefer_60fps and not media.source.prefer_hdr:
        for fmt in video_formats:
            # Check for an exact match
            if (matched_resolution(fmt) and
                source_vcodec == fmt['vcodec'] and 
                fmt['is_60fps'] and
                not fmt['is_hdr']):
                # Exact match
                exact_match, best_match = True, fmt
                break
        if media.source.can_fallback:
            if not best_match and can_switch_codecs:
                for fmt in video_formats:
                    # Check for a resolution and fps match but drop the codec
                    if (matched_resolution(fmt) and 
                        fmt['is_60fps'] and
                        not fmt['is_hdr']):
                        exact_match, best_match = False, fmt
                        break
            if not best_match:
                for fmt in video_formats:
                    # Check for a codec and fps match but drop the resolution
                    if (source_vcodec == fmt['vcodec'] and 
                        fmt['is_60fps'] and
                        not fmt['is_hdr']):
                        exact_match, best_match = False, fmt
                        break
            if not best_match:
                for fmt in video_formats:
                    # Check for a codec and 60fps match
                    if (source_vcodec == fmt['vcodec'] and 
                        fmt['is_60fps']):
                        exact_match, best_match = False, fmt
                        break
            if not best_match:
                for fmt in video_formats:
                    # Check for codec and resolution match but drop 60fps
                    if (matched_resolution(fmt) and
                        source_vcodec == fmt['vcodec'] and
                        not fmt['is_hdr']):
                        exact_match, best_match = False, fmt
                        break
            if not best_match:
                for fmt in video_formats:
                    # Check for codec and resolution match only
                    if (matched_resolution(fmt) and
                        source_vcodec == fmt['vcodec']):
                        exact_match, best_match = False, fmt
                        break
            if not best_match and can_switch_codecs:
                for fmt in video_formats:
                    # Check for resolution
                    if matched_resolution(fmt):
                        exact_match, best_match = False, fmt
                        break
            if not best_match:
                for fmt in video_formats:
                    # Check for codec
                    if (source_vcodec == fmt['vcodec']):
                        exact_match, best_match = False, fmt
                        break
            if not best_match and can_switch_codecs:
                # Match the highest resolution
                exact_match, best_match = False, video_formats[0]
    # Check for resolution + codec + hdr
    elif media.source.prefer_hdr and not media.source.prefer_60fps:
        for fmt in video_formats:
            # Check for an exact match
            if (matched_resolution(fmt) and
                source_vcodec == fmt['vcodec'] and 
                fmt['is_hdr']):
                # Exact match
                exact_match, best_match = True, fmt
                break
        if media.source.can_fallback:
            if not best_match and can_switch_codecs:
                for fmt in video_formats:
                    # Check for a resolution and fps match but drop the codec
                    if (matched_resolution(fmt) and 
                        fmt['is_hdr'] and
                        not fmt['is_60fps']):
                        exact_match, best_match = False, fmt
                        break
            if not best_match:
                for fmt in video_formats:
                    # Check for a codec and fps match but drop the resolution
                    if (source_vcodec == fmt['vcodec'] and 
                        fmt['is_hdr'] and
                        not fmt['is_60fps']):
                        exact_match, best_match = False, fmt
                        break
            if not best_match:
                for fmt in video_formats:
                    # Check for a codec and 60fps match
                    if (source_vcodec == fmt['vcodec'] and 
                        fmt['is_hdr']):
                        exact_match, best_match = False, fmt
                        break
            if not best_match:
                for fmt in video_formats:
                    # Check for codec and resolution match but drop hdr
                    if (matched_resolution(fmt) and
                        source_vcodec == fmt['vcodec'] and
                        not fmt['is_60fps']):
                        exact_match, best_match = False, fmt
                        break
            if not best_match:
                for fmt in video_formats:
                    # Check for codec and resolution match only
                    if (matched_resolution(fmt) and
                        source_vcodec == fmt['vcodec']):
                        exact_match, best_match = False, fmt
                        break
            if not best_match and can_switch_codecs:
                for fmt in video_formats:
                    # Check for resolution
                    if matched_resolution(fmt):
                        exact_match, best_match = False, fmt
                        break
            if not best_match:
                for fmt in video_formats:
                    # Check for codec
                    if (source_vcodec == fmt['vcodec']):
                        exact_match, best_match = False, fmt
                        break
            if not best_match and can_switch_codecs:
                # Match the highest resolution
                exact_match, best_match = False, video_formats[0]
    # check for resolution + codec
    elif not media.source.prefer_hdr and not media.source.prefer_60fps:
        for fmt in video_formats:
            # Check for an exact match
            if (matched_resolution(fmt) and
                source_vcodec == fmt['vcodec'] and
                not fmt['is_60fps'] and
                not fmt['is_hdr']):
                # Exact match
                exact_match, best_match = True, fmt
                break
        if media.source.can_fallback:
            if not best_match and can_switch_codecs:
                for fmt in video_formats:
                    # Check for a resolution, hdr and fps match but drop the codec
                    if (matched_resolution(fmt) and 
                        not fmt['is_hdr'] and not fmt['is_60fps']):
                        # Close match
                        exact_match, best_match = False, fmt
                        break
            if not best_match:
                for fmt in video_formats:
                    # Check for a codec, hdr and fps match but drop the resolution
                    if (source_vcodec == fmt['vcodec'] and 
                        not fmt['is_hdr'] and not fmt['is_60fps']):
                        # Close match
                        exact_match, best_match = False, fmt
                        break
            if not best_match:
                for fmt in video_formats:
                    # Check for resolution, codec and hdr match
                    if (matched_resolution(fmt) and
                        source_vcodec == fmt['vcodec'] and
                        not fmt['is_hdr']):
                        exact_match, best_match = False, fmt
                        break
            if not best_match:
                for fmt in video_formats:
                    # Check for resolution, codec and 60fps match
                    if (matched_resolution(fmt) and
                        source_vcodec == fmt['vcodec'] and
                        not fmt['is_60fps']):
                        exact_match, best_match = False, fmt
                        break
            if not best_match:
                for fmt in video_formats:
                    # Check for resolution and codec
                    if (matched_resolution(fmt) and
                        source_vcodec == fmt['vcodec']):
                        exact_match, best_match = False, fmt
                        break
            if not best_match and can_switch_codecs:
                for fmt in video_formats:
                    # Check for resolution and not hdr
                    if (matched_resolution(fmt) and
                        not fmt['is_hdr']):
                        exact_match, best_match = False, fmt
                        break
            if not best_match and can_switch_codecs:
                for fmt in video_formats:
                    # Check for resolution
                    if matched_resolution(fmt):
                        exact_match, best_match = False, fmt
                        break
            if not best_match:
                for fmt in video_formats:
                    # Check for codec
                    if (source_vcodec == fmt['vcodec']):
                        exact_match, best_match = False, fmt
                        break
            if not best_match and can_switch_codecs:
                # Match the highest resolution
                exact_match, best_match = False, video_formats[0]
    # See if we found a match
    if best_match:
        # Final check to see if the match we found was good enough
        if exact_match:
            return True, best_match['id']
        elif media.source.can_fallback:
            # Allow the fallback if it meets requirements
            if (media.source.fallback == Val(Fallback.REQUIRE_HD) and
                best_match['height'] >= fallback_hd_cutoff):
                return False, best_match['id']
            elif (media.source.fallback == Val(Fallback.REQUIRE_CODEC) and
                source_vcodec == best_match['vcodec']):
                return False, best_match['id']
            elif media.source.fallback == Val(Fallback.NEXT_BEST_RESOLUTION):
                return False, best_match['id']
    # Nope, failed to find match
    return False, False
