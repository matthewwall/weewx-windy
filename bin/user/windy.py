# Copyright 2019-2026 Matthew Wall
# Updated for the Windy Stations API v2

"""
This is a weewx extension that uploads data to windy.com using the
Windy Stations API v2.

http://windy.com

API reference:

https://stations.windy.com/api-reference

The legacy API (https://stations.windy.com/pws/update/<api_key>) shuts down
at the end of 2026. This version uses the v2 observation endpoint:

GET https://stations.windy.com/api/v2/observation/update

Authentication uses the per-station password, sent as a Bearer token. The
account API key does not work for uploads.

Find the station ID and password under My Stations at stations.windy.com.

Minimal configuration

[StdRESTful]
    [[Windy]]
        station_id = STATION_ID
        password = STATION_PASSWORD

For multiple stations, run one uploader per station. Each station has its own
ID and password.

Windy accepts at most one upload every 5 minutes per station. The default
post_interval is 300 seconds. Observations older than 2 hours are rejected,
so the default stale value is 7200 seconds.
"""

# deal with differences between python 2 and python 3
try:
    # Python 3
    import queue
except ImportError:
    # Python 2
    # noinspection PyUnresolvedReferences
    import Queue as queue

try:
    # Python 3
    from urllib.parse import urlencode
except ImportError:
    # Python 2
    # noinspection PyUnresolvedReferences
    from urllib import urlencode

import json
import logging
import time

import weewx
import weewx.manager
import weewx.restx
import weewx.units
from weeutil.weeutil import to_bool, to_int

try:
    # weewx 5.0 and later
    from weeutil.weeutil import version_compare
except ImportError:
    # weewx 4.x has no version_compare, so compare numeric parts locally
    def version_compare(v1, v2):
        import re

        def parts(v):
            return [int(x) for x in re.findall(r'\d+', v)[:3]]

        a, b = parts(v1), parts(v2)
        return (a > b) - (a < b)

VERSION = "1.0.1"

REQUIRED_WEEWX = "4.1.0"
if version_compare(weewx.__version__, REQUIRED_WEEWX) < 0:
    raise weewx.UnsupportedFeature("weewx %s or greater is required, found %s"
                                   % (REQUIRED_WEEWX, weewx.__version__))

log = logging.getLogger(__name__)


def logdbg(msg):
    log.debug(msg)


def loginf(msg):
    log.info(msg)


def logerr(msg):
    log.error(msg)


class Windy(weewx.restx.StdRESTbase):
    DEFAULT_URL = 'https://stations.windy.com/api/v2/observation/update'

    def __init__(self, engine, cfg_dict):
        super(Windy, self).__init__(engine, cfg_dict)
        loginf("version is %s" % VERSION)

        # Warn users who still have a legacy v1 configuration.
        try:
            windy_cfg = cfg_dict['StdRESTful']['Windy']
        except KeyError:
            windy_cfg = {}
        password_cfg = windy_cfg.get('password', '')
        if 'api_key' in windy_cfg and password_cfg in ('', 'replace_me'):
            logerr("Legacy config found. Windy API v2 needs station_id and "
                   "password from My Stations at stations.windy.com. "
                   "The account api_key does not work for uploads.")

        site_dict = weewx.restx.get_site_dict(cfg_dict, 'Windy',
                                              'station_id', 'password')
        if site_dict is None:
            return

        # Drop legacy v1 options so they do not reach the thread.
        site_dict.pop('api_key', None)
        site_dict.pop('station', None)

        try:
            site_dict['manager_dict'] = weewx.manager.get_manager_dict_from_config(
                cfg_dict, 'wx_binding')
        except weewx.UnknownBinding:
            pass

        self.archive_queue = queue.Queue()
        self.archive_thread = WindyThread(self.archive_queue, **site_dict)

        self.archive_thread.start()
        self.bind(weewx.NEW_ARCHIVE_RECORD, self.new_archive_record)
        loginf("Data for station %s will be uploaded" % site_dict['station_id'])

    def new_archive_record(self, event):
        self.archive_queue.put(event.record)


