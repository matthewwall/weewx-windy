# Copyright 2019 Matthew Wall

"""
http://windy.com

This is a weewx extension that uploads data to a windy.com

Minimal configuration

[StdRESTful]
    [[Windy]]
        api_key = API_KEY
"""

import Queue
from distutils.version import StrictVersion
import json
import sys
import syslog
import urllib2

import weewx
import weewx.restx
import weewx.units
from weeutil.weeutil import to_bool

VERSION = "0.1"

REQUIRED_WEEWX = "3.6.0"
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

        self.archive_queue = Queue.Queue()
        try:
            self.archive_thread = WindyThread(self.archive_queue, **site_dict)
        except weewx.ViolatedPrecondition, e:
            loginf("Data will not be posted: %s" % e)
            return

        self.archive_thread.start()
        self.bind(weewx.NEW_ARCHIVE_RECORD, self.new_archive_record)
        loginf("Data will be uploaded to %s" % site_dict['server_url'])

    def new_archive_record(self, event):
        self.archive_queue.put(event.record)


class WindyThread(weewx.restx.RESTThread):

    def __init__(self, queue, api_key, server_url, station,
                 skip_upload=False, manager_dict=None,
                 post_interval=None, max_backlog=sys.maxint, stale=None,
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
        self.server_url = server_url
        self.station = station
        self.skip_upload = to_bool(skip_upload)

    def process_record(self, record, dbm):
        if self.augment_record and dbm:
            record = self.get_record(record, dbm)
        url = '%s:%s' % (self.server_url, self.api_key)
        data = self.get_data(record)
        if weewx.debug >= 2:
            logdbg('url: %s' % self.server_url)
            logdbg('data: %s' % data)
        if self.skip_upload:
            raise AbortedPost()
        req = urllib2.Request(url, '\n'.join(data))
        req.add_header("User-Agent", "weewx/%s" % weewx.__version__)
        req.get_method = lambda: 'POST'
        self.post_with_retries(req)

    def get_data(self, record):
        data = dict()
        data['station'] = self.station
        data['dateutc'] = 
        data['temp'] = 
        data['wind'] = 
        data['winddir'] = 
        data['gust'] = 
        data['rh'] = 
        data['dewpoint'] = 
        data['pressure'] = 
        data['baromin'] = 
        data['precip'] = 
        data['uv'] = 
        return json.dumps(data)


# Use this hook to test the uploader:
#   PYTHONPATH=bin python bin/user/windy.py

if __name__ == "__main__":
    import time
    weewx.debug = 2
    queue = Queue.Queue()
    t = WindyThread(queue, manager_dict=None)
    t.process_record({'dateTime': int(time.time() + 0.5),
                      'usUnits': weewx.US,
                      'outTemp': 32.5,
                      'inTemp': 75.8,
                      'outHumidity': 24}, None)
