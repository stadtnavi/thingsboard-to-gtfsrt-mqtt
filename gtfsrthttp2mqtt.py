import time
import os
from threading import Event, Thread

import ssl
import paho.mqtt.client as mqtt
import requests
from requests.adapters import HTTPAdapter
from requests.packages.urllib3.util.retry import Retry

import gtfs_realtime_pb2
import utils


## https://stackoverflow.com/questions/22498038/improve-current-implementation-of-a-setinterval-python/22498708#22498708
def call_repeatedly(interval, func, *args):
    stopped = Event()

    def loop():
        while not stopped.wait(interval):  # the first call is in `interval` secs
            func(*args)
        print("Polling stopped")

    Thread(target=loop, daemon=False).start()
    return stopped.set


class GTFSRTHTTP2MQTTTransformer:
    def __init__(self, mqttConnect, mqttCredentials, baseMqttTopic):
        self.mqttConnect = mqttConnect
        self.mqttCredentials = mqttCredentials
        print(self.mqttCredentials)
        self.baseMqttTopic = baseMqttTopic
        self.mqttConnected = False
        self.session = requests.Session()
        retry = Retry(connect=60, backoff_factor=1.5)
        adapter = HTTPAdapter(max_retries=retry)

    def onMQTTConnected(self, client, userdata, flags, rc):
        print("Connected with result code " + str(rc))
        if rc != 0:
            return False
        if self.mqttConnected is True:
            print("Reconnecting and restarting poller")
            self.GTFSRTPoller()
        self.mqttConnected = True
        self.startThingsboardPolling()

    def connectMQTT(self):
        self.client = mqtt.Client()
        self.client.on_connect = self.onMQTTConnected
        self.client.tls_set(cert_reqs=ssl.CERT_REQUIRED, tls_version=ssl.PROTOCOL_TLS)
        self.client.connect(**self.mqttConnect)
        if self.mqttCredentials and self.mqttCredentials['username'] and self.mqttCredentials['password']:
            print("settttttinnnggg")
            self.client.username_pw_set(**self.mqttCredentials)
        self.client.loop_forever()

    def startThingsboardPolling(self):
        print("Starting GTFS RT poller")
        polling_interval = int(os.environ.get('INTERVAL', 1))
        self.GTFSRTPoller = call_repeatedly(polling_interval, self.doThingsboardPolling)

    def doThingsboardPolling(self):
        print("doThingsboardPolling", time.ctime())
        #r = self.session.get(self.gtfsrtFeedURL)

        #if r.status_code != 200:
            #print("GTFS RT feed returned with " + str(r.status_code))
            #return
        vehicles = [{ "latitude": 48, "longitude": 8, "id": "vehicle-1" }]

        for vehicle in vehicles:

            nfeedmsg = gtfs_realtime_pb2.FeedMessage()
            nfeedmsg.header.gtfs_realtime_version = "1.0"
            nfeedmsg.header.incrementality = nfeedmsg.header.DIFFERENTIAL
            nfeedmsg.header.timestamp = int(time.time())
            nent = nfeedmsg.entity.add()
            nent.id = "entity-123"

            trip_id = "trip-123"
            route_id = "route-01"
            direction_id = 1
            trip_headsign = "Herrenberg"
            latitude = "{:.6f}".format(vehicle["latitude"]) # Force coordinates to have 6 numbers
            latitude_head = latitude[:2]
            longitude = "{:.6f}".format(vehicle["longitude"])
            longitude_head = longitude[:2]
            geohash_head = latitude_head + ";" + longitude_head
            geohash_firstdeg = latitude[3] + "" + longitude[3]
            geohash_seconddeg = latitude[4] + "" + longitude[4]
            geohash_thirddeg = latitude[5] + "" + longitude[5]
            stop_id = "stop-123"
            start_time = "10:00" # hh:mm
            vehicle_id = vehicle["id"]
            short_name = "bus-1234"
            color = "red"

            # gtfsrt/vp/<feed_name>/<agency_id>/<agency_name>/<mode>/<route_id>/<direction_id>/<trip_headsign>/<trip_id>/<next_stop>/<start_time>/<vehicle_id>/<geohash_head>/<geohash_firstdeg>/<geohash_seconddeg>/<geohash_thirddeg>/<short_name>/<color>/
            # GTFS RT feed used for testing was missing some information so those are empty
            full_topic = '{0}/{1}////{2}/{3}/{4}/{5}/{6}/{7}/{8}/{9}/{10}/{11}/{12}/{13}/{14}/'.format(
                self.baseMqttTopic, "vp", route_id, direction_id,
                trip_headsign, trip_id, stop_id, start_time, vehicle_id, geohash_head, geohash_firstdeg,
                geohash_seconddeg, geohash_thirddeg, short_name, color)

            print(full_topic)

            sernmesg = nfeedmsg.SerializeToString()
            print(sernmesg)
            self.client.publish(full_topic, sernmesg)

if __name__ == '__main__':
    gh2mt = GTFSRTHTTP2MQTTTransformer(
        {'host': os.environ['MQTT_BROKER_URL'], 'port': 8883},
        {'username': os.environ['MQTT_USER'], 'password': os.environ['MQTT_PASSWORD'],},
        '/gtfsrt'
    )

    try:
        gh2mt.connectMQTT()
    finally:
        gh2mt.GTFSRTPoller()
