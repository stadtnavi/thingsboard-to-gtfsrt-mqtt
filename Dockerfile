FROM python:3.9-slim

RUN mkdir -p /usr/src/app
WORKDIR /usr/src/app
COPY requirements.txt /usr/src/app/

RUN apt-get update && \
      apt-get install -y build-essential && \
      pip install -r requirements.txt && \
      apt-get remove -y build-essential && \
      apt-get autoremove -y && \
      apt-get clean

COPY gtfs_realtime_pb2.py /usr/src/app/
COPY thingsboard-to-gtfsrt-mqtt.py /usr/src/app/

CMD ["python", "-u", "thingsboard-to-gtfsrt-mqtt.py" ]
