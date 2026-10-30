# Intro

Generates fake air-quality readings for testing.
3 zones (North, East, West), 12 sensors per zone, 36 sensors in total.

Each zone has 4 sensor types, 3 each:

| Type   | Measures                                                    |
| ------ | ----------------------------------------------------------- |
| `PM25` | PM2.5 (µg/m³)                                               |
| `PM10` | PM10 (µg/m³)                                                |
| `GAS`  | O3, NO2, SO2 (ppb), CO (ppm)                                |
| `WX`   | Temperature, humidity, wind speed and direction, visibility |

***All data here is made up. None of it is factual.***

## Simulator Quicksheet

```bash
python3 simulator.py --rounds 1                   # Generate one reading for all 12 sensors
python3 simulator.py --zones west --interval 2       # Generate for West zone only, every 2 seconds
python3 simulator.py --fault west-PM25-02=step       # One sensor breaks: no advisory expected
python3 simulator.py --haze west=high --interval 1   # Change West Zone to high
```

Requires Python 3.10 or newer.

## Sensor names and Data Storage

- Sensor ID: `{zone}-{TYPE}-{unit}`, 
- Example: `west-PM25-02` = 0.2µg/m³ of PM2.5 at West Zone
      
- Each zone gateway sends to its own directory: `haze/{zone}/telemetry`
- Example: `haze/west/telemetry` = send to West/telemetry

## Message format

Every 60 seconds, each zone gateway sends one message with all 12 readings inside.
It is about 2 KB, so IoT Core bills it as one message (billed per 5 KB).

```json
{
  "schema_version": 3,
  "gateway_id": "gateway-west",
  "zone": "west",
  "ts": "2026-10-23T03:20:58.680+00:00",
  "seq": 42,
  "readings": [
    {
      "sensor_id": "west-PM25-02",
      "type": "PM25",
      "ts": "2026-10-23T03:20:58.680+00:00",
      "seq": 42,
      "metrics": {"pm25_ugm3": 18.4}
    }
  ]
}
```

- `seq` goes up by 1 every round. The backend uses it to skip duplicate or late messages.
- If a sensor is offline, it is just missing from the message.

## Test scenarios

| Option               | What happens                                                                                                       | What it checks                            |
| -------------------- | ------------------------------------------------------------------------------------------------------------------ | ----------------------------------------- |
| `--fault ID=drift`   | One sensor slowly gets worse                                                                                       | The other 2 sensors outvote it            |
| `--fault ID=step`    | One sensor jumps high and stays there                                                                              | One bad sensor cannot trigger an advisory |
| `--fault ID=spike`   | One bad reading, then back to normal                                                                               | The 1-hour average smooths it out         |
| `--fault ID=stuck`   | Sensor keeps sending the same values                                                                               | Stuck sensors get flagged                 |
| `--fault ID=offline` | Sensor stops sending                                                                                               | Missing sensors get flagged               |
| `--haze ZONE=level`  | All sensors in the zone rise together over 30 rounds and visibility drops. Levels: `elevated`, `high`, `very_high` | A real haze event triggers an advisory    |

## Run Simulator

```bash
pip install -r requirements.txt
python3 simulator.py --mode mqtt --endpoint <your-iot-endpoint>
```

Put the certificates here:

```
certs/
  AmazonRootCA1.pem
  gateway-north/certificate.pem.crt
  gateway-north/private.pem.key
  gateway-east/...
  gateway-west/...
```

Certificates are secrets. Never commit them. `certs/` is already in `.gitignore`.