class WindyThread(weewx.restx.RESTThread):

    def __init__(self, q, station_id, password, server_url=Windy.DEFAULT_URL,
                 skip_upload=False, manager_dict=None,
                 post_interval=300, max_backlog=10, stale=7200,
                 log_success=True, log_failure=True,
                 timeout=60, max_tries=3, retry_wait=5):
        super(WindyThread, self).__init__(q,
                                          protocol_name='Windy',
                                          manager_dict=manager_dict,
                                          post_interval=to_int(post_interval),
                                          max_backlog=to_int(max_backlog),
                                          stale=to_int(stale),
                                          log_success=to_bool(log_success),
                                          log_failure=to_bool(log_failure),
                                          max_tries=to_int(max_tries),
                                          timeout=to_int(timeout),
                                          retry_wait=to_int(retry_wait))
        self.station_id = str(station_id)
        self.password = str(password)
        self.server_url = server_url
        self.skip_upload = to_bool(skip_upload)
        self.software_type = "weewx-windy/%s weewx/%s" % (VERSION, weewx.__version__)
        loginf("Data will be uploaded to %s" % self.server_url)

    def get_request(self, url):
        """Add the station password as a Bearer token."""
        request = super(WindyThread, self).get_request(url)
        request.add_header('Authorization', 'Bearer %s' % self.password)
        return request

    def format_url(self, record):
        """Return the v2 upload URL with observations as query parameters.

        The password goes in the Authorization header, not the URL, so it
        does not appear in debug logs.
        """
        record_m = weewx.units.to_METRICWX(record)

        params = {
            'id': self.station_id,
            'ts': int(record_m['dateTime']),
            'softwaretype': self.software_type,
        }

        # (weewx field, windy parameter, multiplier)
        # METRICWX units: degree_C, meter_per_second, mbar, mm, watt_per_meter_squared
        fields = [
            ('outTemp', 'temp', 1.0),            # degree_C
            ('windSpeed', 'wind', 1.0),          # m/s
            ('windGust', 'gust', 1.0),           # m/s
            ('windDir', 'winddir', 1.0),         # degree
            ('outHumidity', 'humidity', 1.0),    # percent
            ('dewpoint', 'dewpoint', 1.0),       # degree_C
            ('barometer', 'pressure', 100.0),    # mbar to Pascals
            ('hourRain', 'precip', 1.0),         # mm in past hour
            ('UV', 'uv', 1.0),                   # index
            ('radiation', 'solarradiation', 1.0),  # W/m2
        ]

        # Windy v2 requires these parameters as integers.
        integer_fields = ('winddir',)

        for wx_field, windy_field, factor in fields:
            value = record_m.get(wx_field)
            if value is None:
                continue
            value = value * factor
            if windy_field == 'winddir':
                params[windy_field] = int(round(value)) % 360
            elif windy_field in integer_fields:
                params[windy_field] = int(round(value))
            else:
                params[windy_field] = round(value, 2)

        url = '%s?%s' % (self.server_url, urlencode(params))
        if weewx.debug >= 2:
            logdbg("url: %s" % url)
        return url

    def get_post_body(self, record):
        """Return None so RESTThread sends a GET request."""
        return None

    def handle_exception(self, e, count):
        """Map Windy v2 error codes to weewx upload outcomes."""
        code = getattr(e, 'code', None)
        if code is None:
            # Network faults (DNS, refused connection, timeout). weewx logs
            # these at debug level only, which hides the cause of repeated
            # "Failed upload after N tries" errors. Log the reason instead.
            self._log_attempt(e, count)
            super(WindyThread, self).handle_exception(e, count)
            return

        body = ''
        try:
            body = e.read()
            if isinstance(body, bytes):
                body = body.decode('utf-8', 'replace')
        except Exception:
            pass

        if code == 401:
            raise weewx.restx.BadLogin("Missing station password: %s" % body)
        if code == 400:
            if 'password' in body.lower():
                raise weewx.restx.BadLogin("Station password rejected: %s" % body)
            raise weewx.restx.FailedPost("Payload rejected (400): %s" % body)
        if code == 409:
            raise weewx.restx.AbortedPost("Duplicate observation (409)")
        if code == 429:
            retry_after = ''
            try:
                retry_after = json.loads(body).get('retry_after', '')
            except (ValueError, AttributeError):
                pass
            raise weewx.restx.AbortedPost("Rate limited (429), retry after %s"
                                          % retry_after)

        self._log_attempt(e, count)
        super(WindyThread, self).handle_exception(e, count)

    def _log_attempt(self, e, count):
        """Log why an upload attempt failed: info for a retry, error on the last."""
        msg = "Upload attempt %d of %d failed: %s" % (count, self.max_tries, e)
        if count >= self.max_tries:
            logerr(msg)
        else:
            loginf(msg)


# Use this hook to test the uploader:
#   PYTHONPATH=bin python bin/user/windy.py

if __name__ == "__main__":
    weewx.debug = 2

    import weeutil.logger
    weeutil.logger.setup('windy', {})

    q = queue.Queue()
    t = WindyThread(q, station_id='STATION_ID', password='STATION_PASSWORD',
                    post_interval=None, stale=None)
    t.start()
    r = {'dateTime': int(time.time() + 0.5),
         'usUnits': weewx.US,
         'outTemp': 32.5,
         'inTemp': 75.8,
         'outHumidity': 24,
         'windSpeed': 10,
         'windDir': 32}
    print(t.format_url(r))
    q.put(r)
    q.put(None)
    t.join(30)
