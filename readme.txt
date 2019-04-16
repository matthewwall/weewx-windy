windy - weewx extension that sends data to windy.com
Copyright 2019 Matthew Wall

Installation instructions:

1) run the installer:

wee_extension --install weewx-windy.tgz

2) enter parameters in weewx.conf:

[StdRESTful]
    [[Windy]]
        

3) restart weewx:

sudo /etc/init.d/weewx stop
sudo /etc/init.d/weewx start
