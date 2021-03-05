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

import glob
import requests
import os
import datetime
import json
from argparse import ArgumentParser
import time
from jinja2 import Environment, FileSystemLoader, select_autoescape
from functools import lru_cache

class ThingsboardClient:
    def __init__(self):
        self.base_url = os.environ['THINGSBOARD_HOST']

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

    def get_vehicles(self):
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
            vehicle = {
                "id": id,
                "latitude" : lat,
                "longitude" : lon
            }
            vehicles.append(vehicle)
        return vehicles

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
        self.client.username_pw_set(**self.mqttCredentials)
        self.client.connect(**self.mqttConnect)
        self.client.loop_forever()

    def startThingsboardPolling(self):
        print("Starting GTFS RT poller")
        polling_interval = int(os.environ.get('INTERVAL', 1))
        self.GTFSRTPoller = call_repeatedly(polling_interval, self.doThingsboardPolling)

    def doThingsboardPolling(self):
        print("doThingsboardPolling", time.ctime())

        thingsboard_client = ThingsboardClient()
        vehicles = thingsboard_client.get_vehicles()

        for vehicle in vehicles:

            nfeedmsg = gtfs_realtime_pb2.FeedMessage()
            nfeedmsg.header.gtfs_realtime_version = "1.0"
            nfeedmsg.header.incrementality = nfeedmsg.header.DIFFERENTIAL
            nfeedmsg.header.timestamp = int(time.time())
            ent = nfeedmsg.entity.add()

            ent.id = vehicle["id"]
            ent.vehicle.position.latitude = vehicle['latitude']
            ent.vehicle.position.longitude = vehicle['longitude']

            full_topic = f'{ self.baseMqttTopic }/vp/busses/{ vehicle["id"] }'

            print(full_topic)

            sernmesg = nfeedmsg.SerializeToString()
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
