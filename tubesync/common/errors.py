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


class NoThumbnailException(Exception):
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


class BgTaskWorkerError(Exception):
    # Raised when the worker process is not in a normal working state.
    pass


class HueyConsumerError(Exception):
    # Raised when the consumer process is not in a normal working state.
    pass


class FormatUnavailableError(Exception):
    def __init__(self, *args, exc=None, format=None, **kwargs):
        self.exc = exc
        self.format = format
        super().__init__(*args, **kwargs)


class QuerySetEmptyError(Exception):
    # Raised when a primary key was missing when iterating a query set.
    def __init__(self, *args, exc=None, key=None, **kwargs):
        self.exc = exc
        self.key = key
        super().__init__(*args, **kwargs)

