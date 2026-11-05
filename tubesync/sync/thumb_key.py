import os
from pathlib import Path

from django.conf import settings
from django.db.models.fields.files import ImageFieldFile


def media_thumb_key_link_relpath(key):
    text = str(key)
    return Path('thumbs') / 'key' / text[:2] / text


def _safe_key(key):
    text = str(key or '').strip()
    if not text or text in {'.', '..'}:
        return None
    if '/' in text or '\\' in text or '\0' in text:
        return None
    return text


def _link_path(media):
    key = _safe_key(getattr(media, 'key', ''))
    if key is None:
        return None
    return Path(settings.MEDIA_ROOT) / media_thumb_key_link_relpath(key)


def _thumb_file(media):
    thumb = getattr(media, 'thumb', None)
    if not thumb:
        return None
    try:
        path = Path(thumb.path)
    except (ValueError, OSError):
        return None
    if path.is_file():
        return path
    return None


def remove_media_thumb_key_symlink(media):
    link = _link_path(media)
    if link is not None and link.is_symlink():
        link.unlink()


def sync_media_thumb_key_symlink(media):
    link = _link_path(media)
    if link is None:
        return
    target = _thumb_file(media)
    if target is None:
        remove_media_thumb_key_symlink(media)
        return
    relative = os.path.relpath(target, start=link.parent)
    if link.is_symlink():
        try:
            current = os.readlink(link)
        except OSError:
            current = None
        if current == relative:
            return
        link.unlink()
    elif link.exists():
        return
    link.parent.mkdir(parents=True, exist_ok=True)
    try:
        link.symlink_to(relative)
    except FileExistsError:
        if not (link.is_symlink() and os.readlink(link) == relative):
            raise


class MediaThumbFieldFile(ImageFieldFile):
    def delete(self, save=True):
        super().delete(save=save)
        remove_media_thumb_key_symlink(self.instance)
