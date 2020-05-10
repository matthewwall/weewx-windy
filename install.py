# installer for windy
# Copyright 2019-2020 Matthew Wall
# Distributed under the terms of the GNU Public License (GPLv3)

from weecfg.extension import ExtensionInstaller

def loader():
    return WindyInstaller()

class WindyInstaller(ExtensionInstaller):
    def __init__(self):
        super(WindyInstaller, self).__init__(
            version="0.7",
            name='windy',
            description='Upload weather data to Windy.',
            author="Matthew Wall",
            author_email="mwall@users.sourceforge.net",
            restful_services='user.windy.Windy',
            config={
                'StdRESTful': {
                    'Windy': {
                        'api_key': 'replace_me'}}},
            files=[('bin/user', ['bin/user/windy.py'])]
            )
