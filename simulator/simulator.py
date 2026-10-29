#!/usr/bin/env python3
"""
Haze sensor simulator.

Simulates 36 air-quality sensors across 3 monitoring zones in Singapore:
  3 zones (North, East, West) x 4 sensor types x 3 units each.

Sensor types:
  PM25 - fine particulate matter (PM2.5)
  PM10 - coarse particulate matter (PM10)
  GAS  - O3, NO2, SO2 and CO
  WX   - weather: temperature, humidity, wind and visibility

Each zone has one gateway. Every round (default 60 s), the gateway batches the
readings from its 12 sensors into ONE MQTT message, which keeps IoT Core
message volume (and cost) low. Gateways authenticate to AWS IoT Core with
their own X.509 certificate.

All values are synthetic. They do not come from, or represent, any real
monitoring station.

Examples:
  # Print one round of readings locally (no AWS needed)
  python simulator.py --rounds 1

  # A single faulty sensor (should NOT raise a zone advisory)
  python simulator.py --fault W-PM25-02=step --interval 1

  # A real haze event rolling into the West zone (SHOULD raise an advisory)
  python simulator.py --haze W=high --interval 1

  # Publish to AWS IoT Core
  python simulator.py --mode mqtt --endpoint xxxx-ats.iot.ap-southeast-1.amazonaws.com
"""

import argparse
import json
import logging
import random
import signal
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

ZONES = {"N": "North", "E": "East", "W": "West"}
UNITS_PER_TYPE = 3
SCHEMA_VERSION = 3
FAULT_TYPES = ["drift", "step", "spike", "stuck", "offline"]

# Target 1-hr PM2.5 for each haze level (NEA bands: Normal 0-55, Elevated 56-150,
# High 151-250, Very High 251+). PM10 is assumed to be about 1.3x PM2.5 in haze.
HAZE_LEVELS = {"elevated": 100.0, "high": 200.0, "very_high": 300.0}
HAZE_RAMP_ROUNDS = 30  # rounds for a haze event to reach full strength

# Each metric is (mean, noise standard deviation).
# fault_metric is the metric that moves when a single-sensor fault is injected.
PROFILES = {
    "PM25": {
        "metrics": {"pm25_ugm3": (18.0, 3.0)},
        "fault_metric": "pm25_ugm3",
        "fault_direction": +1,
        "drift_per_reading": 1.5,
        "step_size": 150.0,
    },
    "PM10": {
        "metrics": {"pm10_ugm3": (30.0, 4.0)},
        "fault_metric": "pm10_ugm3",
        "fault_direction": +1,
        "drift_per_reading": 2.0,
        "step_size": 180.0,
    },
    "GAS": {
        "metrics": {
            "o3_ppb": (20.0, 3.0),
            "no2_ppb": (15.0, 2.0),
            "so2_ppb": (3.0, 0.5),
            "co_ppm": (0.5, 0.05),
        },
        "fault_metric": "co_ppm",
        "fault_direction": +1,
        "drift_per_reading": 0.05,
        "step_size": 3.0,
    },
    "WX": {
        "metrics": {
            "temp_c": (30.0, 0.5),
            "humidity_pct": (78.0, 3.0),
            "wind_speed_ms": (3.0, 0.8),
            "wind_dir_deg": (180.0, 30.0),
            "visibility_km": (10.0, 0.5),
        },
        "fault_metric": "temp_c",
        "fault_direction": +1,
        "drift_per_reading": 0.1,
        "step_size": 15.0,
    },
}

log = logging.getLogger("simulator")


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


