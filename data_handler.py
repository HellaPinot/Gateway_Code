#!/usr/bin/python3

try:
    import httplib
except:
    import http.client as httplib
import config
import serial
import struct
import time
import subprocess
import datetime
import jwt
import paho.mqtt.client as mqtt
from xbee import ZigBee

#Set login keys and connection details for google clouds iot core
ssl_private_key_filepath = '/home/pi/xbee-code/rsa_private.pem'
ssl_algorithm = 'RS256' # Either RS256 or ES256
root_cert_filepath = '/home/pi/xbee-code/roots.pem'
project_id = 'tranquil-garage-284216'
gcp_location = 'europe-west1'
registry_id = 'Raspberrypi'
device_id = 'rpi'
connected = False
USBcon = False

#Set serial port connection values
PORT = '/dev/ttyUSB0'
BAUD_RATE = 9600

#Begin logging to handler_log file
cur_time = datetime.datetime.utcnow()
log = open('handler_log.txt','a')
log.write("Log started: {}\n".format(datetime.datetime.today()))
log.close()

def create_jwt():
  token = {
      'iat': cur_time,
      'exp': cur_time + datetime.timedelta(minutes=60),
      'aud': project_id
  }

  with open(ssl_private_key_filepath, 'r') as f:
    private_key = f.read()

  return jwt.encode(token, private_key, ssl_algorithm)

#set google cloud device registry object
_CLIENT_ID = 'projects/{}/locations/{}/registries/{}/devices/{}'.format(project_id, gcp_location, registry_id, device_id)
_MQTT_TOPIC = '/devices/{}/events'.format(device_id)
_COMMAND = ['/home/pi/xbee-code/data_handler.py']

client = mqtt.Client(client_id=_CLIENT_ID)

# authorization is handled purely with JWT, no user/pass, so username can be whatever
client.username_pw_set(
    username='unused',
    password=create_jwt())

#handle error by number and refer to mqtt class error list
def error_str(rc):
    return '{}: {}'.format(rc, mqtt.error_string(rc))

#handle on connect status, restart program if disconnected
def on_connect(unusued_client, unused_userdata, unused_flags, rc):
    print('on_connect {}\n'.format(error_str(rc)))
    if(rc == 4):
        ser.close()
        logPrint("Trying to reconnect")
        restartProgram

#log published values
def on_publish(unused_client, unused_userdata, unused_mid):
    print('Publishing new values.\n')
    
#ping google to check connection status
def checkInternetHttplib(url="www.google.com", timeout=3):
    conn = httplib.HTTPConnection(url, timeout=timeout)
    try:
        conn.request("HEAD", "/")
        conn.close()
        return True
    except Exception as e:
        print('checkInternetHttplib error')
        return False
    
#handle incoming frames via xbee, determine if number value or string object
def decodeReceivedFrame(data):
    try:
        samples = data['rf_data']   
        ans = struct.unpack('f', samples)
        return float("{:.2f}".format(ans[0]))
    except:
        return str(data['rf_data'],'utf-8')
    
#handles command line messages and logging
def logPrint(message):
    print(message)
    log = open('handler_log.txt','a')
    log.write(message)
    log.close()
    
#handles restart of program if error encountered
def restartProgram():
    client.disconnect()
    client.loop_stop()
    rc = subprocess.call(_COMMAND)


client.on_connect = on_connect
client.on_publish = on_publish
client.tls_set(ca_certs=root_cert_filepath) # Replace this with 3rd party cert if that was used when creating registry

#makes program wait for connection on boot
while connected == False:
    connected = checkInternetHttplib()
    print("waiting for connection \n")
    time.sleep(5)

client.connect('mqtt.googleapis.com', 8883)

# Open serial port, restarts program if error occurs
while USBcon == False:
    try:
        ser = serial.Serial(PORT, BAUD_RATE)
        zb = ZigBee(ser, escaped = True)
        USBcon = True
    except Exception as e :       
        print('USB Error')
        restartProgram()

#Variable used for building database entries
currentType = ""
currentPayload = ""
currentTemperature = 0.0
previousTemperature = 0.0
currentHumidity = 0.0
previousHumidity = 0.0
framesReceived = 0
client.loop_start()


#The below code builds the google cloud entries to be published
#the program waits for incoming values and then checks if they have been altered
while True:
     try:
        try:
            data = zb.wait_read_frame()
        
        except Exception as e:
            print("Read Frame Error")       
            print("Trying to reconnect")
            restartProgram()
            
        print("Data Received.\n")
        decoded = decodeReceivedFrame(data)
        
        if type(decoded) is str:
            currentType = str(data['rf_data'],'utf-8')
            #print("currentType =" + currentType)

        else:
            #print("Assign Value for: " + currentType)
            if currentType == "Humidity:" and decoded > 40:
                #print("Assigning Humidity")
                if currentHumidity != decoded:
                    currentHumidity = decoded
                    
            elif currentType == "Temperature:" and decoded < 40:
                #print("Assigning Temperature")
                if currentTemperature != decoded:
                    currentTemperature = decoded
        
        framesReceived+=1

        if currentType != "":
                    
            payload = '{{ "temperature": {}, "humidity": {} }}'.format(currentTemperature, currentHumidity)
                                                                       
            if (currentHumidity != previousHumidity or currentTemperature != previousTemperature) and currentTemperature > 0.0 and currentHumidity > 0.0 and framesReceived >= 4:
                
                framesReceived = 0 
                previousHumidity = currentHumidity
                previousTemperature = currentTemperature
                currentPayload = payload
                print("{} Time: {}\n".format(payload,time.ctime()))              
                client.publish(_MQTT_TOPIC, payload, qos=1)
                
            else:
                print("Values Unchanged.\n")
                if(framesReceived >= 4):
                    framesReceived = 0 
                                                                                                                                                            
        else:
            print("Waiting for data.\n")
            if(framesReceived >= 4):
                framesReceived = 0 
            
     except KeyboardInterrupt:
         break


client.disconnect()
client.loop_stop()