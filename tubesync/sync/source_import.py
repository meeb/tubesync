'''
    Shared core for bulk-importing Source objects.

    Both the HTTP API (`sync/views/api.py`) and the management command
    (`sync/management/commands/import-sources.py`) delegate here so the two
    entry points behave identically.

    Nothing in this module touches the network: it only validates input and
    creates rows. Reachability of a source key is discovered later, the first
    time `index_source` runs (matching the behaviour of the HTML forms and the
    plain ORM path).
'''

from dataclasses import dataclass, field
from django.conf import settings
from django.core.exceptions import SuspiciousFileOperation, ValidationError
from django.db import IntegrityError, transaction
from django.utils.text import slugify
from django.utils._os import safe_join
from django.utils.translation import gettext_lazy as _

from common.models import TaskHistory

from .choices import (
    Val,
    AudioTrack,
    CapChoices,
    Fallback,
    IndexSchedule,
    SourceResolution,
    SponsorBlock_Category,
    YouTube_AudioCodec,
    YouTube_SourceType,
    YouTube_VideoCodec,
    youtube_validation_urls,
)
from .models import Source
from .utils import validate_url


# Hard ceiling on how many items one import call accepts. The HTTP layer turns
# a breach of this into a 400.
MAX_IMPORT_ITEMS = 500

# Item keys that are helpers for the caller and never map onto a Source field.
CALLER_ONLY_KEYS = frozenset({'url', 'title'})

# Concrete Source fields that must never be set from an import item.
#   uuid / created / last_crawl / has_failed -> managed by the ORM and tasks
#   filter_text                              -> overloaded internally as a
#                                               per-source delete marker
#                                               (see sync/signals.py::source_pre_delete)
DENY_FIELDS = frozenset({'uuid', 'created', 'last_crawl', 'has_failed', 'filter_text'})

# Fields validated explicitly against their model `choices` so the error message
# can list the accepted values.
CHOICE_FIELDS = {
    'source_type': YouTube_SourceType,
    'index_schedule': IndexSchedule,
    'download_cap': CapChoices,
    'source_resolution': SourceResolution,
    'source_vcodec': YouTube_VideoCodec,
    'source_acodec': YouTube_AudioCodec,
    'audio_track': AudioTrack,
    'fallback': Fallback,
}

# full_clean() cannot validate these on an unsaved instance.
_FULL_CLEAN_EXCLUDE = ['uuid', 'created', 'last_crawl', 'has_failed']


@dataclass
class ImportItemResult:
    status: str                 # "created" | "exists" | "error"
    key: str | None = None
    uuid: str | None = None
    detail: str | None = None
    input: dict | None = None   # echoed back only on error

    def as_dict(self):
        d = {'status': self.status}
        if self.key is not None:
            d['key'] = self.key
        if self.uuid is not None:
            d['uuid'] = self.uuid
        if self.detail is not None:
            d['detail'] = self.detail
        if self.input is not None:
            d['input'] = self.input
        return d


@dataclass
class ImportReport:
    created: int = 0
    exists: int = 0
    errors: int = 0
    results: list = field(default_factory=list)
    dry_run: bool = False

    def as_dict(self):
        return {
            'created': self.created,
            'exists': self.exists,
            'errors': self.errors,
            'dry_run': self.dry_run,
            'results': [r.as_dict() for r in self.results],
        }


def _concrete_source_field_names():
    names = set()
    for f in Source._meta.get_fields():
        if getattr(f, 'concrete', False) and not f.auto_created:
            names.add(f.name)
    return names


def _boolean_source_field_names():
    from django.db import models
    return {
        f.name for f in Source._meta.get_fields()
        if isinstance(f, models.BooleanField)
    }


def _integer_source_field_names():
    from django.db import models
    return {
        f.name for f in Source._meta.get_fields()
        if isinstance(f, models.IntegerField) and not isinstance(f, models.BooleanField)
    }


