import paho.mqtt.client as mqtt
import requests
import logging
from threading import Thread, Lock, Event
import serial
import base64
import json
import sys
import time
import datetime
import pandas as pd
from pandas.io.json import json_normalize
from pyACS.acs import ACS as ACSParser
from pyACS.acs import FrameIncompleteError, NumberWavelengthIncorrectError

ATTRIBUTES_TOPIC = 'v1/devices/me/attributes'
TELEMETRY_TOPIC = 'v1/devices/me/telemetry'
RPC_TOPIC = 'v1/devices/me/rpc'

class Inlinino:
    REST_API_PORT = 8080

    def __init__(self, host, username, password, host_device_id, rest_token=None, device_name_list=None):
        self.log = logging.getLogger('Inlinino')
        # REST API Init
        self._host = host
        self.__rest_username = username
        self.__rest_password = password
        self._host_device_id = host_device_id
        if rest_token is None:
            self.get_rest_token()
        else:
            self._rest_token = rest_token

        # Init MQTT
        self.tb_connected = False
        self.tb = mqtt.Client()
        self.tb.on_connect = self.on_connect
        self.tb.on_disconnect = self.on_disconnect
        self.tb.on_message = self.on_message
        # self.tb.on_publish = self.on_publish
        # self.tb.on_log = self.on_log
        try:
            response = requests.get('http://' + self._host + ':' + str(self.REST_API_PORT) +
                                             '/api/device/' + self._host_device_id + '/credentials',
                                             headers={'Content-Type': 'application/json', 'Accept': 'application/json',
                                                      'X-Authorization': 'Bearer ' + self._rest_token}).json()
            self.tb.username_pw_set(response["credentialsId"])
        except requests.exceptions.ConnectionError:
            self.log.error('Host not reachable.')
            raise
        except KeyError:
            if response['status'] == 401:
                self.log.error('Invalid credentials.')
                raise
            else:
                raise

        # Device init
        self._lock = Lock()
        if device_name_list is None:
            attributes = requests.get('http://' + self._host + ':' + str(self.REST_API_PORT) +
                                      '/api/plugins/telemetry/DEVICE/' + self._host_device_id + '/keys/attributes',
                                      headers={'Content-Type': 'application/json', 'Accept': 'application/json',
                                               'X-Authorization': 'Bearer ' + self._rest_token}).json()
            self.devices = {d[0:-3]: None for d in attributes if d.endswith('_id')}
        else:
            self.devices = {d: None for d in device_name_list}

        # Export init
        self.export_keys = None
        self.export_dt_start = None
        self.export_dt_end = None

    def get_rest_token(self):
        try:
            response = requests.post('http://' + self._host + ':' + str(self.REST_API_PORT) + '/api/auth/login',
                                             data='{"username":"' + self.__rest_username + '", "password":"' + self.__rest_password + '"}',
                                             headers={'Content-Type': 'application/json', 'Accept': 'application/json'}).json()

            self._rest_token = response['token']
        except requests.exceptions.ConnectionError:
            self.log.error('Host not reachable.')
            raise
        except KeyError:
            if response['status'] == 401:
                self.log.error('Invalid credentials.')
                raise
            else:
                raise
        # print(self._rest_token)

    # def get_device_list(self):
    #     """ Initialize devices from ThingsBoard Shared Attributes using REST API """
    #     # Query REST API to get all attributes keys
    #     # Get list of devices from every attributes ending by _token
    #     attributes = requests.get('http://' + self._host + ':' + str(self.REST_API_PORT) + '/api/plugins/telemetry/DEVICE/' + self.device_id + '/keys/attributes',
    #                               headers={'Content-Type': 'application/json', 'Accept': 'application/json', 'X-Authorization': 'Bearer ' + self._rest_token}).json()
    #     self.devices = {d[0:-6]:None for d in attributes if d.endswith('_id')}
    #     # Get values of specific attributes
    #     # query_attributes = ','.join(
    #     #     [d + '_active' for d in self.devices.keys()] + [d + '_token' for d in self.devices.keys()])
    #     # response = requests.get('http://' + self.host + ':' + str(
    #     #     self.REST_API_PORT) + '/api/plugins/telemetry/DEVICE/' + device_id + '/values/attributes?keys=' + query_attributes,
    #     #                         headers={'Content-Type': 'application/json', 'Accept': 'application/json',
    #     #                                  'X-Authorization': 'Bearer ' + rest_token}).json()
    #     # Get all attributes keys and values
    #     # response = requests.get('http://' + self.host + ':' + str(self.REST_API_PORT) + '/api/plugins/telemetry/DEVICE/' + device_id + '/values/attributes',
    #     #                         headers={'Content-Type': 'application/json', 'Accept': 'application/json', 'X-Authorization': 'Bearer ' + rest_token}).json()
    #     # print(response)

    def get_devices_attributes(self):
        """ Get values of token and active for each device """
        # Use MQTT in case of update on ThingsBoard
        attribute_keys = [d + '_active' for d in self.devices.keys()] +\
                         [d + '_id' for d in self.devices.keys()] +\
                         ['export_dt_start', 'export_dt_end', 'export_keys']
        self.get_attributes(attribute_keys)

    def set_device(self, device_name, device_id):
        if self.devices[device_name] is None:
            self.init_device(device_name, device_id)
        elif self.devices[device_name].device_id != device_id:
            # Get current instrument state
            was_alive = self.devices[device_name].alive
            # Stop instrument
            self.devices[device_name].stop()
            # Assign instrument to new device
            # self.devices[device_name].mqtt.username_pw_set(device_token)
            self.init_device(device_name, device_id)
            # Restore previous state of instrument
            if was_alive:
                self.devices[device_name].start()
        else:
            self.log.info('This case should never happen.')

    def init_device(self, device_name, device_id):
        # Get device type
        device_type = requests.get('http://' + self._host + ':' + str(self.REST_API_PORT) + '/api/device/' + device_id,
                                   headers={'Content-Type': 'application/json', 'Accept': 'application/json',
                                            'X-Authorization': 'Bearer ' + self._rest_token}).json()["type"]
        device_token = requests.get('http://' + self._host + ':' + str(self.REST_API_PORT) + '/api/device/' + device_id + '/credentials',
                                    headers={'Content-Type': 'application/json', 'Accept': 'application/json',
                                    'X-Authorization': 'Bearer ' + self._rest_token}).json()["credentialsId"]
        # Initialize device
        if device_type in ['ACS']:
            self.devices[device_name] = ACS(device_name, device_id, self._host, device_token)
        elif device_type in ['ECO', 'ECO-BB3', 'SBE19+']:
            self.devices[device_name] = ECO(device_name, device_id, self._host, device_token)
        else:
            self.log.error('Unknown device type: ' + device_type + '. Unable to initialize device: ' + device_name + '.')

    def get_device_telemetry(self, device_id):
        # # Get export keys
        # export_keys = requests.get('http://' + self._host + ':' + str(self.REST_API_PORT) +
        #                           '/api/plugins/telemetry/DEVICE/' + device_id + '/values/attributes?keys=export_keys',
        #                           headers={'Content-Type': 'application/json', 'Accept': 'application/json',
        #                                    'X-Authorization': 'Bearer ' + self._rest_token}).json()["value"]
        # if export_keys:
        #     export_keys = [s.strip() for s in export_keys.split(',')]
        # else:
        #     # Get all timeseries keys from device
        #     export_keys = requests.get('http://' + self._host + ':' + str(self.REST_API_PORT) +
        #                                '/api/plugins/telemetry/DEVICE/' + device_id + '/keys/timeseries',
        #                                headers={'Content-Type': 'application/json', 'Accept': 'application/json',
        #                                         'X-Authorization': 'Bearer ' + self._rest_token}).json()
        export_keys_str = ','.join(self.export_keys)
        # Get device name
        device_name = requests.get('http://' + self._host + ':' + str(self.REST_API_PORT) + '/api/device/' + device_id,
                                   headers={'Content-Type': 'application/json', 'Accept': 'application/json',
                                            'X-Authorization': 'Bearer ' + self._rest_token}).json()["name"]
        # Get timeseries
        ts = requests.get('http://' + self._host + ':' + str(self.REST_API_PORT) +
                          '/api/plugins/telemetry/DEVICE/' + device_id + '/values/timeseries?' +
                          'limit=864000&keys=' + export_keys_str + '&startTs=' + str(self.export_dt_start) + '&endTs=' + str(self.export_dt_end),
                          headers={'Content-Type': 'application/json', 'Accept': 'application/json',
                                   'X-Authorization': 'Bearer ' + self._rest_token}).json()

        export_dt_start_str = datetime.datetime.fromtimestamp(self.export_dt_start / 1000).strftime('%Y%m%d%H%M%S')
        export_dt_end_str = datetime.datetime.fromtimestamp(self.export_dt_start / 1000).strftime('%Y%m%d%H%M%S')
        if ts:
            filename = device_name + '_' + str(export_dt_start_str) + '-' + str(export_dt_end_str) + '.csv'
            # Reformat and write data (pandas >= 0.25)
            # ts = pd.concat([json_normalize(ts, record_path=k).set_index('ts').rename(columns={'value': k})
            #                 for k in ts.keys()], axis=1, sort=True)
            # ts.index = pd.to_datetime(ts.index, unit='ms')  # Not supported on pandas 0.22.0
            # ts.to_csv(filename, date_format='%Y/%m/%d %H:%M:%S', na_rep='NaN')  # Export index
            # Reformat and write data (pandas >= 0.22)
            ts = pd.concat([json_normalize(ts, record_path=k).set_index('ts').rename(columns={'value': k})
                            for k in ts.keys()], axis=1)
            ts.insert(0, 'dt', pd.to_datetime(ts.index, unit='ms'))
            ts.to_csv(filename, date_format='%Y/%m/%d %H:%M:%S.%f', na_rep='NaN', index=False)
            self.log.info('Wrote data for ' + device_name + ' from ' + export_dt_start_str + ' to ' + export_dt_end_str)
            return filename
        else:
            self.log.warning('No data for ' + device_name + ' from ' + export_dt_start_str + ' to ' + export_dt_end_str)

    def connect(self):
        """ Connect to MQTT server """
        self.tb.connect(self._host, 1883, 60)
        self.tb.loop_start()

    def disconnect(self):
        """ Disconnect from MQTT server """
        self.tb.loop_stop()
        self.tb.disconnect()

    def on_connect(self, client, userdata, flags, rc):
        self.tb_connected = True
        self.log.debug('Client connected.')
        self.tb.subscribe(ATTRIBUTES_TOPIC, qos=1)
        self.tb.subscribe(ATTRIBUTES_TOPIC + "/response/+", 1)
        self.tb.subscribe(RPC_TOPIC + '/request/+')
        self.get_devices_attributes()

    def on_disconnect(self, client, userdata, rc):
        self.tb_connected = False
        self.log.debug('Client disconnected.')

    def on_message(self, client, userdata, message):
        content = json.loads(message.payload.decode("utf-8"))
        # print(content)
        if message.topic == ATTRIBUTES_TOPIC or message.topic.startswith(ATTRIBUTES_TOPIC + "/response/"):
            if 'shared' in content:
                content = content['shared']
            with self._lock:
                # Classify received messages
                id_content = {}
                active_content = {}
                export_content = {}
                for k, v in content.items():
                    if k.endswith('_id'):
                        id_content[k[0:-3]] = v
                    elif k.endswith('_active'):
                        active_content[k[0:-7]] = v
                    elif k.startswith('export_'):
                        export_content[k[7:]] = v
                    else:
                        self.log.warning('Attribute unknown ' + k)

                # Set or Update token (need to be done first to initialize all the devices)
                for k, v in id_content.items():
                    self.set_device(k, v)

                # Start or stop device
                for k, v in active_content.items():
                    if v and not self.devices[k].alive:
                        self.devices[k].start()
                    elif not v and self.devices[k].alive:
                        self.devices[k].stop()

                # Configure export parameters
                for k, v in export_content.items():
                    if k == 'dt_start':
                        self.export_dt_start = int(datetime.datetime.strptime(v, '%Y-%m-%dT%H:%M:%S.%fZ').replace(tzinfo=datetime.timezone.utc).timestamp() * 1000)
                    elif k == 'dt_end':
                        self.export_dt_end = int(datetime.datetime.strptime(v, '%Y-%m-%dT%H:%M:%S.%fZ').replace(tzinfo=datetime.timezone.utc).timestamp() * 1000)
                    elif k == 'keys':
                        self.export_keys = [s.strip() for s in v.split(',')]
                    else:
                        self.log.warning('Attribute unknown export_' + k)
        elif message.topic.startswith(RPC_TOPIC + '/request/'):
            if 'method' in content:
                if content['method'] == 'exportData':
                    filename = self.get_device_telemetry(json.loads(content['params'])['device_id'])
                    request_id = message.topic.rsplit('/', 1)[-1]
                    if filename is None:
                        self.rpc_response(request_id, 'Failed')
                    else:
                        self.rpc_response(request_id, filename)
        else:
            self.log.debug('Ignored message: ' + message.topic)

    def on_publish(self, client, obj, mid):
        self.log.debug('Client published mid: ' + str(mid))

    def on_log(self, client, userdata, level, buf):
        self.log.debug(buf)

    def send_telemetry(self, data):
        """ Send data with MQTT """
        if self.tb_connected:
            self.tb.publish(TELEMETRY_TOPIC, json.dumps(data), 1)
        else:
            self.log.error('Unable to send telemetry: client disconnected.')

    def set_attributes(self, data):
        if self.tb_connected:
            self.tb.publish(ATTRIBUTES_TOPIC, json.dumps(data), 1)
        else:
            self.log.error('Unable to set attributes: client disconnected.')

    def get_attributes(self, keys):
        if self.tb_connected:
            self.tb.publish(ATTRIBUTES_TOPIC + '/request/1', json.dumps({"sharedKeys": ','.join(keys)}), 1)
        else:
            self.log.error('Unable to get attributes: client disconnected.')

    def rpc_response(self, request_id, message):
        if self.tb_connected:
            self.tb.publish(RPC_TOPIC + '/response/' + request_id, json.dumps({'message': message}), 1)
        else:
            self.log.error('Unable to get attributes: client disconnected.')


