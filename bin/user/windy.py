# Copyright 2019-2020 Matthew Wall

"""
This is a weewx extension that uploads data to a windy.com

http://windy.com

The protocol is desribed at the windy community forum:

https://community.windy.com/topic/8168/report-you-weather-station-data-to-windy

Minimal configuration

[StdRESTful]
    [[Windy]]
        api_key = API_KEY

If you have multiple stations, distinguish them using a station identifier.
For example:

[StdRESTful]
    [[Windy]]
        api_key = API_KEY
        station = 1

The default station identifier is 0.
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

from distutils.version import StrictVersion
import json
import sys
import time

import weewx
import weewx.manager
import weewx.restx
import weewx.units
from weeutil.weeutil import to_bool, to_int

VERSION = "0.7"

REQUIRED_WEEWX = "3.8.0"
if StrictVersion(weewx.__version__) < StrictVersion(REQUIRED_WEEWX):
    raise weewx.UnsupportedFeature("weewx %s or greater is required, found %s"
                                   % (REQUIRED_WEEWX, weewx.__version__))

try:
    # Test for new-style weewx logging by trying to import weeutil.logger
    import weeutil.logger
    import logging
    log = logging.getLogger(__name__)

    def logdbg(msg):
        log.debug(msg)

    def loginf(msg):
        log.info(msg)

    def logerr(msg):
        log.error(msg)

except ImportError:
    # Old-style weewx logging
    import syslog

    def logmsg(level, msg):
        syslog.syslog(level, 'windy: %s' % msg)

    def logdbg(msg):
        logmsg(syslog.LOG_DEBUG, msg)

    def loginf(msg):
        logmsg(syslog.LOG_INFO, msg)

    def logerr(msg):
        logmsg(syslog.LOG_ERR, msg)


class Windy(weewx.restx.StdRESTbase):
    DEFAULT_URL = 'https://stations.windy.com/pws/update'

    def __init__(self, engine, cfg_dict):
        super(Windy, self).__init__(engine, cfg_dict)
        loginf("version is %s" % VERSION)
        site_dict = weewx.restx.get_site_dict(cfg_dict, 'Windy', 'api_key')
        if site_dict is None:
            return

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

    def __init__(self, q, api_key, station=0, server_url=Windy.DEFAULT_URL,
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
        self.api_key = api_key
        self.station = to_int(station)
        self.server_url = server_url
        loginf("Data will be uploaded to %s" % self.server_url)
        self.skip_upload = to_bool(skip_upload)

    def format_url(self, _):
        """Return an URL for doing a POST to windy"""
        url = '%s/%s' % (self.server_url, self.api_key)
        if weewx.debug >= 2:
            logdbg("url: %s" % url)
        return url

    def get_post_body(self, record):
        """Specialized version for doing a POST to windy"""
        record_m = weewx.units.to_METRICWX(record)
        data = {
            'station': self.station,  # integer identifier, usually "0"
            'dateutc': time.strftime("%Y-%m-%d %H:%M:%S",
                                     time.gmtime(record_m['dateTime']))
            }
        if 'outTemp' in record_m:
            data['temp'] = record_m['outTemp']  # degree_C
        if 'windSpeed' in record_m:
            data['wind'] = record_m['windSpeed']  # m/s
        if 'windDir' in record_m:
            data['winddir'] = record_m['windDir']  # degree
        if 'windGust' in record_m:
            data['gust'] = record_m['windGust']  # m/s
        if 'outHumidity' in record_m:
            data['rh'] = record_m['outHumidity']  # percent
        if 'dewpoint' in record_m:
            data['dewpoint'] = record_m['dewpoint']  # degree_C
        if 'barometer' in record_m:
            if record_m['barometer'] is not None:
                data['pressure'] = 100.0 * record_m['barometer']  # Pascals
            else:
                data['pressure'] = None
        if 'hourRain' in record_m:
            data['precip'] = record_m['hourRain']  # mm in past hour
        if 'UV' in record_m:
            data['uv'] = record_m['UV']

        body = {
            'observations': [data]
            }
        if weewx.debug >= 2:
            logdbg("JSON: %s" % body)

        return json.dumps(body), 'application/json'


# Use this hook to test the uploader:
#   PYTHONPATH=bin python bin/user/windy.py

if __name__ == "__main__":
    weewx.debug = 2

    try:
        # WeeWX V4 logging
        weeutil.logger.setup('windy', {})
    except NameError:
        # WeeWX V3 logging
        syslog.openlog('windy', syslog.LOG_PID | syslog.LOG_CONS)
        syslog.setlogmask(syslog.LOG_UPTO(syslog.LOG_DEBUG))

    q = queue.Queue()
    t = WindyThread(q, api_key='123', station=0)
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