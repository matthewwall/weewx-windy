# Copyright 2019-2026 Matthew Wall

"""
This is a weewx extension that uploads data to windy.com

http://windy.com

It posts to the Windy Stations API v2, which is documented at:

https://stations.windy.com/api-reference

Authentication is the per-station password shown on the station detail page
under "My Stations" at https://stations.windy.com/stations

Note that the station password is NOT the same thing as an API key created on
the "API Keys" page.  An API key manages stations and reads open-licensed
station data; it cannot upload observations.

Minimal configuration

[StdRESTful]
    [[Windy]]
        station_password = STATION_PASSWORD
        station = STATION_ID

Both options are required.  The station identifier is shown on the station
detail page; it is a string, and is not necessarily a number.

For compatibility with configurations written for version 0.8 and earlier, the
option api_key is accepted as a synonym for station_password.

Windy accepts at most one observation per station every five minutes.  If the
weewx archive_interval is 300 seconds then uploads sit exactly on that limit;
raise post_interval if HTTP 429 responses appear.
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

import logging
import sys
import time

import weewx
import weewx.manager
import weewx.restx
import weewx.units
from weeutil.weeutil import to_bool, version_compare

VERSION = "0.9"

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
        # the station identifier is mandatory for the v2 API
        site_dict = weewx.restx.get_site_dict(cfg_dict, 'Windy', 'station')
        if site_dict is None:
            return

        # Through version 0.8 this option was called api_key.  The value it
        # holds is the per-station password, so station_password is the
        # preferred name, but accept the old spelling so that existing
        # configurations keep working.
        password = site_dict.pop('station_password', None)
        legacy_key = site_dict.pop('api_key', None)
        if password is None and legacy_key is not None:
            password = legacy_key
            loginf("option api_key is deprecated;"
                   " please rename it to station_password")
        if password is None:
            logerr("Data will not be posted: Missing option station_password")
            return
        site_dict['station_password'] = password

        try:
            site_dict['manager_dict'] = weewx.manager.get_manager_dict_from_config(cfg_dict, 'wx_binding')
        except weewx.UnknownBinding:
            pass

        self.archive_queue = queue.Queue()
        self.archive_thread = WindyThread(self.archive_queue, **site_dict)

        self.archive_thread.start()
        self.bind(weewx.NEW_ARCHIVE_RECORD, self.new_archive_record)

    def new_archive_record(self, event):
        self.archive_queue.put(event.record)


class WindyThread(weewx.restx.RESTThread):

    def __init__(self, q, station_password, station,
                 server_url=Windy.DEFAULT_URL,
                 skip_upload=False, manager_dict=None,
                 post_interval=None, max_backlog=sys.maxsize, stale=None,
                 log_success=True, log_failure=True,
                 timeout=60, max_tries=3, retry_wait=5):
        super(WindyThread, self).__init__(q,
                                          protocol_name='Windy',
                                          manager_dict=manager_dict,
                                          post_interval=post_interval,
                                          max_backlog=max_backlog,
                                          stale=stale,
                                          log_success=log_success,
                                          log_failure=log_failure,
                                          max_tries=max_tries,
                                          timeout=timeout,
                                          retry_wait=retry_wait)
        self.station_password = station_password
        # v2 station identifiers are strings, not integers
        self.station = str(station).strip()
        self.server_url = server_url
        self.skip_upload = to_bool(skip_upload)
        loginf("Data for station %s will be uploaded to %s"
               % (self.station, self.server_url))

    def format_url(self, record):
        """Return an URL for doing a GET to windy.

        The v2 API takes the entire observation as query parameters.  The
        station password may be passed either as the PASSWORD parameter or as
        a bearer token; this uses the parameter.
        """
        record_m = weewx.units.to_METRICWX(record)

        data = {
            'id': self.station,
            'dateutc': time.strftime("%Y-%m-%d %H:%M:%S",
                                     time.gmtime(record_m['dateTime'])),
            'softwaretype': 'weewx-%s' % weewx.__version__,
        }
        if record_m.get('outTemp') is not None:
            data['temp'] = round(record_m['outTemp'], 2)          # degree_C
        if record_m.get('windSpeed') is not None:
            data['wind'] = round(record_m['windSpeed'], 2)        # m/s
        if record_m.get('windDir') is not None:
            # Windy validates winddir as an integer even though the published
            # schema declares it a number, so an averaged wind direction is
            # rejected with HTTP 400 "winddir must be an integer number".
            data['winddir'] = int(round(record_m['windDir']))     # degree
        if record_m.get('windGust') is not None:
            data['gust'] = round(record_m['windGust'], 2)         # m/s
        if record_m.get('outHumidity') is not None:
            data['rh'] = round(record_m['outHumidity'], 2)        # percent
        if record_m.get('dewpoint') is not None:
            data['dewpoint'] = round(record_m['dewpoint'], 2)     # degree_C
        if record_m.get('barometer') is not None:
            data['pressure'] = round(100.0 * record_m['barometer'], 1)  # Pa
        if record_m.get('hourRain') is not None:
            data['precip'] = round(record_m['hourRain'], 2)   # mm in past hour
        if record_m.get('UV') is not None:
            data['uv'] = round(record_m['UV'], 2)
        if record_m.get('radiation') is not None:
            data['solarradiation'] = round(record_m['radiation'], 1)  # W/m^2

        if weewx.debug >= 2:
            logdbg("url: %s?%s&PASSWORD=XXX"
                   % (self.server_url, urlencode(data)))

        # add the password last so that the redacted line logged above is an
        # accurate rendering of everything else in the query string
        data['PASSWORD'] = self.station_password
        return '%s?%s' % (self.server_url, urlencode(data))

    # There is deliberately no get_post_body here.  The v2 API expects a GET
    # with query parameters, and the inherited implementation returns None,
    # which makes RESTThread issue a GET rather than a POST.


# Use this hook to test the uploader:
#   PYTHONPATH=bin python bin/user/windy.py

if __name__ == "__main__":
    weewx.debug = 2

    import weeutil.logger
    weeutil.logger.setup('windy', {})

    q = queue.Queue()
    t = WindyThread(q, station_password='123', station='test-station')
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