def _resolve_key_and_type(item):
    '''
        Returns (key, source_type). Mirrors
        sync/views/sources.py::ValidateSourceView.form_valid for the `url` case.
    '''
    url = item.get('url')
    if url:
        for source_type in YouTube_SourceType.values:
            validation_url = youtube_validation_urls.get(source_type)
            try:
                key = validate_url(url, validation_url)
            except ValidationError:
                continue
            if key:
                return str(key).strip(), source_type
        raise ValidationError(
            _('URL "%(url)s" does not match any supported YouTube source format')
            % {'url': url}
        )

    key = item.get('key')
    source_type = item.get('source_type')
    if key and source_type:
        if source_type not in YouTube_SourceType.values:
            raise ValidationError(
                _("invalid 'source_type' %(got)r, must be one of %(valid)s")
                % {'got': source_type, 'valid': sorted(YouTube_SourceType.values)}
            )
        return str(key).strip(), source_type

    raise ValidationError(_("provide either 'url' or 'key'+'source_type'"))


def _derive_name(item, key):
    name = item.get('name') or item.get('title') or key
    name = str(name).strip()
    max_length = Source._meta.get_field('name').max_length
    return name[:max_length]


def _derive_directory(item, name):
    directory = item.get('directory')
    if directory:
        directory = str(directory).strip()
    else:
        # Same call Source.slugname uses.
        directory = slugify(name.replace('_', '-').replace('&', 'and').replace('+', 'and'))
    max_length = Source._meta.get_field('directory').max_length
    directory = directory[:max_length]
    if not directory:
        raise ValidationError(_("could not derive a 'directory' from the name; set one explicitly"))
    # Path-traversal guard. The ORM path skips the check that
    # sync/views/sources.py::EditSourceMixin.form_valid applies, so do it here.
    if directory.startswith('/') or directory.startswith('\\'):
        raise ValidationError(_("'directory' must be relative, not an absolute path"))
    if '..' in directory.replace('\\', '/').split('/'):
        raise ValidationError(_("'directory' must not contain '..'"))
    try:
        safe_join(str(settings.DOWNLOAD_ROOT), directory + '/.virt')
    except SuspiciousFileOperation as e:
        raise ValidationError(
            _("'directory' resolves outside of the downloads root (%(root)s)")
            % {'root': settings.DOWNLOAD_ROOT}
        ) from e
    return directory


def _clean_bool(name, value):
    if not isinstance(value, bool):
        raise ValidationError(
            _("field '%(name)s' must be a JSON boolean (true/false), got %(got)r")
            % {'name': name, 'got': value}
        )
    return value


def _clean_int_choice(name, value, choices_enum):
    if isinstance(value, bool):
        raise ValidationError(_("field '%(name)s' must be a number") % {'name': name})
    try:
        value = int(value)
    except (TypeError, ValueError) as e:
        raise ValidationError(_("field '%(name)s' must be a number") % {'name': name}) from e
    valid = [c[0] for c in choices_enum.choices]
    if value not in valid:
        raise ValidationError(
            _("invalid %(name)s %(got)r, must be one of %(valid)s")
            % {'name': name, 'got': value, 'valid': valid}
        )
    return value


def _clean_str_choice(name, value, choices_enum):
    value = str(value)
    valid = [c[0] for c in choices_enum.choices]
    if value not in valid:
        raise ValidationError(
            _("invalid %(name)s %(got)r, must be one of %(valid)s")
            % {'name': name, 'got': value, 'valid': valid}
        )
    return value


def _clean_sponsorblock_categories(value):
    if isinstance(value, str):
        parts = [p.strip() for p in value.split(',') if p.strip()]
    elif isinstance(value, (list, tuple)):
        parts = [str(p).strip() for p in value]
    else:
        raise ValidationError(
            _("'sponsorblock_categories' must be a list or a comma-separated string")
        )
    valid = {c[0] for c in SponsorBlock_Category.choices} | {'all'}
    bad = [p for p in parts if p not in valid]
    if bad:
        raise ValidationError(
            _("invalid sponsorblock_categories %(bad)s, valid values: %(valid)s")
            % {'bad': bad, 'valid': sorted(valid)}
        )
    return parts


