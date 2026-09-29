# weewx-windy

WeeWX extension that sends data to windy.com

This version uses the Windy Stations API v2. The legacy API shuts down at the
end of 2026.

You need the station ID and station password for your station. Find both on
the station detail page under My Stations:

  https://stations.windy.com/

The station password is not the same as an API key from the API Keys page.
An API key cannot upload observations.

## Installation

1) download and install:

    WeeWX Version 4.x:
    
        wget -O weewx-windy.zip https://github.com/matthewwall/weewx-windy/archive/master.zip
        wee_extension --install weewx-windy.zip
    
    WeeWX Version 5.x:
    
        weectl extension install https://github.com/matthewwall/weewx-windy/archive/master.zip
 

2) enter parameters in the weewx configuration file

    ```
    [StdRESTful]
        [[Windy]]
            station_id = STATION_ID
            password = STATION_PASSWORD
    ```

3) restart weewx. For example:

    ```
    sudo systemctl restart weewx
    ```

    or, on older systems:

    ```
    sudo /etc/init.d/weewx stop
    sudo /etc/init.d/weewx start
    ```

## Upgrading from 0.8 or earlier

Version 1.0 uses the v2 API, which needs different credentials. After you
install the new version:

1) delete the `api_key` and `station` lines from the `[[Windy]]` section
2) add `station_id` and `password` from My Stations
3) restart weewx

Windy accepts at most one upload every 5 minutes per station, and rejects
observations older than 2 hours. The defaults `post_interval = 300` and
`stale = 7200` match these limits.

## License & Copyright
Copyright (c) 2019-2026 Matthew Wall

Distributed under the terms of the GNU Public License (GPLv3)
See the file LICENSE.txt for your full rights.
