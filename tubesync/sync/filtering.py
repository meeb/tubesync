"""
    All the logic for filtering media from channels to work out if we should skip downloading it or not
"""

from common.logger import log
from .models import Media
from datetime import datetime
from django.utils import timezone
from .overrides.custom_filter import filter_custom


# Check the filter conditions for instance, return is if the Skip property has changed so we can do other things
def filter_media(instance: Media):
    unskip = True
    # Assume we aren't skipping it, if any of these conditions are true, we skip it
    skip = False

    # Check if it's published
    is_published = not filter_published(instance)
    if not skip and not is_published:
        skip = True

    # Check if older than max_cap_age, skip
    video_too_old = is_published and filter_max_cap(instance)
    if not skip and video_too_old:
        skip = True

    # Check if older than source_cutoff
    download_kept = not filter_source_cutoff(instance)
    if not skip and not download_kept:
        skip = True

    # Check if we have filter_text and filter text matches
    if not skip and filter_filter_text(instance):
        skip = True
        unskip = False

    # Check if the video is longer than the max, or shorter than the min
    if not skip and filter_duration(instance):
        skip = True
        unskip = False

    # If we aren't already skipping the file, call our custom function that can be overridden
    if not skip and filter_custom(instance):
        log.info(f"Media: {instance.source} / {instance} has been skipped by Custom Filter")
        skip = True
        unskip = False

    keep_newly_published_video = (
        is_published and download_kept and
        not (instance.downloaded or video_too_old)
    )

    # Check if skipping
    if not keep_newly_published_video:
        unskip = False
    if instance.skip != skip:
        was_skipped = instance.skip
        instance.skip = skip

        if was_skipped and not (unskip or skip):
            instance.skip = True

        if instance.skip != was_skipped:
            log.info(
                f"Media: {instance.source} / {instance} has changed skip setting to {instance.skip}"
            )
            return True

    return False


def filter_published(instance: Media):
    # Check if the instance is not published, we have to skip then
    if not isinstance(instance.published, datetime):
        log.info(
            f"Media: {instance.source} / {instance} has no published date "
            f"set, marking to be skipped"
        )
        return True
    return False


# Return True if we are to skip downloading it based on video title not matching the filter text
def filter_filter_text(instance: Media):
    filter_text = instance.source.filter_text.strip()

    if not filter_text:
        return False

    if not instance.source.filter_text_invert:
        # We match the filter text, so don't skip downloading this
        if instance.source.is_regex_match(instance.title):
            log.info(
                f"Media: {instance.source} / {instance} has a valid "
                f"title filter, not marking to be skipped"
            )
            return False

        log.info(
            f"Media: {instance.source} / {instance} doesn't match "
            f"title filter, marking to be skipped"
        )

        return True

    if instance.source.is_regex_match(instance.title):
        log.info(
            f"Media: {instance.source} / {instance} matches inverted "
            f"title filter, marking to be skipped"
        )

        return True

    log.info(
        f"Media: {instance.source} / {instance} does not match the inverted "
        f"title filter, not marking to be skipped"
    )
    return False


def filter_max_cap(instance: Media):

    if instance.published is None:
        log.debug(
            f"Media: {instance.source} / {instance} has no published date "
            f"set (likely not downloaded metadata) so not filtering based on "
            f"publish date"
        )
        return False

    max_cap_age = instance.source.download_cap_date
    if not max_cap_age:
        log.debug(
            f"Media: {instance.source} / {instance} has not max_cap_age "
            f"so not skipping based on max_cap_age"
        )
        return False

    if instance.published <= max_cap_age:
        # log new media instances, not every media instance every time
        if not instance.skip:
            log.info(
                f"Media: {instance.source} / {instance} is too old for "
                f"the download cap date, marking to be skipped"
            )
        return True

    return False


# If the source has a cut-off, check the download date is within the allowed delta
def filter_source_cutoff(instance: Media):
    if instance.source.delete_old_media and instance.source.days_to_keep_date:
        if not instance.downloaded or not isinstance(instance.download_date, datetime):
            return False

        days_to_keep_age = instance.source.days_to_keep_date
        if instance.download_date < days_to_keep_age:
            # Media has expired, skip it
            log.info(
                f"Media: {instance.source} / {instance} is older than "
                f"{instance.source.days_to_keep} days, skipping"
            )
            return True

    return False


# Check if we skip based on duration (min/max)
def filter_duration(instance: Media):
    if not instance.source.filter_seconds:
        return False

    duration = instance.duration
    if not duration:
        # Attempt fallback to slower metadata field, this adds significant time, new media won't need this
        # Tests show fetching instance.duration can take as long as the rest of the filtering
        if instance.metadata_duration:
            duration = instance.metadata_duration
            instance.duration = duration
            instance.save()
        else:
            log.info(
                f"Media: {instance.source} / {instance} has no duration stored, not skipping"
            )
            return False

    duration_limit = instance.source.filter_seconds
    if instance.source.filter_seconds_min and duration < duration_limit:
        # Filter out videos that are shorter than the minimum
        log.info(
            f"Media: {instance.source} / {instance} is shorter ({duration}) than "
            f"the minimum duration ({duration_limit}), skipping"
        )
        return True

    if not instance.source.filter_seconds_min and duration > duration_limit:
        # Filter out videos that are greater than the maximum
        log.info(
            f"Media: {instance.source} / {instance} is longer ({duration}) than "
            f"the maximum duration ({duration_limit}), skipping"
        )
        return True

    return False