def build_source_kwargs(item):
    '''
        Turn one import item into validated Source(**kwargs) keyword arguments.
        Raises django.core.exceptions.ValidationError with a human message on
        any problem. Does not instantiate or save.
    '''
    if not isinstance(item, dict):
        raise ValidationError(_('each source item must be a JSON object'))

    allow = _concrete_source_field_names() - DENY_FIELDS
    booleans = _boolean_source_field_names()
    integers = _integer_source_field_names()

    # Reject unknown / denied keys early.
    for k in item:
        if k in CALLER_ONLY_KEYS:
            continue
        if k in DENY_FIELDS:
            raise ValidationError(_("field '%(k)s' may not be set via import") % {'k': k})
        if k not in allow:
            raise ValidationError(_("unknown field '%(k)s'") % {'k': k})

    key, source_type = _resolve_key_and_type(item)
    if not key:
        raise ValidationError(_("'key' must not be empty"))
    key_max = Source._meta.get_field('key').max_length
    if len(key) > key_max:
        raise ValidationError(
            _("'key' is longer than %(max)d characters") % {'max': key_max}
        )

    name = _derive_name(item, key)
    directory = _derive_directory(item, name)

    kwargs = {
        'key': key,
        'source_type': source_type,
        'name': name,
        'directory': directory,
    }

    for k, v in item.items():
        if k in CALLER_ONLY_KEYS or k in ('key', 'source_type', 'name', 'directory'):
            continue
        if k in CHOICE_FIELDS:
            enum = CHOICE_FIELDS[k]
            if k in integers:
                kwargs[k] = _clean_int_choice(k, v, enum)
            else:
                kwargs[k] = _clean_str_choice(k, v, enum)
        elif k == 'sponsorblock_categories':
            kwargs[k] = _clean_sponsorblock_categories(v)
        elif k in booleans:
            kwargs[k] = _clean_bool(k, v)
        elif k in integers:
            if isinstance(v, bool) or (v is not None and not _is_intish(v)):
                raise ValidationError(_("field '%(k)s' must be a number") % {'k': k})
            kwargs[k] = None if v is None else int(v)
        else:
            # Remaining fields (e.g. media_format, sub_langs) pass through as
            # given; the model's own validators run in import_sources().
            kwargs[k] = v

    return kwargs


def _is_intish(v):
    if isinstance(v, int):
        return True
    try:
        int(str(v))
        return True
    except (TypeError, ValueError):
        return False


def _apply_activate(kwargs, activate):
    if activate is False:
        kwargs['index_schedule'] = Val(IndexSchedule.NEVER)
        kwargs['download_media'] = False
    elif activate is True:
        kwargs.setdefault('index_schedule', Val(IndexSchedule.EVERY_24_HOURS))
        kwargs.setdefault('download_media', True)
    # activate is None -> leave whatever build_source_kwargs produced


def _schedule_index_tasks(source, *, extra_delay=0):
    from .tasks import check_source_directory_exists, index_source, save_all_media_for_source
    check_source_directory_exists(str(source.pk))
    if source.is_active:
        TaskHistory.schedule(
            index_source,
            str(source.pk),
            delay=600 + extra_delay,
            vn_fmt=_('Index media from source "{}"'),
            vn_args=(source.name,),
        )
    TaskHistory.schedule(
        save_all_media_for_source,
        str(source.pk),
        remove_duplicates=True,
        vn_fmt=_('Checking all media for "{}"'),
        vn_args=(source.name,),
    )


