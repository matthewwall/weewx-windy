# Copyright 2019 Matthew Wall

"""
This is a weewx extension that uploads data to a windy.com

http://windy.com

The protocol is desribed at the windy community forum:

https://community.windy.com/topic/8168/report-you-weather-station-data-to-windy

Minimal configuration

[StdRESTful]
    [[Windy]]
        api_key = API_KEY
        station = STATION_IDENTIFIER
"""

try:
    # Python 2
    from Queue import Queue
except ImportError:
    # Python 3
    from queue import Queue

from distutils.version import StrictVersion
import json
import re
import sys
import syslog

import weewx
import weewx.restx
import weewx.units
from weeutil.weeutil import to_bool

VERSION = "0.1"

REQUIRED_WEEWX = "3.8.0"
if StrictVersion(weewx.__version__) < StrictVersion(REQUIRED_WEEWX):
    raise weewx.UnsupportedFeature("weewx %s or greater is required, found %s"
                                   % (REQUIRED_WEEWX, weewx.__version__))

def logmsg(level, msg):
    syslog.syslog(level, 'restx: Windy: %s' % msg)

def logdbg(msg):
    logmsg(syslog.LOG_DEBUG, msg)

def loginf(msg):
    logmsg(syslog.LOG_INFO, msg)

def logerr(msg):
    logmsg(syslog.LOG_ERR, msg)


class Windy(weewx.restx.StdRESTbase):
    _DEFAULT_URL = 'https://node.windy.com/pws/update'

    def __init__(self, engine, cfg_dict):
        super(Windy, self).__init__(engine, cfg_dict)        
        loginf("version is %s" % VERSION)
        site_dict = weewx.restx.get_site_dict(cfg_dict, 'Windy',
                                              'api_key', 'station')
        if site_dict is None:
            return
        site_dict.setdefault('server_url', Windy._DEFAULT_URL)

        mgr_dict = weewx.manager.get_manager_dict_from_config(
            cfg_dict, 'wx_binding')

        self.archive_queue = Queue()
        try:
            self.archive_thread = WindyThread(self.archive_queue,
                                              manager_dict=mgr_dict,
                                              **site_dict)
        except weewx.ViolatedPrecondition as e:
            loginf("Data will not be posted: %s" % e)
            return

        self.archive_thread.start()
        self.bind(weewx.NEW_ARCHIVE_RECORD, self.new_archive_record)
        loginf("Data will be uploaded to %s" % site_dict['server_url'])

    def new_archive_record(self, event):
        self.archive_queue.put(event.record)


class WindyThread(weewx.restx.RESTThread):

    def __init__(self, queue, api_key, station, server_url=Windy._DEFAULT_URL,
                 skip_upload=False, manager_dict=None,
                 post_interval=None, max_backlog=sys.maxsize, stale=None,
                 log_success=True, log_failure=True,
                 timeout=60, max_tries=3, retry_wait=5):
        super(WindyThread, self).__init__(queue,
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
        self.station = int(station)
        self.server_url = server_url
        self.skip_upload = to_bool(skip_upload)

    def format_url(self, record):
        url = '%s/%s' % (self.server_url, self.api_key)
        if weewx.debug >= 2:
            logdbg('url: %s' % re.sub(r"api_key=.*", "api_key=XXX", url))
        return url

    def get_post_body(self, record):
        rec = weewx.units.to_METRICWX(record)
        data = dict()
        data['station'] = self.station # integer identifier
        data['dateutc'] = time.strftime("%Y-%m-%d %H:%M:%S",
                                        time.gmtime(rec['dateTime']))
        if 'outTemp' in rec:
            data['temp'] = rec['outTemp'] # degree_C
        if 'windSpeed' in rec:
            data['wind'] = rec['windSpeed'] # m/s
        if 'windDir' in rec:
            data['winddir'] = rec['windDir'] # degree
        if 'windGust' in rec:
            data['gust'] = rec['windGust'] # m/s
        if 'outHumidity' in rec:
            data['rh'] = rec['outHumidity'] # percent
        if 'dewpoint' in rec:
            data['dewpoint'] = rec['dewpoint'] # degree_C
        if 'pressure' in rec:
            data['pressure'] = rec['pressure'] # Pa
        if 'barometer' in rec:
            data['baromin'] = rec['barometer'] # inHg # FIXME: need to convert
        if 'hourRain' in rec:
            data['precip'] = rec['hourRain'] # mm in past hour
        if 'UV' in rec:
            data['uv'] = rec['UV']
        return json.dumps(data), 'application/json'


# Use this hook to test the uploader:
#   PYTHONPATH=bin python bin/user/windy.py

if __name__ == "__main__":
    class FakeMgr(object):
        table_name = 'fake'
        def getSql(self, query, value):
            return None

    import time
    weewx.debug = 2
    queue = Queue()
    t = WindyThread(queue, api_key='123', station=0)
    r = {'dateTime': int(time.time() + 0.5),
         'usUnits': weewx.US,
         'outTemp': 32.5,
         'inTemp': 75.8,
         'outHumidity': 24,
         'windSpeed': 10,
         'windDir': 32}
    print t.format_url(r)
    print t.get_post_body(r)
    t.process_record(r, FakeMgr())