class Instrument:

    MAX_BUFFER_LENGTH = 8000
    ATTRIBUTE_LIST = 'serial_port,serial_baudrate,serial_timeout,registration_bytes,bytes_to_read,send_raw'

    def __init__(self, name, device_id, mqtt_host, mqtt_token, serial_port=None, serial_baudrate=19200, serial_timeout=3,
                 registration_bytes=b'\n', bytes_to_read=32):
        self.log = logging.getLogger(name)
        self.device_id = device_id
        # Set MQTT
        self.mqtt_connected = False
        self.mqtt_host = mqtt_host
        self.mqtt = mqtt.Client()
        self.mqtt.username_pw_set(mqtt_token)
        self.mqtt.on_connect = self.mqtt_on_connect
        self.mqtt.on_disconnect = self.mqtt_on_disconnect
        self.mqtt.on_message = self.mqtt_on_message
        # self.mqtt.on_publish = self.mqtt_on_publish
        # self.mqtt.on_log = self.mqtt_on_log
        self.send_raw = True
        self.attributes_to_get = ''
        self._lock = Lock()
        # Set serial port
        self.registration_bytes = registration_bytes
        self.bytes_to_read = bytes_to_read
        self.serial = None
        self.serial_connected = False
        self.serial_cfg = {'port': serial_port, 'baudrate': serial_baudrate, 'timeout': serial_timeout}
        self.serial_cfg_rx_event = Event()
        self.serial_cfg_init = False
        if serial_port is None:
            self.serial_cfg_force = False
        else:
            self.serial_cfg_force = True
        # Set reading thread
        self.alive = False
        self._buffer = bytearray()
        self.thread = None

    def start(self):
        self.log.debug('Starting instrument')
        # Connect ThingsBoard
        if not self.mqtt_connected:
            self.mqtt.connect(self.mqtt_host, 1883, 60)
            self.mqtt.loop_start()
        # Initialize serial connection
        if not self.serial_connected:
            # Get serial configuration (if not forced)
            if not self.serial_cfg_force:
                if not self.serial_cfg_init:
                    # Wait to receive serial configuration through MQTT (timeout of 5 s) for the first time
                    if not self.serial_cfg_rx_event.wait(5):
                        self.log.error('Did not receive serial configuration.')
                        return
                    self.serial_cfg_init = True
                self.serial_cfg_rx_event.clear()
                if self.serial_cfg['port'] is None:
                    self.log.error('Serial port undefined on client.')
                    return
            self.log.debug(self.serial_cfg)
            # Connect to serial port
            try:
                self.serial = serial.serial_for_url(self.serial_cfg['port'],
                                                    baudrate=self.serial_cfg['baudrate'],
                                                    timeout=self.serial_cfg['timeout'])
                self.serial_connected = True
                self.log.debug("Serial port %s:%d open." % (self.serial_cfg['port'], self.serial_cfg['baudrate']))
            except serial.SerialException as e:
                self.log.error("Could not open serial port {}".format(self.serial_cfg['port']))
                return
        # Start reading thread
        if not self.alive:
            self.alive = True
            self.thread = Thread(target=self.run)
            self.thread.daemon = True
            self.thread.start()

    def restart_serial(self):
        self.log.debug('Restart serial connection.')
        # Stop serial connection (we're in reader thread so can't stop it)
        self.stop(thread=False, mqtt=False)
        # Empty serial buffer
        self._buffer = bytearray()
        # Open serial port with updated configuration
        self.start()

    def stop(self, thread=True, serial=True, mqtt=True):
        self.log.debug('Stopping instrument')
        if thread and self.alive:
            self.alive = False
            self.thread.join()
            self.log.debug('Reader thread stopped.')
        if serial and self.serial_connected:
            self.serial.close()
            self.serial_connected = False
            self.log.debug("Serial port %s:%d closed." % (self.serial.port, self.serial.baudrate))
        if mqtt and self.mqtt_connected:
            self.mqtt.loop_stop()
            self.mqtt.disconnect()

    def get_serial_cfg(self):
        if self.mqtt_connected:
            self.mqtt.publish(ATTRIBUTES_TOPIC + '/request/1', json.dumps({"sharedKeys": self.ATTRIBUTE_LIST}), 1)
        else:
            self.log.error('Unable to get serial cfg: client disconnected.')

    def mqtt_on_connect(self, client, userdata, flags, rc):
        self.mqtt_connected = True
        self.log.debug("MQTT connected.")
        if not self.serial_cfg_force:
            self.mqtt.subscribe(ATTRIBUTES_TOPIC, qos=1)
            self.mqtt.subscribe(ATTRIBUTES_TOPIC + "/response/+", 1)
            self.get_serial_cfg()

    def mqtt_on_disconnect(self, client, userdata, rc):
        self.mqtt_connected = False
        self.log.debug("MQTT disconnected.")

    def mqtt_on_message(self, client, userdata, message):
        content = json.loads(message.payload.decode("utf-8"))
        # self.log.debug(content)
        if message.topic == ATTRIBUTES_TOPIC or message.topic.startswith(ATTRIBUTES_TOPIC + "/response/"):
            if 'shared' in content:
                content = content['shared']
            with self._lock:
                # Update Serial Configuration
                rx_serial_cfg = False
                for k, v in content.items():
                    if k.startswith('serial_'):
                        self.serial_cfg[k[7:]] = v
                        rx_serial_cfg = True  # Restart serial connection
                    elif k == 'registration_bytes':
                        # convert hexadecimal string to bytearray (to get hexadecimal string do: b'\n'.hex() )
                        self.registration_bytes = bytes.fromhex(v)
                    elif k == 'bytes_to_read':
                        # 1024 is good for ACS, 32 is good for BB3
                        self.bytes_to_read = v
                    elif k == 'send_raw':
                        # send raw values encoded in base64
                        self.send_raw = v
                    else:
                        self.mqtt_message_key_parser(k, v)
                if rx_serial_cfg:
                    self.serial_cfg_rx_event.set()
        else:
            self.log.debug('Ignored message: ' + message.type)

    def mqtt_message_key_parser(self, key, value):
        pass

    def mqtt_on_log(self, client, userdata, level, buf):
        self.log.debug(buf)

    def run(self):
        """Loop forever on serial instance"""
        self.log.debug('Reader thread started.')
        while self.alive:
            try:
                data = self.serial.read(self.bytes_to_read)
                self.data_read(data)
                if self.serial_cfg_rx_event.is_set():
                    self.restart_serial()
                if len(self._buffer) > self.MAX_BUFFER_LENGTH:
                    self.log.error('Buffer exceeded maximum length. Buffer emptied to prevent overflow')
                    self._buffer = bytearray()
            except serial.SerialException as e:
                self.log.error(e)
                self.alive = False
        # self.handle_last_frame(self.buffer)  # Incomplete frame

    def data_read(self, data):
        """ Separate each frame """
        # Does not send registration bytes with the frame to handle_frame
        # Might need to use lock here as it could generate unexpected behaviour when self.registration is modified
        self._buffer.extend(data)
        while self.registration_bytes in self._buffer:
            frame, self._buffer = self._buffer.split(self.registration_bytes, 1)
            if frame:
                self.handle_frame(frame)

    def handle_frame(self, frame):
        """ Encode frame in Base64 ASCII and send it to server """
        ts = int(time.time() * 1000)
        self.mqtt.publish(TELEMETRY_TOPIC, json.dumps({'ts': ts, 'values': {'frame': base64.b64encode(frame).decode('ascii')}}), 1)
        # self.mqtt.publish(TELEMETRY_TOPIC, json.dumps({'frame': base64.b64encode(frame).decode('ascii')}), 1)  # ThingsBoard timestamp

    def handle_last_frame(self, frame):
        return self.handle_frame(frame)


