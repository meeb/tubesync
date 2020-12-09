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


class DownloadFailedException(Exception):
    '''
        Raised when a downloaded media file is expected to be present, but doesn't
        exist.
    '''
    pass
