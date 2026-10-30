"""Unit tests for the haze sensor simulator. Run from the repo root: pytest"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "simulator"))

import simulator as sim  # noqa: E402


def test_network_is_3_zones_of_12_sensors():
    network = sim.build_network(list(sim.ZONES))
    assert sorted(network) == ["east", "north", "west"]
    assert all(len(sensors) == 12 for sensors in network.values())
    ids = [s.sensor_id for sensors in network.values() for s in sensors]
    assert len(ids) == len(set(ids)) == 36
    assert "west-PM25-02" in ids


def test_batch_fits_in_one_iot_billing_unit():
    network = sim.build_network(["north"])
    batch = sim.build_batch("north", 1, [s.reading() for s in network["north"]])
    assert batch["gateway_id"] == "gateway-north"
    assert len(batch["readings"]) == 12
    assert len(json.dumps(batch).encode()) < 5 * 1024  # IoT Core meters in 5 KB units


def test_normal_pm25_is_in_band_1():
    network = sim.build_network(["east"])
    values = [s.reading()["metrics"]["pm25_ugm3"] for s in network["east"] if s.stype == "PM25"]
    assert all(v <= 55 for v in values)


def test_offline_sensor_is_missing_from_batch():
    network = sim.build_network(["east"])
    sim.apply_faults(network, ["east-GAS-03=offline"])
    readings = [r for r in (s.reading() for s in network["east"]) if r is not None]
    assert len(readings) == 11
    assert "east-GAS-03" not in {r["sensor_id"] for r in readings}


def test_single_sensor_step_affects_only_that_sensor():
    network = sim.build_network(["west"])
    sim.apply_faults(network, ["west-PM25-02=step"])
    pm25 = {s.sensor_id: s.reading()["metrics"]["pm25_ugm3"] for s in network["west"] if s.stype == "PM25"}
    assert pm25["west-PM25-02"] > 150
    assert pm25["west-PM25-01"] <= 55 and pm25["west-PM25-03"] <= 55


def test_haze_event_raises_all_pm25_sensors_in_zone():
    network = sim.build_network(["west"])
    haze = sim.haze_at(sim.HAZE_LEVELS["high"], sim.HAZE_RAMP_ROUNDS)
    readings = [s.reading(haze) for s in network["west"]]
    pm25 = [r["metrics"]["pm25_ugm3"] for r in readings if r["type"] == "PM25"]
    vis = [r["metrics"]["visibility_km"] for r in readings if r["type"] == "WX"]
    assert all(v > 150 for v in pm25)  # all three agree: Band 3 (High)
    assert all(v < 5 for v in vis)


def test_haze_ramps_up_gradually():
    target = sim.HAZE_LEVELS["elevated"]
    assert sim.haze_at(target, 1) < sim.haze_at(target, 15) < sim.haze_at(target, 30) == target


def test_stuck_sensor_repeats_values_with_new_seq():
    network = sim.build_network(["north"])
    sensor = network["north"][0]
    first = sensor.reading()
    sensor.fault = "stuck"
    second = sensor.reading()
    assert second["metrics"] == first["metrics"]
    assert second["seq"] == first["seq"] + 1
