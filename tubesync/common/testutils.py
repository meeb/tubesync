import logging

def prevent_request_warnings(original_function: callable) -> callable:
    """
    Suppresses errors from views that raise legitimate errors, such as testing
    that a page does indeed 404 or a non-authenticated user cannot access a
    page requiring authentication which raises a 403.

    Args:
        original_function: The function to be wrapped.

    Returns:
        A new function that suppresses request warnings.
    """
    def new_function(*args: tuple, **kwargs: dict) -> None:
        # Get the current logger and store its level
        logger = logging.getLogger('django.request')
        previous_logging_level = logger.getEffectiveLevel()

        # Temporarily set the logger level to CRITICAL to suppress warnings
        logger.setLevel(logging.CRITICAL)

        try:
            # Call the original function with the provided arguments
            original_function(*args, **kwargs)
        finally:
            # Restore the original logger level
            logger.setLevel(previous_logging_level)

    return new_function