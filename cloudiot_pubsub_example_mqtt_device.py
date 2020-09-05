import argparse
import datetime
import json
import os
import ssl
import time
import config
import serial
import struct
import datetime
import jwt
import paho.mqtt.client as mqtt
from xbee import ZigBee

private_key_file = '/home/pi/xbee-code/rsa_private.pem'
algorithm = 'RS256' # Either RS256 or ES256
root_cert_filepath = '/home/pi/xbee-code/roots.pem'
project_id = 'tranquil-garage-284216'
cloud_region = 'europe-west1'
registry_id = 'Raspberrypi'
device_id = 'rpi'

PORT = '/dev/ttyUSB0'
BAUD_RATE = 9600


def create_jwt(project_id, private_key_file, algorithm):
    """Create a JWT (https://jwt.io) to establish an MQTT connection."""
    token = {
        'iat': datetime.datetime.utcnow(),
        'exp': datetime.datetime.utcnow() + datetime.timedelta(minutes=60),
        'aud': project_id
    }
    with open(private_key_file, 'r') as f:
        private_key = f.read()
    print('Creating JWT using {} from private key file {}'.format(
        algorithm, private_key_file))
    return jwt.encode(token, private_key, algorithm=algorithm)


def error_str(rc):
    """Convert a Paho error to a human readable string."""
    return '{}: {}'.format(rc, mqtt.error_string(rc))


class Device(object):
    """Represents the state of a single device."""

    def __init__(self):
        self.temperature = 0
        self.fan_on = False
        self.connected = False

    def update_sensor_data(self):
        """Pretend to read the device's sensor data.
        If the fan is on, assume the temperature decreased one degree,
        otherwise assume that it increased one degree.
        """
        if self.fan_on:
            self.temperature -= 1
        else:
            self.temperature += 1

    def wait_for_connection(self, timeout):
        """Wait for the device to become connected."""
        total_time = 0
        while not self.connected and total_time < timeout:
            time.sleep(1)
            total_time += 1

        if not self.connected:
            raise RuntimeError('Could not connect to MQTT bridge.')

    def on_connect(self, unused_client, unused_userdata, unused_flags, rc):
        """Callback for when a device connects."""
        print('Connection Result:', error_str(rc))
        self.connected = True

    def on_disconnect(self, unused_client, unused_userdata, rc):
        """Callback for when a device disconnects."""
        print('Disconnected:', error_str(rc))
        self.connected = False

    def on_publish(self, unused_client, unused_userdata, unused_mid):
        """Callback when the device receives a PUBACK from the MQTT bridge."""
        print('Published message acked.')

    def on_subscribe(self, unused_client, unused_userdata, unused_mid,
                     granted_qos):
        """Callback when the device receives a SUBACK from the MQTT bridge."""
        print('Subscribed: ', granted_qos)
        if granted_qos[0] == 128:
            print('Subscription failed.')

    def on_message(self, unused_client, unused_userdata, message):
        """Callback when the device receives a message on a subscription."""
        payload = message.payload.decode('utf-8')
        print('Received message \'{}\' on topic \'{}\' with Qos {}'.format(
            payload, message.topic, str(message.qos)))

        # The device will receive its latest config when it subscribes to the
        # config topic. If there is no configuration for the device, the device
        # will receive a config with an empty payload.
        if not payload:
            return

        # The config is passed in the payload of the message. In this example,
        # the server sends a serialized JSON string.
        data = json.loads(payload)
        if data['fan_on'] != self.fan_on:
            # If changing the state of the fan, print a message and
            # update the internal state.
            self.fan_on = data['fan_on']
            if self.fan_on:
                print('Fan turned on.')
            else:
                print('Fan turned off.')

def decodeReceivedFrame(data):
        try:
            samples = data['rf_data']   
            ans = struct.unpack('f', samples)
            return float("{:.2f}".format(ans[0]))
        except:
            return str(data['rf_data'],'utf-8')   


def main():
     

    # Create the MQTT client and connect to Cloud IoT.
    client = mqtt.Client(
        client_id='projects/{}/locations/{}/registries/{}/devices/{}'.format(
            project_id,
            cloud_region,
            registry_id,
            device_id))
    client.username_pw_set(
        username='unused',
        password=create_jwt(
            project_id,
            private_key_file,
            algorithm))
    client.tls_set(root_cert_filepath, tls_version=ssl.PROTOCOL_TLSv1_2)

    device = Device()

    client.on_connect = device.on_connect
    client.on_publish = device.on_publish
    client.on_disconnect = device.on_disconnect
    client.on_subscribe = device.on_subscribe
    client.on_message = device.on_message

    client.connect('mqtt.googleapis.com', 443)

    client.loop_start()

    # This is the topic that the device will publish telemetry events
    # (temperature data) to.
    mqtt_telemetry_topic = '/devices/{}/events'.format(device_id)

    # This is the topic that the device will receive configuration updates on.
    mqtt_config_topic = '/devices/{}/config'.format(device_id)

    # Wait up to 5 seconds for the device to connect.
    device.wait_for_connection(5)

    # Subscribe to the config topic.
    client.subscribe(mqtt_config_topic, qos=1)
    
    ser = serial.Serial(PORT, BAUD_RATE)
    zb = ZigBee(ser, escaped = True)
    currentType = ""
    currentPayload = ""
    currentTemperature = 0.0
    currentHumidity = 0.0


    while True:
         try:
            data = zb.wait_read_frame()
            decoded = decodeReceivedFrame(data)
            
            if type(decoded) is str:
                currentType = str(data['rf_data'],'utf-8')
                #print("currentType =" + currentType)

            else:
                #print("Assign Value for: " + currentType)
                if currentType == "Humidity:":
                    #print("Assigning Humidity")
                    if currentHumidity != decoded:
                        currentHumidity = decoded
                        
                elif currentType == "Temperature:":
                    #print("Assigning Temperature")
                    if currentTemperature != decoded:
                        currentTemperature = decoded

            if currentType != "":
                payload = '{{ "temperature": {}, "humidity": {} }}'.format(currentTemperature, currentHumidity)
                                                                           
                if currentPayload != payload and currentTemperature > 0.0 and currentHumidity > 0.0:
                    currentPayload = payload                                                       
                    client.publish(mqtt_telemetry_topic, payload, qos=1)
                    print("{}\n".format(payload))
                else:
                    print("{}\n".format(payload))                                                       
                                                                           

            else:
                print("Waiting for data.\n")
                
         except KeyboardInterrupt:
             break





#     # Update and publish temperature readings at a rate of one per second.
#     for _ in range(100):
#         # In an actual device, this would read the device's sensors. Here,
#         # you update the temperature based on whether the fan is on.
#         device.update_sensor_data()
# 
#         # Report the device's temperature to the server by serializing it
#         # as a JSON string.
#         payload = json.dumps({'temperature': device.temperature})
#         print('Publishing payload', payload)
#         client.publish(mqtt_telemetry_topic, payload, qos=1)
#         # Send events every second.
#         time.sleep(1)

    client.disconnect()
    client.loop_stop()
    


if __name__ == '__main__':
    main()
