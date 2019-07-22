windy - weewx extension that sends data to windy.com
Copyright 2019 Matthew Wall

You will need an API key from windy.com

  https://stations.windy.com/

Installation instructions:

1) download the latest extension

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
