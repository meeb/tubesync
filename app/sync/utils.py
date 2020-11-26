import re
from urllib.parse import urlsplit, parse_qs
from django.forms import ValidationError


def validate_url(url, validator):
    '''
        Validate a URL against a dict of validation requirements. Returns an extracted
        part of the URL if the URL is valid, if invalid raises a ValidationError.
    '''
    valid_scheme, valid_netloc, valid_path, valid_query, extract_parts = (
        validator['scheme'], validator['domain'], validator['path_regex'],
        validator['qs_args'], validator['extract_key'])
    url_parts = urlsplit(str(url).strip())
    url_scheme = str(url_parts.scheme).strip().lower()
    if url_scheme != valid_scheme:
        raise ValidationError(f'scheme "{url_scheme}" must be "{valid_scheme}"')
    url_netloc = str(url_parts.netloc).strip().lower()
    if url_netloc != valid_netloc:
        raise ValidationError(f'domain "{url_netloc}" must be "{valid_netloc}"')
    url_path = str(url_parts.path).strip()
    matches = re.findall(valid_path, url_path)
    if not matches:
        raise ValidationError(f'path "{url_path}" must match "{valid_path}"')
    url_query = str(url_parts.query).strip()
    url_query_parts = parse_qs(url_query)
    for required_query in valid_query:
        if required_query not in url_query_parts:
            raise ValidationError(f'query string "{url_query}" must '
                                  f'contain the parameter "{required_query}"')
    extract_from, extract_param = extract_parts
    extract_value = ''
    if extract_from == 'path_regex':
        try:
            submatches = matches[0]
            try:
                extract_value = submatches[extract_param]
            except IndexError:
                pass
        except IndexError:
            pass
    elif extract_from == 'qs_args':
        extract_value = url_query_parts[extract_param][0]
    return extract_value