@dataclass
class Sensor:
    sensor_id: str
    zone: str
    stype: str
    fault: str | None = None
    seq: int = 0
    offset: float = 0.0
    last: dict | None = None

    def reading(self, haze: float = 0.0) -> dict | None:
        """Return the next reading, or None if the sensor is offline.

        haze is the zone's current extra PM2.5 (µg/m³) from a haze event.
        """
        self.seq += 1

        if self.fault == "offline":
            return None

        # A stuck sensor keeps reporting, but its values never change.
        if self.fault == "stuck" and self.last is not None:
            msg = dict(self.last)
            msg["ts"] = utc_now()
            msg["seq"] = self.seq
            return msg

        profile = PROFILES[self.stype]
        metrics = {
            name: random.gauss(mean, sd)
            for name, (mean, sd) in profile["metrics"].items()
        }

        # Zone-wide haze affects every sensor in the zone together.
        if haze > 0:
            if self.stype == "PM25":
                metrics["pm25_ugm3"] += haze * random.uniform(0.9, 1.1)
            elif self.stype == "PM10":
                metrics["pm10_ugm3"] += 1.3 * haze * random.uniform(0.9, 1.1)
            elif self.stype == "GAS":
                metrics["co_ppm"] += haze / 200.0
            elif self.stype == "WX":
                metrics["visibility_km"] = max(0.5, metrics["visibility_km"] - haze / 30.0)

        fault_metric = profile["fault_metric"]
        direction = profile["fault_direction"]

        if self.fault == "drift":
            # Gradual sensor degradation, e.g. a dirty optical chamber.
            self.offset += profile["drift_per_reading"] * direction
        elif self.fault == "step":
            # One sensor jumps and stays there, e.g. a failed component.
            self.offset = profile["step_size"] * direction
        elif self.fault == "spike":
            # A single bad reading. Good alerting should NOT advise on this alone.
            metrics[fault_metric] += profile["step_size"] * direction
            self.fault = None

        metrics[fault_metric] += self.offset

        for name in metrics:
            value = max(0.0, metrics[name])
            if name.endswith("_pct"):
                value = min(100.0, value)
            if name == "wind_dir_deg":
                value = value % 360
            metrics[name] = round(value, 2)

        msg = {
            "sensor_id": self.sensor_id,
            "type": self.stype,
            "ts": utc_now(),
            "seq": self.seq,
            "metrics": metrics,
        }
        self.last = msg
        return msg


def gateway_topic(zone: str) -> str:
    return f"haze/{zone}/telemetry"


def build_batch(zone: str, gateway_seq: int, readings: list[dict]) -> dict:
    """One message per gateway per round. Offline sensors are simply absent."""
    return {
        "schema_version": SCHEMA_VERSION,
        "gateway_id": f"gateway-{zone}",
        "zone": zone,
        "ts": utc_now(),
        "seq": gateway_seq,
        "readings": readings,
    }


def build_network(zones: list[str]) -> dict[str, list[Sensor]]:
    """Return sensors grouped by zone, e.g. W-PM25-02."""
    return {
        zone: [
            Sensor(f"{zone}-{stype}-{unit:02d}", zone, stype)
            for stype in PROFILES
            for unit in range(1, UNITS_PER_TYPE + 1)
        ]
        for zone in zones
    }


class StdoutPublisher:
    def publish(self, topic: str, payload: str) -> None:
        print(json.dumps({"topic": topic, "payload": json.loads(payload)}))

    def close(self) -> None:
        pass


class MqttPublisher:
    """One MQTT connection per zone gateway, authenticated with its own certificate."""

    def __init__(self, zone: str, endpoint: str, certs_dir: Path):
        import paho.mqtt.client as mqtt

        client_id = f"gateway-{zone}"
        cert_dir = certs_dir / client_id
        self.client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=client_id)
        self.client.tls_set(
            ca_certs=str(certs_dir / "AmazonRootCA1.pem"),
            certfile=str(cert_dir / "certificate.pem.crt"),
            keyfile=str(cert_dir / "private.pem.key"),
        )
        self.client.on_connect = lambda c, u, f, rc, p: log.info("%s connected: %s", client_id, rc)
        self.client.on_disconnect = lambda c, u, f, rc, p: log.warning("%s disconnected: %s", client_id, rc)
        self.client.connect(endpoint, port=8883, keepalive=60)
        self.client.loop_start()

    def publish(self, topic: str, payload: str) -> None:
        self.client.publish(topic, payload, qos=1)

    def close(self) -> None:
        self.client.loop_stop()
        self.client.disconnect()


def parse_zones(text: str) -> list[str]:
    zones = [z.strip().upper() for z in text.split(",") if z.strip()]
    for zone in zones:
        if zone not in ZONES:
            raise argparse.ArgumentTypeError(f"zone {zone} not in {list(ZONES)}")
    return zones