class ACS(Instrument):

    ATTRIBUTE_LIST = 'serial_port,serial_baudrate,serial_timeout,registration_bytes,bytes_to_read,send_raw,device_file'

    def __init__(self, name, device_id, mqtt_host, mqtt_token, device_file=None, serial_port=None, serial_baudrate=115200, serial_timeout=3,
             registration_bytes=b'\xff\x00\xff\x00', bytes_to_read=512):
        self.parser = ACSParser(device_file)
        Instrument.__init__(self, name, device_id, mqtt_host, mqtt_token, serial_port, serial_baudrate, serial_timeout,
             registration_bytes, bytes_to_read)

    def mqtt_message_key_parser(self, key, value):
        if key == 'device_file':
            self.parser.read_device_file(value)

    def handle_frame(self, frame):
        ts = int(time.time()*1000)  # Host timestamp different from ACS internal timestamp
        if self.send_raw:
            self.mqtt.publish(TELEMETRY_TOPIC,
                              json.dumps({'ts': ts, 'values': {'frame': base64.b64encode(frame).decode('ascii')}}), 1)
        try:
            raw_frame = self.parser.unpack_frame(self.registration_bytes + frame)
            cal_frame = self.parser.calibrate_frame(raw_frame, True)  # return tuple (c, a, int_t_su, ext_t_su)
            values = {'timestamp': raw_frame.time_stamp,
                      'internal_temperature_su': cal_frame[2], 'external_temperature_su': cal_frame[3]}
            # To intense for RPi (runs at 100 %)
            # values.update({'c' + str(l): d for l, d in zip(self.parser.lambda_c, cal_frame[0])})
            # values.update({'a'+str(l): d for l, d in zip(self.parser.lambda_a, cal_frame[1])})
            self.mqtt.publish(TELEMETRY_TOPIC,
                              json.dumps({'ts': ts, 'values': values}), 1)
        except FrameIncompleteError as e:
            self.log.warning(e)
        except NumberWavelengthIncorrectError as e:
            self.log.warning('Number of wavelength incorrect. Likely due to invalid device file.')


