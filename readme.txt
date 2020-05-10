windy - weewx extension that sends data to windy.com
Copyright 2019-2020 Matthew Wall
Distributed under the terms of the GNU Public License (GPLv3)

You will need an API key from windy.com

  https://stations.windy.com/

Installation instructions:

1) download

wget -O weewx-windy.zip https://github.com/matthewwall/weewx-windy/archive/master.zip

2) run the installer

wee_extension --install weewx-windy.zip

3) enter parameters in the weewx configuration file

[StdRESTful]
    [[Windy]]
        api_key = API_KEY

4) restart weewx

sudo /etc/init.d/weewx stop
sudo /etc/init.d/weewx start
