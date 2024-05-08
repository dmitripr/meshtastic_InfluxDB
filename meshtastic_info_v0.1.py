'''
 *  Meshtastic Node Information upload to InfluxDB v0.1
 *
 * MIT License
 *
 * Copyright (c) 2024 Dmitri Prigojev
 *
 * Permission is hereby granted, free of charge, to any person
 * obtaining a copy of this software and associated documentation
 * files (the "Software"), to deal in the Software without
 * restriction, including without limitation the rights to use,
 * copy, modify, merge, publish, distribute, sublicense, and/or sell
 * copies of the Software, and to permit persons to whom the
 * Software is furnished to do so, subject to the following
 * conditions:
 * 
 * The above copyright notice and this permission notice shall be
 * included in all copies or substantial portions of the Software.
 * 
 * THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND,
 * EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES
 * OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND
 * NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT
 * HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY,
 * WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING
 * FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR
 * OTHER DEALINGS IN THE SOFTWARE.
 */
'''

import json
import os
import subprocess
import time
from influxdb import InfluxDBClient


INFLUXDB_HOST = '192.168.13.14' #ip or hostname
INFLUXDB_PORT = '8086'
INFLUXDB_USER = 'root'
INFLUXDB_PASSWORD = ''
INFLUXDB_DB = 'meshtastic' # databases name
MESH_NODE_HOST = '192.168.2.150'
TIME_OFFSET = 600 # in seconds, upload only nodes heard in the last X seconds

cur_time = time.time()
client = InfluxDBClient(INFLUXDB_HOST, INFLUXDB_PORT, INFLUXDB_USER,INFLUXDB_PASSWORD, INFLUXDB_DB) #InfluxDB client connection details
data = []


cmd = ['meshtastic', '--host', MESH_NODE_HOST, '--info'] #local server command to execute to get the node information
result = subprocess.run(cmd, stdout=subprocess.PIPE)

result = str(result.stdout)

### Clean up the results
start_pos = result.find('Nodes in mesh: ') + len('Nodes in mesh: ')
end_pos = result.find('Preferences:')

### Get only the piece of data with node information
json_chunk = result[start_pos:end_pos]

### Clean up the JSON before parsing
json_chunk_fixed = json_chunk.replace("\\r","")
json_chunk_fixed = json_chunk_fixed.replace("\\n","")

try:
    parsed_json = json.loads(json_chunk_fixed) # Parse JSON
except JSONDecodeError:
    print("Can't parse JSON, no data or bad data received from the local node. Check the node")

print("Appending Nodes for DB upload:")

### Iterate through JSON to get node details
### InfluxDB doesn't handle nulls well, need to check each key to see if it exists and only then append to the string
for key, value in parsed_json.items():
    shortName = str(value["user"].get("shortName",""))
    snr = str(value.get("snr",""))
    lastHeard = value.get("lastHeard",0)
    deviceMetrics = str(value.get("deviceMetrics","")) 
    if deviceMetrics!="": ### See if deviceMetrics is available for the node
        batteryLevel = str(value["deviceMetrics"].get("batteryLevel",""))
        voltage = str(value["deviceMetrics"].get("voltage",""))
        channelUtilization = str(value["deviceMetrics"].get("channelUtilization",""))
        airUtilTx = str(value["deviceMetrics"].get("airUtilTx",""))
        uptime = str(value["deviceMetrics"].get("uptimeSeconds",""))

    #test_heard = cur_time-lastHeard ### For debug
    #print("Test Node: "+shortName+" lastHeard "+str(test_heard)+"sec ago") ### For debug
    
    if lastHeard > cur_time-TIME_OFFSET: ### Check if the node is fresh

        #print(shortName+" Node made it past If") ### For debug
        append_string = "nodeinfo,"+"shortName="+shortName+" " ### Using 'nodeinfo' as the measurement name
        if batteryLevel!="":
            append_string=append_string+"batteryLevel="+batteryLevel
        if voltage!="":
            append_string=append_string+",voltage="+voltage
        if channelUtilization!="":
            append_string=append_string+",channelUtilization="+channelUtilization
        if airUtilTx!="":
            append_string=append_string+",airUtilTx="+airUtilTx
        if uptime!="":
            append_string=append_string+",uptime="+uptime
        if snr!="":
            append_string=append_string+",snr="+snr
            
        append_string=append_string+" "+str(value["lastHeard"])+"000000000" ### add extra zeros to timestamp to accomodate precision of nanoseconds, probably there is an easier way to do this :). Check data in your database to make sure it's being recorded correctly for your setup.
        
        print(append_string)
        data.append(append_string) ### Append the node data to be uploaded

client.write(data,{'db':'meshtastic'},protocol='line') ### Upload to DB information of all recent nodes

print("Success!")