class ECO(Instrument):

    ATTRIBUTE_LIST = 'serial_port,serial_baudrate,serial_timeout,registration_bytes,bytes_to_read,send_raw,str_separator,var_columns,var_types,expected_n_var'

    def __init__(self, name, device_id, mqtt_host, mqtt_token, serial_port=None, serial_baudrate=19200, serial_timeout=5,
                 registration_bytes=b'\r\n', bytes_to_read=16,
                 str_separator='\t', var_columns=[3, 5, 7], var_types=['int', 'int', 'int']):
        self.str_separator = str_separator
        self.var_columns = var_columns
        self.var_types = var_types
        self.expected_n_var = None
        Instrument.__init__(self, name, device_id, mqtt_host, mqtt_token, serial_port, serial_baudrate, serial_timeout,
             registration_bytes, bytes_to_read)

    def mqtt_message_key_parser(self, key, value):
        if key == 'str_separator':
            self.str_separator = value
        elif key == 'var_columns':
            self.var_columns = [int(v) for v in value.split(',')]
        elif key == 'var_types':
            self.var_types = value.split(',')
        elif key == 'expected_n_var':
            self.expected_n_var = value

    def handle_frame(self, frame):
        ts = int(time.time()*1000)
        if self.send_raw:
            self.mqtt.publish(TELEMETRY_TOPIC,
                              json.dumps({'ts': ts, 'values': {'frame': base64.b64encode(frame).decode('ascii')}}), 1)
        try:
            raw = frame.decode('ascii').split(self.str_separator)
            if self.expected_n_var:
                if len(raw) != self.expected_n_var:
                    self.log.warning('Invalid data format. Unexpected number of variables.')
                    return
            data = dict()
            for i, (c, t) in enumerate(zip(self.var_columns, self.var_types)):
                if t == 'int':
                    data['c' + str(i)] = int(raw[c])
                elif t == 'float':
                    data['c' + str(i)] = float(raw[c])
                elif t == 'bool':
                    data['c' + str(i)] = bool(raw[c])
                else:
                    data['c' + str(i)] = raw[c]
            self.mqtt.publish(TELEMETRY_TOPIC, json.dumps({'ts': ts, 'values': data}), 1)
        except IndexError:
            self.log.warning('Index out of range. Check var_columns.')
        except TypeError:
            self.log.warning('Invalid data format. Check var_types or var.')
        except UnicodeDecodeError:
            self.log.warning('Invalid data format. Unable to decode frame.')
        except:
            self.log.error(sys.exc_info()[0])


