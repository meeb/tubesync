'''
    All the logic for filtering media from channels to work out if we should skip downloading it or not
'''

from common.logger import log
from .models import Source, Media, MediaServer
from datetime import datetime, timedelta
from django.utils import timezone

# Check the filter conditions for instance, return is if the Skip property has changed so we can do other things
def filter_media(instance: Media):
    # Assume we aren't skipping it, if any of these conditions are true, we skip it
    skip = False

    # Check if it's published
    if filter_published(instance):
        skip = True

    # Check if older than max_cap_age, skip
    if filter_max_cap(instance):
        skip = True

    # Check if older than source_cutoff
    if filter_source_cutoff(instance):
        skip = True

    # Check if we have filter_text and filter text matches, set unskip
    if filter_filter_text(instance):
        skip = True

    # Check if skipping
    if instance.skip != skip:
        instance.skip = skip
        log.warn(f'Media: {instance.source} / {instance} has changed skip setting to {skip}')
        return True

    return False


def filter_published(instance: Media):
    # Check if the instance is not published, we have to skip then
    if not instance.published:
        log.warn(f'Media: {instance.source} / {instance} has no published date '
                 f'set, marking to be skipped')
        return True
    return False


# Return True if we are to skip downloading it based on video title not matching the filter text
def filter_filter_text(instance: Media):
    filter_text = instance.source.filter_text.strip()

    if not filter_text:
        return False

    # We match the filter text, so don't skip downloading this
    if instance.source.is_regex_match(instance.title):
        log.info(f'Media: {instance.source} / {instance} has a valid '
                 f'title filter, marking to be unskipped')
        return False

    log.info(f'Media: {instance.source} / {instance} doesn\'t match '
             f'title filter, marking to be skipped')

    return True


def filter_max_cap(instance: Media):
    max_cap_age = instance.source.download_cap_date
    if not max_cap_age:
        log.debug(f'Media: {instance.source} / {instance} has not max_cap_age '
                  f'so not skipping based on max_cap_age')
        return False

    if instance.published <= max_cap_age:
        log.info(f'Media: {instance.source} / {instance} is too old for '
                 f'the download cap date, marking to be skipped')
        return True

    return False


# If the source has a cut-off, check the upload date is within the allowed delta
def filter_source_cutoff(instance: Media):
    if instance.source.delete_old_media and instance.source.days_to_keep > 0:
        if not isinstance(instance.published, datetime):
            # Media has no known published date or incomplete metadata
            log.warn(f'Media: {instance.source} / {instance} has no published date, skipping')
            return True

        delta = timezone.now() - timedelta(days=instance.source.days_to_keep)
        if instance.published < delta:
            # Media was published after the cutoff date, skip it
            log.warn(f'Media: {instance.source} / {instance} is older than '
                     f'{instance.source.days_to_keep} days, skipping')
            return True

    return False