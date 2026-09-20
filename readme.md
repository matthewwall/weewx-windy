# weewx-windy

WeeWX extension that sends data to windy.com

You will need a station password from windy.com

  https://stations.windy.com/

## Credentials

Windy issues two different things, and only one of them can upload:

* **Station password** - shown on the station detail page under *My Stations*.
  This is what this extension needs.
* **API key** - created on the *API Keys* page.  It manages stations and reads
  open-licensed station data, but it cannot upload observations.

The station identifier is shown on the same station detail page.  It is a
string, and is not necessarily a number.

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
            station_password = STATION_PASSWORD
            station = STATION_ID
   ```

   Both options are required.  For configurations written for version 0.8 and
   earlier, `api_key` is still accepted in place of `station_password`.

3) restart weewx. For example:

    ```
    sudo /etc/init.d/weewx stop
    sudo /etc/init.d/weewx start
    ```

## Notes

Windy accepts at most one observation per station every five minutes.  If your
`archive_interval` is 300 seconds you are exactly on that limit; raise
`post_interval` if HTTP 429 responses appear in the log.

## License & Copyright
Copyright (c) 2019-2026 Matthew Wall

Distributed under the terms of the GNU Public License (GPLv3)
See the file LICENSE.txt for your full rights.
