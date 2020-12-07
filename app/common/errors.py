class NoMediaException(Exception):
    '''
        Raised when a source returns no media to be indexed. Could be an invalid
        playlist name or similar, or the upstream source returned an error.
    '''
    pass
