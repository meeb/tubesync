import os
import re
import socket
import sys
from datetime import datetime
from hat.syslog import common

# --- Constants & Grammar ---

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
MSG_BODY    = '(?P<msg>.+)'

formats = [
    {'parts': (
        PRI, MONTH, S, DAY, S, HOUR, MINUTE, SECOND,
        HOST_STRICT, S, NOT_HOST, TAG_PID, S,
        MSG_BODY, EOL,
    )},
    {'parts': (
        PRI,
        '(?P<app_name>.+?):', S, PID, S,
        MSG_BODY, EOL,
    )},
]
for _dict in formats:
    _dict['string'] = ''.join(_dict['parts'])
    _dict['regex'] = re.compile(_dict['string'])


def msg_from_busybox_str(msg_str: str) -> common.Msg:
    """Strict BusyBox RFC 3164 parser. Raises ValueError on any deviation."""
    now = datetime.now()

    for _dict in formats:
        _format_ = _dict['regex']
        match_obj = _format_.fullmatch(msg_str)
        if match_obj is not None:
            break

    if match_obj is None:
        raise ValueError(f'BusyBox (RFC 3164) grammar mismatch: {msg_str}')

    m = match_obj.groupdict()

    if 'month' in m:
        day_val = m['day'].replace(' ', '0')
        time_str = f'{m["hour"]}:{m["minute"]}:{m["second"]}'
        ts_str = f'{now.year} {m["month"]} {day_val} {time_str}'

        dt = datetime.strptime(ts_str, '%Y %b %d %H:%M:%S')
        if now < dt:
            dt = dt.replace(year=now.year - 1)
    else:
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
            elif 4_194_304 < _pid:
                raise ValueError('too high')
        except Exception as e:
            raise ValueError(f'BusyBox (RFC 3164) invalid process ID: {e}')

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


# --- Test Suite ---

def run_test_suite():
    h = KNOWN_HOSTNAME
    p = f'[{os.getpid()}]'
    negative_cases = [
        f'<13>May  1 23:59:59 {h} logger[a]: Invalid pid',
        f'<13>May  1 23:59:59 {h} logger[0]: Invalid pid',
        f'<13>May  1 23:59:59 {h} logger[4194305]: Invalid pid',
        f'<13>May 11 24:60:60 {h} logger: Invalid time',
        f'<192>May  1 00:00:00 {h} logger: Priority 192',
        #f'<13>Feb 29 00:00:00 {h} logger: Non-leap year', # flaky during leap years
        f'<13>May  1 00:00:00 {h}extra logger: Host mismatch',
        f'<13>Jun 32 00:00:00 {h} logger: Invalid day',
        f'<13>July  1 00:00:00 {h} logger: Invalid month',
    ]
    test_cases = [
        f'<13>May  1 23:59:59 {h} logger[4194304]: Valid pid',
        '<13>Apr 30 23:17:18 logger: testing',
        f'<13>May  1 01:31:45 {h} logger{p}: with args: -i -t logger --rfc3164',
        f'<13>May  1 01:34:51 logger{p}: with args: -i -t logger',
        '<13>May  1 01:38:28 logger: with args: -t logger',
        f'<31>May  1 01:54:23 logger.as.root{p}: with args: -i -t logger.as.root -p daemon.debug',
        f'<191>May  1 01:56:59 logger.as.root{p}: with args: -i -t logger.as.root -p local7.debug',
        f'<0>May  1 02:01:08 :[]{p}: with args: -i -t :[] -p kern.emerg',
        f'<0>May  1 02:01:08 :[]: with args: -t :[] -p kern.emerg',
        f'<128>May  1 02:07:20 Already.running.as.root.in.a.container:[]{p}: with args: -i -t Already.running.as.root.in.a.container:[] -p local0.emerg',
        '<13>May  1 01:47:46 root: without any args',
        b'<150>gunicorn.gunicorn.access: [113427] 127.0.0.1 - - [02/May/2026:09:03:03 +0000] "GET /healthcheck HTTP/1.1" 200 2 "-" "healthcheck"\n'.decode(),
    ]

    print(f'--- Running Full Test Suite (Hostname: {h}) ---')
    for i, test in enumerate(test_cases, 1):
        try:
            res = msg_from_busybox_str(test)
        except Exception as e:
            print(f'[FAIL] Case {i}: {e}')
        else:
            print(f'[PASS] Case {i}: APP={res.app_name} PID={res.procid}')

    print('\n--- Running Negative Tests ---')
    for i, test in enumerate(negative_cases, 1):
        try:
            msg_from_busybox_str(test)
        except ValueError:
            print(f'[PASS] Neg Case {i} correctly rejected')
        except Exception as e:
            print(f'[FAIL] Neg Case {i}: {e}')
        else:
            print(f'[FAIL] Neg Case {i} accepted invalid string: {test}')


if '__main__' == __name__:
    run_test_suite()
