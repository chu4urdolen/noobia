#!/usr/bin/env python3
"""Bounded, unpaired Nexus BLE PING/INFO to Lynx's GATT endpoint."""

import argparse
import asyncio
import json
from pathlib import Path

from dbus_next import Variant
from dbus_next.aio import MessageBus
from dbus_next.constants import BusType

from lynx_ble_gatt_probe import REQUEST_UUID, RESPONSE_UUID, SERVICE_UUID


async def trial(address, seconds):
    bus = await MessageBus(bus_type=BusType.SYSTEM).connect()
    root = bus.get_proxy_object("org.bluez", "/",
                                await bus.introspect("org.bluez", "/"))
    manager = root.get_interface("org.freedesktop.DBus.ObjectManager")
    adapter_path = "/org/bluez/hci0"
    adapter_obj = bus.get_proxy_object("org.bluez", adapter_path,
                                       await bus.introspect("org.bluez", adapter_path))
    adapter = adapter_obj.get_interface("org.bluez.Adapter1")
    device = None
    discovery = False
    result = {"state": "searching", "paired": False}
    try:
        await adapter.call_set_discovery_filter({"Transport": Variant("s", "le")})
        await adapter.call_start_discovery()
        discovery = True
        deadline = asyncio.get_running_loop().time() + seconds
        path = None
        while asyncio.get_running_loop().time() < deadline:
            objects = await manager.call_get_managed_objects()
            for candidate, interfaces in objects.items():
                properties = interfaces.get("org.bluez.Device1")
                if properties and properties.get("Address", Variant("s", "")).value.upper() == address:
                    path = candidate
                    break
            if path:
                break
            await asyncio.sleep(0.3)
        if not path:
            result["state"] = "not-discovered"
            return result
        result["discovered"] = True
        await adapter.call_stop_discovery()
        discovery = False
        device_obj = bus.get_proxy_object("org.bluez", path,
                                          await bus.introspect("org.bluez", path))
        device = device_obj.get_interface("org.bluez.Device1")
        await asyncio.wait_for(device.call_connect(), timeout=10)
        result["connected"] = True
        while asyncio.get_running_loop().time() < deadline:
            objects = await manager.call_get_managed_objects()
            service_paths = [p for p, props in objects.items()
                             if props.get("org.bluez.GattService1", {}).get(
                                 "UUID", Variant("s", "")).value.lower() == SERVICE_UUID]
            chars = {}
            for candidate, interfaces in objects.items():
                props = interfaces.get("org.bluez.GattCharacteristic1", {})
                uuid = props.get("UUID", Variant("s", "")).value.lower()
                if uuid in (REQUEST_UUID, RESPONSE_UUID) and any(
                        candidate.startswith(service + "/") for service in service_paths):
                    chars[uuid] = candidate
            if len(chars) == 2:
                break
            await asyncio.sleep(0.3)
        if len(chars) != 2:
            result["state"] = "service-not-resolved"
            return result
        result["service_resolved"] = True
        request_path = chars[REQUEST_UUID]
        response_path = chars[RESPONSE_UUID]
        request_obj = bus.get_proxy_object("org.bluez", request_path,
                                           await bus.introspect("org.bluez", request_path))
        response_obj = bus.get_proxy_object("org.bluez", response_path,
                                            await bus.introspect("org.bluez", response_path))
        request = request_obj.get_interface("org.bluez.GattCharacteristic1")
        response = response_obj.get_interface("org.bluez.GattCharacteristic1")
        await asyncio.wait_for(request.call_write_value(
            b"NRP/1 52 PING\n", {"type": Variant("s", "request")}), timeout=5)
        answer = bytes(await asyncio.wait_for(response.call_read_value({}), timeout=5))
        result["pong"] = answer == b"NRP/1 52 OK PONG\n"
        if not result["pong"]:
            result["state"] = "unexpected-ping-reply"
            return result
        await asyncio.wait_for(request.call_write_value(
            b"NRP/1 53 INFO\n", {"type": Variant("s", "request")}), timeout=5)
        info = bytes(await asyncio.wait_for(response.call_read_value({}), timeout=5))
        result["info_ok"] = info == (b"NRP/1 53 OK name=Lynx "
                                        b"firmware=alpine-native protocol=1 vm=1\n")
        result["state"] = "ping-info-complete" if result["info_ok"] else "unexpected-info-reply"
        return result
    finally:
        if device is not None:
            try:
                await asyncio.wait_for(device.call_disconnect(), timeout=5)
            except Exception:
                pass
        if discovery:
            await adapter.call_stop_discovery()
        bus.disconnect()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--factory-address-receipt", type=Path, required=True)
    parser.add_argument("--seconds", type=int, default=25)
    args = parser.parse_args()
    receipt = json.loads(args.factory_address_receipt.read_text())
    if receipt.get("partition") != "nvdata" or receipt.get("partition_writes") is not False:
        parser.error("factory address receipt is not a read-only nvdata read")
    if not 5 <= args.seconds <= 45:
        parser.error("seconds must be 5..45")
    print(json.dumps(asyncio.run(trial(receipt["address"], args.seconds))))