def apply_faults(network: dict[str, list[Sensor]], specs: list[str]) -> None:
    by_id = {s.sensor_id: s for sensors in network.values() for s in sensors}
    for spec in specs:
        sensor_id, _, fault = spec.partition("=")
        if sensor_id not in by_id:
            sys.exit(f"Unknown sensor in --fault: {sensor_id}")
        if fault not in FAULT_TYPES:
            sys.exit(f"Unknown fault '{fault}'. Choose from {FAULT_TYPES}")
        by_id[sensor_id].fault = fault
        log.info("Injected %s fault on %s", fault, sensor_id)


def parse_haze(specs: list[str], zones: list[str]) -> dict[str, float]:
    """--haze W=high  ->  {"W": 200.0} (target extra PM2.5 for that zone)."""
    targets = {}
    for spec in specs:
        zone, _, level = spec.partition("=")
        zone = zone.upper()
        if zone not in zones:
            sys.exit(f"--haze zone {zone} is not being simulated ({zones})")
        if level not in HAZE_LEVELS:
            sys.exit(f"Unknown haze level '{level}'. Choose from {list(HAZE_LEVELS)}")
        targets[zone] = HAZE_LEVELS[level]
        log.info("Haze event in %s zone, ramping to about %s µg/m³ PM2.5", ZONES[zone], HAZE_LEVELS[level])
    return targets


def haze_at(target: float, round_no: int) -> float:
    """Haze builds up gradually over HAZE_RAMP_ROUNDS rounds."""
    return target * min(1.0, round_no / HAZE_RAMP_ROUNDS)


def main() -> None:
    parser = argparse.ArgumentParser(description="Haze sensor simulator")
    parser.add_argument("--mode", choices=["stdout", "mqtt"], default="stdout")
    parser.add_argument("--endpoint", help="AWS IoT Core ATS endpoint (mqtt mode)")
    parser.add_argument("--certs-dir", type=Path, default=Path("certs"))
    parser.add_argument("--zones", type=parse_zones, default=list(ZONES), help="e.g. N,E,W or W")
    parser.add_argument("--interval", type=float, default=60.0, help="seconds between rounds")
    parser.add_argument("--rounds", type=int, default=0, help="0 = run forever")
    parser.add_argument("--fault", action="append", default=[], help="SENSOR_ID=fault, repeatable")
    parser.add_argument("--haze", action="append", default=[],
                        help="ZONE=level (elevated, high, very_high), repeatable")
    parser.add_argument("--random-fault-rate", type=float, default=0.0,
                        help="chance per sensor per round of starting a random fault")
    parser.add_argument("--seed", type=int, help="random seed for repeatable runs")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s",
                        stream=sys.stderr)

    if args.seed is not None:
        random.seed(args.seed)
    if args.mode == "mqtt" and not args.endpoint:
        parser.error("--endpoint is required in mqtt mode")

    network = build_network(args.zones)
    apply_faults(network, args.fault)
    haze_targets = parse_haze(args.haze, args.zones)

    if args.mode == "mqtt":
        publishers = {z: MqttPublisher(z, args.endpoint, args.certs_dir) for z in network}
    else:
        stdout = StdoutPublisher()
        publishers = {z: stdout for z in network}

    running = True

    def stop(*_):
        nonlocal running
        running = False

    signal.signal(signal.SIGINT, stop)
    signal.signal(signal.SIGTERM, stop)

    sensor_count = sum(len(s) for s in network.values())
    log.info("Simulating %d sensors in zones %s every %ss", sensor_count, list(network), args.interval)

    rounds = 0
    try:
        while running:
            started = time.monotonic()
            for zone, sensors in network.items():
                haze = haze_at(haze_targets.get(zone, 0.0), rounds + 1)
                readings = []
                for sensor in sensors:
                    if sensor.fault is None and random.random() < args.random_fault_rate:
                        sensor.fault = random.choice(FAULT_TYPES)
                        log.info("Random %s fault started on %s", sensor.fault, sensor.sensor_id)
                    msg = sensor.reading(haze)
                    if msg is not None:
                        readings.append(msg)
                batch = build_batch(zone, rounds + 1, readings)
                publishers[zone].publish(gateway_topic(zone), json.dumps(batch))

            rounds += 1
            if args.rounds and rounds >= args.rounds:
                break
            time.sleep(max(0.0, args.interval - (time.monotonic() - started)))
    finally:
        for publisher in set(publishers.values()):
            publisher.close()
        log.info("Stopped after %d rounds", rounds)


if __name__ == "__main__":
    main()