if __name__ == '__main__':
    import Inlinino_cfg as cfg

    logging.basicConfig(level=cfg.logging_level)

    # Test Instrument Class
    # device_file = '~/Data/EXPORTS/DeviceFiles/acs301.dev'
    # serial_port = '/dev/tty.usbserial-DN01YOW4'  # RerBoard
    # serial_port = '/dev/tty.SLAB_USBtoUART'  # ESP8266
    # serial_port = '/dev/tty.usbmodem144101'  # Arduino Micro
    # serial_baudrate = 115200
    # registration = b'\xff\x00\xff\x00'
    #
    # # Force serial configuration at initialization
    # # acs = Instrument('ACS301', cfg.tb_host, cfg.acs_token, serial_port, serial_baudrate, registration=registration)
    # # Get serial configuration from ThingsBoard
    # acs = Instrument('ACS301', cfg.tb_host, cfg.acs_token, registration=registration)
    # # Get serial configuration from ThingsBoard and decode before sending
    # acs = ACS('ACS301', cfg.acs_device_id, cfg.tb_host, cfg.acs_token, device_file, serial_port=serial_port)
    # # Test BB3
    # acs = ECO('BB3349', '', cfg.tb_host, cfg.bb3_token, serial_port=serial_port)
    # acs.start()
    # try:
    #     sleep(150)
    # except KeyboardInterrupt:
    #     logging.info('stopping ...')
    # acs.stop()

    # Run Inlinino
    core = Inlinino(cfg.tb_host, cfg.tb_user, cfg.tb_pwd, cfg.tb_device_id)
    core.connect()
    try:
        core.tb._thread.join()
    except KeyboardInterrupt:
        logging.info('stopping ...')
    core.disconnect()

