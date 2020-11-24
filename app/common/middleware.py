from django.forms import BaseForm


class MaterializeDefaultFieldsMiddleware:
    '''
        Adds 'browser-default' CSS attribute class to all form fields.
    '''

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        return response

    def process_template_response(self, request, response):
        for _, v in getattr(response, 'context_data', {}).items():
            if isinstance(v, BaseForm):
                for _, field in v.fields.items():
                    field.widget.attrs.update({'class':'browser-default'})
        return response
