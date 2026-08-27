import re
import socket
from datetime import datetime
from hat.syslog import common


KNOWN_HOSTNAME = socket.gethostname()
RE_HOSTNAME = re.escape(KNOWN_HOSTNAME)

VALID_MONTHS = (
    'Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun',
    'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec',
)

S           = ' '
EOL         = r'\r?\n?'
PRI         = '<(?P<prival>0|[1-9][0-9]?|1[0-8][0-9]|19[0-1])>'
MONTH       = f'(?P<month>{"|".join(map(re.escape, VALID_MONTHS))})'
DAY         = f'(?P<day>{S}[1-9]|[1-2][0-9]|3[0-1])'
HOUR        = '(?P<hour>[0-1][0-9]|2[0-3])'
MINUTE      = ':(?P<minute>[0-5][0-9])'
SECOND      = ':(?P<second>[0-5][0-9])'
HOST_STRICT = f'(?:{S}{RE_HOSTNAME}(?={S}))?'
NOT_HOST    = f'(?!{RE_HOSTNAME})'
PID         = r'(?:[\[](?P<procid>[0-9]+)[\]])'
TAG_PID     = f'(?P<app_name>.+?){PID}?:'
MSG_BODY    = '(?P<msg>(?s:.)+)'

formats = [
    # Generic with optional hostname and PID:
    # Begins with a partial (5-15) ctime() date string.
    # Does not accept hostnames other than this one.
    # Remote logs that do not include a hostname are accepted.
    {'parts': (
        PRI, MONTH, S, DAY, S, HOUR, MINUTE, SECOND,
        HOST_STRICT, S, NOT_HOST, TAG_PID, S,
        MSG_BODY, EOL,
    )},
    # Support for `gunicorn` logs:
    # No date or hostname.
    # Also, non-standard PID placement.
    {'parts': (
        PRI,
        '(?P<app_name>.+?):', S, PID, S,
        MSG_BODY, EOL,
    )},
]
for _dict in formats:
    _dict['regex'] = re.compile(''.join(_dict['parts']))


def msg_from_rfc3164_str(msg_str: str) -> common.Msg:
    """RFC 3164 parser. Raises ValueError on any deviation."""
    now = datetime.now()

    for _dict in formats:
        _format_ = _dict['regex']
        match_obj = _format_.fullmatch(msg_str)
        if match_obj is not None:
            break

    if match_obj is None:
        raise ValueError(f'No formats matched: {msg_str.encode()!r}')

    m = match_obj.groupdict()

    if 'month' in m:
        day_val = m['day'].replace(' ', '0')
        time_str = f'{m["hour"]}:{m["minute"]}:{m["second"]}'
        ts_str = f'{now.year} {m["month"]} {day_val} {time_str}'

        dt = datetime.strptime(ts_str, '%Y %b %d %H:%M:%S')
        # The skew should be zero when logging from the same host.
        if now < dt:
            dt = dt.replace(year=now.year - 1)
    else:
        # The matched format did not include the date and time.
        dt = now

    prival = int(str(m['prival']), 10)
    procid = m.get('procid', None)
    tag_str = m['app_name']
    tag_ends_with_brackets = (
        ']' == tag_str[-1] and
        tag_str.rsplit('[')[-1][:-1] and
        tag_str[-1] != tag_str.rsplit('[')[-1][:-1]
    )
    if procid is None and tag_ends_with_brackets:
        procid = tag_str.rsplit('[')[-1][:-1]
    if procid is not None:
        try:
            _pid = int(str(procid), 10)
            if 0 >= _pid:
                raise ValueError('too low')
            elif 4_194_304 < _pid: # read from /proc instead?
                raise ValueError('too high')
        except Exception as e:
            raise ValueError(f'Invalid process ID: {e}')

    return common.Msg(
        facility=common.Facility(prival // 8),
        severity=common.Severity(prival % 8),
        version=None,
        timestamp=dt.timestamp(),
        hostname=KNOWN_HOSTNAME,
        app_name=m['app_name'],
        procid=m.get('procid', None),
        msgid=None,
        data=None,
        msg=m['msg']
    )
