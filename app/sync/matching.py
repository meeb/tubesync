'''
    Match functions take a single Media object instance as its only argument and return
    two boolean values. The first value is if the match was exact or "best fit", the
    second argument is the ID of the format that was matched.
'''


from django.conf import settings


min_height = getattr(settings, 'VIDEO_HEIGHT_CUTOFF', 360)
fallback_hd_cutoff = getattr(settings, 'VIDEO_HEIGHT_IS_HD', 500)


def get_best_combined_format(media):
    '''
        Attempts to see if there is a single, combined audio and video format that
        exactly matches the source requirements. This is used over separate audio
        and video formats if possible. Combined formats are the easiest to check
        for as they must exactly match the source profile be be valid.
    '''
    for fmt in media.iter_formats():
        # Check height matches
        if media.source.source_resolution.strip().upper() != fmt['format']:
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
        return True, fmt['id']
    return False, False


def get_best_audio_format(media):
    '''
        Finds the best match for the source required audio format. If the source
        has a 'fallback' of fail this can return no match.
    '''
    # Order all audio-only formats by bitrate
    audio_formats = []
    for fmt in media.iter_formats():
        # If the format has a video stream, skip it
        if fmt['vcodec']:
            continue
        audio_formats.append(fmt)
    audio_formats = list(reversed(sorted(audio_formats, key=lambda k: k['abr'])))
    if not audio_formats:
        # Media has no audio formats at all
        return False, False
    # Find the highest bitrate audio format with a matching codec
    for fmt in audio_formats:
        if media.source.source_acodec == fmt['acodec']:
            # Matched!
            return True, fmt['id']
    # No codecs matched
    if media.source.can_fallback:
        # Can fallback, find the next highest bitrate non-matching codec
        return False, audio_formats[0]
    else:
        # Can't fallback
        return False, False


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
    # Filter video-only formats by resolution that matches the source
    video_formats = []
    for fmt in media.iter_formats():
        # If the format has an audio stream, skip it
        if fmt['acodec']:
            continue
        if media.source.source_resolution.strip().upper() == fmt['format']:
            video_formats.append(fmt)
    # Check we matched some streams
    if not video_formats:
        # No streams match the requested resolution, see if we can fallback
        if media.source.can_fallback:
            # Find the next-best format matches by height
            for fmt in media.iter_formats():
                # If the format has an audio stream, skip it
                if fmt['acodec']:
                    continue
                if (fmt['height'] <= media.source.source_resolution_height and 
                    fmt['height'] >= min_height):
                    video_formats.append(fmt)
        else:
            # Can't fallback
            return False, False
    video_formats = list(reversed(sorted(video_formats, key=lambda k: k['height'])))
    print('height', media.source.source_resolution_height)
    print('video_formats', video_formats)
    if not video_formats:
        # Still no matches
        return False, False
    exact_match, best_match = None, None
    # Of our filtered video formats, check for resolution + codec + hdr + fps match
    if media.source.prefer_60fps and media.source.prefer_hdr:
        for fmt in video_formats:
            # Check for an exact match
            if (media.source.source_resolution.strip().upper() == fmt['format'] and
                media.source.source_vcodec == fmt['vcodec'] and 
                fmt['is_hdr'] and
                fmt['is_60fps']):
                # Exact match
                exact_match, best_match = True, fmt
                break
        if media.source.can_fallback:
            if not best_match:
                for fmt in video_formats:
                    # Check for a codec, hdr and fps match but drop the resolution
                    if (media.source.source_vcodec == fmt['vcodec'] and 
                        fmt['is_hdr'] and fmt['is_60fps']):
                        # Close match
                        exact_match, best_match = False, fmt
                        break
            if not best_match:
                for fmt in video_formats:
                    # Check for hdr and fps match but drop the resolution and codec
                    if fmt['is_hdr'] and fmt['is_60fps']:
                        exact_match, best_match = False, fmt
                        break
            if not best_match:
                for fmt in video_formats:
                    # Check for fps match but drop the resolution and codec and hdr
                    if fmt['is_hdr'] and fmt['is_60fps']:
                        exact_match, best_match = False, fmt
                        break
            if not best_match:
                # Match the highest resolution
                exact_match, best_match = False, video_formats[0]
    # Check for resolution + codec + fps match
    if media.source.prefer_60fps and not media.source.prefer_hdr:
        for fmt in video_formats:
            # Check for an exact match
            if (media.source.source_resolution.strip().upper() == fmt['format'] and
                media.source.source_vcodec == fmt['vcodec'] and 
                fmt['is_60fps']):
                # Exact match
                exact_match, best_match = True, fmt
                break
        if media.source.can_fallback:
            if not best_match:
                for fmt in video_formats:
                    # Check for a codec and fps match but drop the resolution
                    if (media.source.source_vcodec == fmt['vcodec'] and 
                        fmt['is_60fps']):
                        exact_match, best_match = False, fmt
                        break
            if not best_match:
                for fmt in video_formats:
                    # Check for an fps match but drop the resolution and codec
                    if fmt['is_60fps']:
                        exact_match, best_match = False, fmt
                        break
            if not best_match:
                # Match the highest resolution
                exact_match, best_match = False, video_formats[0]
    # Check for resolution + codec + hdr
    if media.source.prefer_hdr and not media.source.prefer_60fps:
        for fmt in video_formats:
            # Check for an exact match
            if (media.source.source_resolution.strip().upper() == fmt['format'] and
                media.source.source_vcodec == fmt['vcodec'] and 
                fmt['is_hdr']):
                # Exact match
                exact_match, best_match = True, fmt
                break
        if media.source.can_fallback:
            if not best_match:
                for fmt in video_formats:
                    # Check for a codec and hdr match but drop the resolution
                    if (media.source.source_vcodec == fmt['vcodec'] and 
                        fmt['is_hdr']):
                        exact_match, best_match = True, fmt
                        break
            if not best_match:
                for fmt in video_formats:
                    # Check for an hdr match but drop the resolution and codec
                    if fmt['is_hdr']:
                        exact_match, best_match = False, fmt
                        break
            if not best_match:
                # Match the highest resolution
                exact_match, best_match = False, video_formats[0]
    # check for resolution + codec
    if not media.source.prefer_hdr and not media.source.prefer_60fps:
        for fmt in video_formats:
            # Check for an exact match
            if (media.source.source_resolution.strip().upper() == fmt['format'] and
                media.source.source_vcodec == fmt['vcodec'] and
                not fmt['is_60fps']):
                # Exact match
                exact_match, best_match = True, fmt
                break
        if media.source.can_fallback:
            if not best_match:
                for fmt in video_formats:
                    # Check for a codec match without 60fps and drop the resolution
                    if (media.source.source_vcodec == fmt['vcodec'] and
                        not fmt['is_60fps']):
                        exact_match, best_match = False, fmt
                        break
            if not best_match:
                for fmt in video_formats:
                    # Check for a codec match but drop the resolution
                    if media.source.source_vcodec == fmt['vcodec']:
                        # Close match
                        exact_match, best_match = False, fmt
                        break
            if not best_match:
                # Match the highest resolution
                exact_match, best_match = False, video_formats[0]
    # See if we found a match
    if best_match:
        # Final check to see if the match we found was good enough
        if exact_match:
            return True, best_match['id']
        elif media.source.can_fallback:
            # Allow the fallback if it meets requirements
            if (media.source.fallback == media.source.FALLBACK_NEXT_BEST_HD and
                best_match['height'] >= fallback_hd_cutoff):
                return False, best_match['id']
            elif media.source.fallback == media.source.FALLBACK_NEXT_BEST:
                return False, best_match['id']
    # Nope, failed to find match
    return False, False
