# installer for windy
# Copyright 2019-2026 Matthew Wall
# Distributed under the terms of the GNU Public License (GPLv3)

"""Installer for the Windy uploader.

On an interactive install, the installer asks for the Windy station ID and
station password. On an upgrade from 0.8 or earlier, it also removes the
legacy api_key and station options, which do not work with the v2 API.

Press Enter at either prompt to skip. The options are then set to
replace_me, and must be edited in weewx.conf before uploads start.
"""

from __future__ import print_function

import getpass
import sys

from weecfg.extension import ExtensionInstaller

try:
    # Python 2
    # noinspection PyUnresolvedReferences
    input = raw_input
except NameError:
    # Python 3
    pass

try:
    # Python 3
    from urllib.request import Request, urlopen
    from urllib.error import HTTPError
except ImportError:
    # Python 2
    # noinspection PyUnresolvedReferences
    from urllib2 import Request, urlopen, HTTPError

VERSION = "1.0.1"
PLACEHOLDER = 'replace_me'
CHECK_URL = 'https://stations.windy.com/api/v2/observation?latestLimit=1'
LEGACY_OPTIONS = ('api_key', 'station')


def loader():
    return WindyInstaller()


class WindyInstaller(ExtensionInstaller):
    def __init__(self):
        super(WindyInstaller, self).__init__(
            version=VERSION,
            name='windy',
            description='Upload weather data to Windy.',
            author="Matthew Wall",
            author_email="mwall@users.sourceforge.net",
            restful_services='user.windy.Windy',
            config={
                'StdRESTful': {
                    'Windy': {
                        'station_id': PLACEHOLDER,
                        'password': PLACEHOLDER}}},
            files=[('bin/user', ['bin/user/windy.py'])]
            )

    def configure(self, engine):
        """Prompt for v2 credentials and remove legacy options.

        Runs before the installer merges its config section, so any values
        set here are kept. Returns True if the config was changed.
        """
        out = _printer(engine)
        if getattr(engine, 'dry_run', False):
            return False

        restful = engine.config_dict.setdefault('StdRESTful', {})
        windy = restful.setdefault('Windy', {})
        changed = False

        legacy = [k for k in LEGACY_OPTIONS if k in windy]
        if legacy:
            out("Windy: found legacy option(s) %s from version 0.8 or earlier."
                % ', '.join(legacy))
            out("Windy: the v2 API needs a station ID and station password"
                " from My Stations at https://stations.windy.com/")

        if _is_set(windy.get('station_id')) and _is_set(windy.get('password')):
            station_id = windy['station_id']
            password = windy['password']
        elif sys.stdin.isatty():
            station_id = input("Windy station ID (Enter to skip): ").strip()
            password = ''
            if station_id:
                password = getpass.getpass(
                    "Windy station password (Enter to skip): ").strip()
        else:
            station_id = password = ''
            out("Windy: non-interactive install, not prompting for credentials.")

        if station_id and password:
            if windy.get('station_id') != station_id or windy.get('password') != password:
                windy['station_id'] = station_id
                windy['password'] = password
                changed = True
            _check_credentials(station_id, password, out)
            if legacy:
                _retire_legacy(windy, legacy)
                changed = True
                out("Windy: commented out legacy option(s) %s."
                    % ', '.join(legacy))
        else:
            out("Windy: set station_id and password in the [[Windy]] section"
                " of weewx.conf, then restart weewx.")
            if legacy:
                out("Windy: legacy option(s) %s left in place. Delete them"
                    " once the new credentials are set." % ', '.join(legacy))

        return changed


def _retire_legacy(windy, legacy):
    """Comment out legacy options and keep the user's comments.

    configobj attaches comments to the option that follows them, so deleting
    an option also deletes its comments. This moves those comments, plus a
    commented-out copy of each legacy line, onto station_id. It then places
    station_id and password where the first legacy option was.
    """
    scalars = getattr(windy, 'scalars', None)
    position = None
    if scalars is not None:
        position = min(scalars.index(k) for k in legacy)

    carried = []
    for i, key in enumerate(legacy):
        carried.extend(windy.comments.get(key, []))
        if i == 0:
            carried.append('# Legacy option(s) below are not used by the v2 API.')
        line = '# %s = %s' % (key, windy[key])
        inline = windy.inline_comments.get(key)
        if inline:
            line = '%s %s' % (line, inline)
        carried.append(line)
        del windy[key]
    windy.comments['station_id'] = carried + windy.comments.get('station_id', [])

    if scalars is not None:
        for key in ('station_id', 'password'):
            scalars.remove(key)
        scalars[position:position] = ['station_id', 'password']


def _is_set(value):
    return bool(value) and value != PLACEHOLDER


def _printer(engine):
    """Return a print function for weewx 5 (printer) or weewx 4 (logger)."""
    printer = getattr(engine, 'printer', None)
    if printer is not None:
        return printer.out
    logger = getattr(engine, 'logger', None)
    if logger is not None:
        return logger.log
    return print


def _check_credentials(station_id, password, out):
    """Confirm the password works by reading the latest observation.

    A failed check is reported but never stops the install.
    """
    request = Request(CHECK_URL)
    request.add_header('Authorization', 'Bearer %s' % password)
    try:
        response = urlopen(request, timeout=10)
        body = response.read().decode('utf-8', 'replace')
        if station_id in body:
            out("Windy: credentials verified for station %s." % station_id)
        else:
            out("Windy: password accepted, but it belongs to a different"
                " station ID. Check station_id in weewx.conf.")
    except HTTPError as e:
        if e.code in (400, 401):
            out("Windy: station password rejected (HTTP %s). Check it in"
                " My Stations and update weewx.conf." % e.code)
        else:
            out("Windy: could not verify credentials (HTTP %s)." % e.code)
    except Exception as e:
        out("Windy: could not verify credentials (%s)." % e)
