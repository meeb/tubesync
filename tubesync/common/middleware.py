from django.conf import settings
from django.forms import BaseForm
from basicauth.middleware import BasicAuthMiddleware as BaseBasicAuthMiddleware


class MaterializeDefaultFieldsMiddleware:
    """
    Adds 'browser-default' CSS attribute class to all form fields in template responses.
    """

    def __init__(self, get_response: callable) -> None:
        """
        Initializes the middleware with the get_response callable.

        :param get_response: The callable to get the response from.
        """
        self.get_response = get_response

    def __call__(self, request: object) -> object:
        """
        Calls the get_response callable with the request.

        :param request: The request object.
        :return: The response object.
        """
        response = self.get_response(request)
        return response

    def process_template_response(self, request: object, response: object) -> object:
        """
        Processes the template response by adding the 'browser-default' class to form fields.

        :param request: The request object.
        :param response: The response object.
        :return: The processed response object.
        """
        # Get the context data from the response
        context_data = getattr(response, 'context_data', {})
        
        # Iterate over the context data items
        for key, value in context_data.items():
            # Check if the value is an instance of BaseForm
            if isinstance(value, BaseForm):
                # Iterate over the form fields
                for field_name, field in value.fields.items():
                    # Update the widget attributes with the 'browser-default' class
                    field.widget.attrs.update({'class': 'browser-default'})
        
        # Return the processed response
        return response


class BasicAuthMiddleware(BaseBasicAuthMiddleware):
    """
    Custom BasicAuthMiddleware that bypasses authentication for certain URIs.
    """

    def process_request(self, request: object) -> object:
        """
        Processes the request by checking if it should bypass authentication.

        :param request: The request object.
        :return: None if authentication should be bypassed, otherwise the result of the parent's process_request method.
        """
        # Get the bypass URIs from the settings
        bypass_uris = getattr(settings, 'BASICAUTH_ALWAYS_ALLOW_URIS', [])
        
        # Check if the request path is in the bypass URIs
        if request.path in bypass_uris:
            # If it is, return None to bypass authentication
            return None
        
        # If not, call the parent's process_request method
        return super().process_request(request)