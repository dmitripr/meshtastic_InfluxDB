'''
 *  Meshtastic Node Information upload to InfluxDB v0.2
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
import subprocess
import time
from influxdb import InfluxDBClient

# InfluxDB connection settings
INFLUXDB_HOST = 'localhost'
INFLUXDB_PORT = 8086  # integer, not string
INFLUXDB_USER = 'root'
INFLUXDB_PASSWORD = 'xxxxx'
INFLUXDB_DB = 'meshtastic'

# Meshtastic node
MESH_NODE_HOST = 'mesh_ush1.uska.me'

# Only upload nodes heard within the last TIME_OFFSET seconds
TIME_OFFSET = 900  # in seconds


def escape_tag(value: str) -> str:
    """
    Escape a string for use as an InfluxDB tag value.
    Influx tag escaping rules: spaces, commas, equals, and backslashes must be escaped.
    """
    if value is None:
        return ""
    return (
        str(value)
        .replace('\\', '\\\\')
        .replace(' ', r'\ ')
        .replace(',', r'\,')
        .replace('=', r'\=')
    )


def get_meshtastic_info(host: str) -> str:
    """
    Run the meshtastic CLI and return its stdout as text.
    """
    cmd = ['meshtastic', '--host', host, '--info']

    result = subprocess.run(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True
    )

    if result.returncode != 0:
        print("meshtastic command failed:")
        print(result.stderr)
        raise SystemExit(1)

    return result.stdout


def extract_nodes_json(output: str) -> dict:
    """
    Extract and parse the JSON block between 'Nodes in mesh:' and 'Preferences:'.
    """
    start_marker = 'Nodes in mesh: '
    end_marker = 'Preferences:'

    start_pos = output.find(start_marker)
    end_pos = output.find(end_marker)

    if start_pos == -1 or end_pos == -1:
        print("Couldn't find 'Nodes in mesh:' and/or 'Preferences:' in meshtastic output.")
        print("Raw output for debugging:")
        print(output)
        raise SystemExit(1)

    start_pos += len(start_marker)
    json_chunk = output[start_pos:end_pos].strip()

    # Some versions/outputs may have a trailing comma; safely strip it
    if json_chunk.endswith(','):
        json_chunk = json_chunk[:-1].strip()

    try:
        parsed = json.loads(json_chunk)
    except json.JSONDecodeError as e:
        print("Can't parse JSON from meshtastic output:", e)
        print("First 1000 chars of JSON chunk for debugging:")
        print(json_chunk[:1000])
        raise SystemExit(1)

    return parsed


def main():
    cur_time = time.time()

    # Connect to InfluxDB
    client = InfluxDBClient(
        INFLUXDB_HOST,
        INFLUXDB_PORT,
        INFLUXDB_USER,
        INFLUXDB_PASSWORD,
        INFLUXDB_DB
    )

    # Get raw text from meshtastic
    output = get_meshtastic_info(MESH_NODE_HOST)

    # Parse JSON block
    parsed_json = extract_nodes_json(output)

    data = []

    print("Appending Nodes for DB upload:")

    # Iterate through node entries
    for key, value in parsed_json.items():
        # Defaults to avoid carrying values from previous iterations
        batteryLevel = ""
        voltage = ""
        channelUtilization = ""
        airUtilTx = ""
        uptime = ""

        user = value.get("user", {})
        deviceMetrics = value.get("deviceMetrics", {})

        shortName = str(user.get("shortName", ""))
        snr = str(value.get("snr", ""))
        lastHeard = value.get("lastHeard", 0)

        if deviceMetrics:
            batteryLevel = str(deviceMetrics.get("batteryLevel", ""))
            voltage = str(deviceMetrics.get("voltage", ""))
            channelUtilization = str(deviceMetrics.get("channelUtilization", ""))
            airUtilTx = str(deviceMetrics.get("airUtilTx", ""))
            uptime = str(deviceMetrics.get("uptimeSeconds", ""))

        # Only include nodes heard recently
        if lastHeard > cur_time - TIME_OFFSET:
            # Measurement and tags
            append_string = f"nodeinfo,shortName={escape_tag(shortName)} "

            first_field = True

            def add_field(s: str, name: str, val: str) -> str:
                nonlocal first_field
                if val == "":
                    return s
                if first_field:
                    s += f"{name}={val}"
                    first_field = False
                else:
                    s += f",{name}={val}"
                return s

            append_string = add_field(append_string, "batteryLevel", batteryLevel)
            append_string = add_field(append_string, "voltage", voltage)
            append_string = add_field(append_string, "channelUtilization", channelUtilization)
            append_string = add_field(append_string, "airUtilTx", airUtilTx)
            append_string = add_field(append_string, "uptime", uptime)
            append_string = add_field(append_string, "snr", snr)

            # Timestamp: lastHeard (seconds) converted to nanoseconds
            append_string += f" {int(lastHeard)}000000000"

            print(append_string)
            data.append(append_string)

    if data:
        # Write as line protocol
        client.write(data, {'db': INFLUXDB_DB}, protocol='line')
        print(f"Success! Wrote {len(data)} points.")
    else:
        print("No recent nodes to write.")


if __name__ == "__main__":
    main()

