import time
import os
from threading import Event, Thread

import paho.mqtt.client as mqtt
import requests

import gtfs_realtime_pb2


## https://stackoverflow.com/questions/22498038/improve-current-implementation-of-a-setinterval-python/22498708#22498708
def call_repeatedly(interval, func, *args):
    stopped = Event()

    def loop():
        while not stopped.wait(interval):  # the first call is in `interval` secs
            func(*args)

    Thread(target=loop, daemon=True).start()
    return stopped.set


class GTFSRTHTTP2MQTTTransformer:
    def __init__(self, mqttConnect, mqttCredentials, baseMqttTopic, gtfsrtFeedURL):
        self.mqttConnect = mqttConnect
        self.mqttCredentials = mqttCredentials
        self.baseMqttTopic = baseMqttTopic
        self.gtfsrtFeedURL = gtfsrtFeedURL
        self.mqttConnected = False

    def onMQTTConnected(self, client, userdata, flags, rc):
        print("Connected with result code " + str(rc))
        if rc != 0:
            return False
        self.mqttConnected = True

        self.startGTFSRTPolling()

    def connectMQTT(self):
        self.client = mqtt.Client()
        self.client.on_connect = self.onMQTTConnected
        self.client.connect(**self.mqttConnect)
        if self.mqttCredentials and self.mqttCredentials['username'] and self.mqttCredentials['password']:
            self.client.username_pw_set(**self.mqttCredentials)
        self.client.loop_forever()

    def startGTFSRTPolling(self):
        print("Starting poller")
        polling_delay = int(os.environ.get('DELAY', 5))
        self.cancelPoller = call_repeatedly(polling_delay, self.doGTFSRTPolling)

    def doGTFSRTPolling(self):
        print("doGTFSRTPolling", time.ctime())
        r = requests.get(self.gtfsrtFeedURL)

        feedmsg = gtfs_realtime_pb2.FeedMessage()
        try:
            feedmsg.ParseFromString(r.content)
            for entity in feedmsg.entity:
                nfeedmsg = gtfs_realtime_pb2.FeedMessage()
                nfeedmsg.header.gtfs_realtime_version = "1.0"
                nfeedmsg.header.incrementality = nfeedmsg.header.DIFFERENTIAL
                nfeedmsg.header.timestamp = int(time.time())
                nent = nfeedmsg.entity.add()

                nent.CopyFrom(entity)

                route_id_remove_first = int(os.environ.get('ROUTE_ID_REMOVE_FIRST', 0)) # Remove first n characters
                route_id_remove_last = int(os.environ.get('ROUTE_ID_REMOVE_LAST', 0)) # Remove last n characters
                route_id = entity.vehicle.trip.route_id[route_id_remove_first:-route_id_remove_last]
                direction_id = entity.vehicle.trip.direction_id
                trip_headsign = entity.vehicle.vehicle.label
                start_time = entity.vehicle.trip.start_time[0:5] # hh:mm
                vehicle_id = entity.vehicle.vehicle.id

                # gtfsrt/vp/<feed_Id>/<agency_id>/<agency_name>/<mode>/<route_id>/<direction_id>/<trip_headsign>/<next_stop>/<start_time>/<vehicle_id>
                # GTFS RT feed used for testing was missing some information so those are empty
                full_topic = '{0}////{1}/{2}/{3}//{4}/{5}'.format(
                    self.baseMqttTopic, route_id, direction_id,
                    trip_headsign, start_time, vehicle_id)

                sernmesg = nfeedmsg.SerializeToString()
                self.client.publish(full_topic, sernmesg)

        except:
            print(r.content)
            raise


if __name__ == '__main__':
    gh2mt = GTFSRTHTTP2MQTTTransformer(
        {'host': os.environ['MQTT_BROKER_URL']},
        {'username': os.environ['USERNAME'], 'password': os.environ['PASSWORD']},
        '/gtfsrt/{0}/{1}'.format(os.environ['FEED_TYPE'], os.environ['FEED_NAME']),
        os.environ['FEED_URL']
    )

    try:
        gh2mt.connectMQTT()
    finally:
        gh2mt.cancelPoller()
