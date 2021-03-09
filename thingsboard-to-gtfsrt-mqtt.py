import time
import os
import threading
from threading import Event, Thread

import ssl
import paho.mqtt.client as mqtt
import requests
from requests.adapters import HTTPAdapter
from requests.packages.urllib3.util.retry import Retry

from google.protobuf.json_format import MessageToJson
import gtfs_realtime_pb2

import os, sys, datetime, json, time

class ThingsboardClient:
    def __init__(self):
        self.base_url = os.environ['THINGSBOARD_HOST']
        self.data = []

    def get_token(self):
        token_url = f"{self.base_url}/auth/login"

        payload = {
            "username": os.environ['THINGSBOARD_USERNAME'],
            "password": os.environ['THINGSBOARD_PASSWORD']
        }

        response = requests.post(token_url, json=payload)
        return response.json()["token"]

    def fetch_timeseries(self, id, token):
        auth_headers = {
            "X-Authorization": f"Bearer {token}"
        }
        timeseries_url = f"{self.base_url}/plugins/telemetry/DEVICE/{id}/values/timeseries"
        return requests.get(timeseries_url, headers=auth_headers).json()

    def fetch_vehicle_data(self):
        token = self.get_token()
        ids = [
            '17e40b70-5b04-11eb-98a5-133ebfea8661',
            '66df3b20-5b02-11eb-98a5-133ebfea8661',
            '14341fa0-5b00-11eb-98a5-133ebfea8661',
            'fef36ff0-5afb-11eb-98a5-133ebfea8661'
        ]
        vehicles = []
        for id in ids:
            timeseries = self.fetch_timeseries(id, token)
            lat = float(timeseries["latitude"][0]["value"])
            lon = float(timeseries["longitude"][0]["value"])
            pax = int(timeseries["pax"][0]["value"])
            vehicle = {
                "id": id,
                "latitude" : lat,
                "longitude" : lon,
                "pax" : pax
            }
            vehicles.append(vehicle)
        print("Fetched vehicle data from thingsboard")
        self.data = vehicles

    def get_vehicles(self):
        return self.data

thingsboard_client = ThingsboardClient()

def exception_hook(exctype):
    print(exctype.exc_value)
    os._exit(1)

## https://stackoverflow.com/questions/22498038/improve-current-implementation-of-a-setinterval-python/22498708#22498708
def call_repeatedly(interval, func, *args):
    stopped = Event()

    def loop():
        while not stopped.wait(interval):  # the first call is in `interval` secs
            func(*args)
        print("Polling stopped")

    threading.excepthook = exception_hook
    Thread(target=loop, daemon=True).start()
    return stopped.set


class GTFSRTHTTP2MQTTTransformer:
    def __init__(self, mqttConnect, mqttCredentials):
        self.mqttConnect = mqttConnect
        self.mqttCredentials = mqttCredentials
        self.mqttConnected = False
        print("Connecting to MQTT")

    def onMQTTConnected(self, client, userdata, flags, rc):
        print("Connected with result code " + str(rc))
        if rc != 0:
            return False
        if self.mqttConnected is True:
            print("Reconnecting and restarting poller")
            self.ThingsboardPoller()
        self.mqttConnected = True
        self.startThingsboardPolling()

    def connectMQTT(self):
        self.client = mqtt.Client()
        self.client.on_connect = self.onMQTTConnected
        self.client.tls_set(cert_reqs=ssl.CERT_REQUIRED, tls_version=ssl.PROTOCOL_TLS)
        self.client.username_pw_set(**self.mqttCredentials)
        self.client.connect(**self.mqttConnect)
        self.client.loop_forever()

    def update_thingsboard(self):
        thingsboard_client.fetch_vehicle_data()

    def startThingsboardPolling(self):
        print("Starting Thingsboard poller")
        thingsboard_client.fetch_vehicle_data()
        call_repeatedly(15, self.update_thingsboard)
        self.ThingsboardPoller = call_repeatedly(1, self.publish_to_mqtt)

    def calculate_occupancy(self, pax):
        percent_full = pax / 60 * 100
        if (percent_full < 50):
            return "MANY_SEATS_AVAILABLE"
        elif (percent_full < 85):
            return "FEW_SEATS_AVAILABLE"
        else:
            return "STANDING_ROOM_ONLY"

    def publish_to_mqtt(self):

        vehicles = thingsboard_client.get_vehicles()

        for vehicle in vehicles:

            nfeedmsg = gtfs_realtime_pb2.FeedMessage()
            nfeedmsg.header.gtfs_realtime_version = "1.0"
            nfeedmsg.header.incrementality = nfeedmsg.header.DIFFERENTIAL
            nfeedmsg.header.timestamp = int(time.time())
            ent = nfeedmsg.entity.add()
            ent.id = vehicle["id"]
            trip = ent.vehicle.trip.trip_id = "unknown-trip-id"
            ent.vehicle.position.latitude = vehicle['latitude']
            ent.vehicle.position.longitude = vehicle['longitude']
            ent.vehicle.vehicle.id = vehicle['id']

            pax = vehicle["pax"]
            occupancy = gtfs_realtime_pb2.VehiclePosition.OccupancyStatus.Value(self.calculate_occupancy(pax))
            ent.vehicle.occupancy_status = occupancy

            #percent_full = pax / 60 * 100
            #ent.vehicle.occupancy_percentage = percent_full

            # /gtfsrt/vp/<feed_Id>/<agency_id>/<agency_name>/<mode>/<route_id>/<direction_id>/<trip_headsign>/<trip_id>/<next_stop>/<start_time>/<vehicle_id>/<geo_hash>/<short_name>
            full_topic = f'/gtfsrt/vp/hb/1/1/bus//0/unknown-headsign/unknown-trip-id/unknown-next-stop/00:00/{ vehicle["id"] }/0/0'

            sernmesg = nfeedmsg.SerializeToString()
            self.client.publish(full_topic, sernmesg)

            json = MessageToJson(nfeedmsg)
            self.client.publish(f'/json/vp/{vehicle["id"]}', json)

if __name__ == '__main__':
    gh2mt = GTFSRTHTTP2MQTTTransformer(
        {'host': os.environ['MQTT_BROKER_URL'], 'port': 8883},
        {'username': os.environ['MQTT_USER'], 'password': os.environ['MQTT_PASSWORD'],}
    )

    try:
        gh2mt.connectMQTT()
    finally:
        gh2mt.ThingsboardPoller()