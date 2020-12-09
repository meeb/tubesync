import logging


def prevent_request_warnings(original_function):
    '''
        Suppress errors from views that raise legitimate errors, such as
        testing that a page does indeed 404 or a non-authenticated user
        cannot access page requiring authentication which raises a 403. You
        can wrap test methods with this to drop the error logging down a notch.
    '''
    
    def new_function(*args, **kwargs):
        logger = logging.getLogger('django.request')
        previous_logging_level = logger.getEffectiveLevel()
        logger.setLevel(logging.CRITICAL)
        original_function(*args, **kwargs)
        logger.setLevel(previous_logging_level)

    return new_function
