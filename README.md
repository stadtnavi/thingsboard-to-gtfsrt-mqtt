[![Build Status](https://travis-ci.org/HSLdevcom/thingsboard-to-gtfsrt-mqtt.svg?branch=master)]
# thingsboard-to-gtfsrt-mqtt

Reads GTFS-RT feed from a http(s) source and publishes every entity to MQTT topic as its own differential GTFS-RT feed

## Configuration

You need to configure at least the following env variables that are marked as mandatory

* (mandatory) "MQTT_BROKER_URL" MQTT broker's URL
* (mandatory) "FEED_TYPE" which type of a GTFS RT data is provided (for example vp for vehicle position), used in MQTT topic
* (mandatory) "FEED_NAME" name for the data feed, used in MQTT topic
* (mandatory) "FEED_URL" URL for the HTTP(S) GTFS RT data source
* (optional) "USERNAME" username for publishing to a MQTT broker
* (optional) "PASSWORD" password for publishing to a MQTT broker
* (optional, default 5) "INTERVAL" how long to wait in seconds between fetching new data from HTTP(S) data feed
* (optional, default https://dev-api.digitransit.fi/routing/v1/routers/waltti/index/graphql) "OTP_URL" defines where to fetch otp data from
* (optional, default 3600) "OTP_INTERVAL" defines in seconds the wait time between fetching new data from OTP
