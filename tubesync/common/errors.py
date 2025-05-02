from django.http import Http404


class NoMediaException(Exception):
    '''
        Raised when a source returns no media to be indexed. Could be an invalid
        playlist name or similar, or the upstream source returned an error.
    '''
    pass


class NoFormatException(Exception):
    '''
        Raised when a media item is attempted to be downloaded but it has no valid
        format combination.
    '''
    pass


class NoMetadataException(Exception):
    '''
        Raised when a media item is attempted to be downloaded but it has no valid
        metadata.
    '''
    pass


class NoThumbnailException(Http404):
    '''
        Raised when a thumbnail was not found at the remote URL.
    '''
    pass


class DownloadFailedException(Exception):
    '''
        Raised when a downloaded media file is expected to be present, but doesn't
        exist.
    '''
    pass


class DatabaseConnectionError(Exception):
    '''
        Raised when parsing or initially connecting to a database.
    '''
    pass