def import_sources(items, *, activate=None, defer_indexing=False, dry_run=False):
    '''
        Create Source rows from an iterable of import items.

        activate:
            True  -> force the source active (index_schedule + download_media
                     default on) unless the item set them
            False -> force the source inactive (index_schedule = 0,
                     download_media = False); no index task is scheduled
            None  -> leave item values / model defaults untouched
        defer_indexing:
            True  -> bulk_create (bypasses signals), then schedule staggered
                     index tasks manually. For very large imports only.
        dry_run:
            True  -> roll everything back; the report is still populated and
                     per-item IntegrityError / ValidationError still surface.
    '''
    items = list(items)
    if len(items) > MAX_IMPORT_ITEMS:
        raise ValidationError(
            _('too many items (%(n)d), the limit is %(max)d per import')
            % {'n': len(items), 'max': MAX_IMPORT_ITEMS}
        )

    report = ImportReport(dry_run=bool(dry_run))
    deferred_new = []   # (Source instance, extra_delay) for defer_indexing

    with transaction.atomic():
        for index, item in enumerate(items):
            try:
                kwargs = build_source_kwargs(item)
                _apply_activate(kwargs, activate)

                existing = Source.objects.filter(key=kwargs['key']).first()
                if existing is not None:
                    report.results.append(ImportItemResult(
                        'exists', key=kwargs['key'], uuid=str(existing.uuid),
                    ))
                    report.exists += 1
                    continue

                candidate = Source(**kwargs)
                candidate.full_clean(exclude=_FULL_CLEAN_EXCLUDE)

                if defer_indexing:
                    deferred_new.append((candidate, index * 30))
                    report.results.append(ImportItemResult(
                        'created', key=kwargs['key'], uuid=str(candidate.uuid),
                    ))
                    report.created += 1
                    continue

                with transaction.atomic():   # savepoint
                    obj, created = Source.objects.get_or_create(
                        key=kwargs['key'],
                        defaults={k: v for k, v in kwargs.items() if k != 'key'},
                    )
                if created:
                    report.results.append(ImportItemResult(
                        'created', key=kwargs['key'], uuid=str(obj.uuid),
                    ))
                    report.created += 1
                else:
                    report.results.append(ImportItemResult(
                        'exists', key=kwargs['key'], uuid=str(obj.uuid),
                    ))
                    report.exists += 1
            except (ValidationError, IntegrityError) as e:
                report.results.append(ImportItemResult(
                    'error', detail=_validation_message(e), input=item,
                ))
                report.errors += 1

        if defer_indexing and deferred_new:
            _bulk_create_deferred(deferred_new, report)

        if dry_run:
            transaction.set_rollback(True)

    return report


def _bulk_create_deferred(deferred_new, report):
    '''
        bulk_create the candidates from the defer_indexing path, then schedule
        their index tasks. On an IntegrityError (e.g. two items in the same
        batch collide on name/directory) fall back to saving one at a time so
        the offender becomes a per-item error instead of failing the batch.

        Note: report counters were already incremented as "created" while
        iterating; adjust them here when a row turns out to be an error.
    '''
    objs = [c for c, _delay in deferred_new]
    try:
        with transaction.atomic():   # savepoint
            Source.objects.bulk_create(objs, batch_size=100)
    except IntegrityError:
        for candidate, extra_delay in deferred_new:
            try:
                with transaction.atomic():
                    candidate.save(force_insert=True)
            except (IntegrityError, ValidationError) as e:
                report.created -= 1
                report.errors += 1
                for r in report.results:
                    if r.status == 'created' and r.uuid == str(candidate.uuid):
                        r.status = 'error'
                        r.detail = _validation_message(e)
                        r.uuid = None
                        break
                continue
            _schedule_index_tasks(candidate, extra_delay=extra_delay)
        return
    for candidate, extra_delay in deferred_new:
        _schedule_index_tasks(candidate, extra_delay=extra_delay)


def _validation_message(exc):
    if isinstance(exc, ValidationError):
        try:
            if hasattr(exc, 'message_dict'):
                parts = []
                for f_name, msgs in exc.message_dict.items():
                    joined = '; '.join(str(m) for m in msgs)
                    parts.append(joined if f_name == '__all__' else f'{f_name}: {joined}')
                return ' / '.join(parts)
            return '; '.join(str(m) for m in exc.messages)
        except Exception:
            return str(exc)
    return str(exc)
