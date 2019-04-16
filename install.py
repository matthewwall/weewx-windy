# installer for windy
# Copyright 2019 Matthew Wall

from setup import ExtensionInstaller

def loader():
    return WindyInstaller()

class WindyInstaller(ExtensionInstaller):
    def __init__(self):
        super(WindyInstaller, self).__init__(
            version="0.1",
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
