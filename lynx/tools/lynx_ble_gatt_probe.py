#!/usr/bin/env python3
"""Temporary, read-only Lynx NRP/1 GATT endpoint for a guarded BlueZ trial.

Only PING and INFO are accepted. No pairing, VM, or hardware calls are exposed.
The response is read from a separate characteristic, including ATT offsets.
Run as root in the same mount namespace as /run/lynx/noobd.sock.
"""

import argparse
import asyncio
import os
import re
import signal
import socket

from dbus_next import DBusError, Variant
from dbus_next.aio import MessageBus
from dbus_next.constants import BusType, PropertyAccess
from dbus_next.service import ServiceInterface, dbus_property, method


ROOT = "/org/noobia/lynx"
SERVICE_PATH = ROOT + "/service0"
REQUEST_PATH = SERVICE_PATH + "/request"
RESPONSE_PATH = SERVICE_PATH + "/response"
ADV_PATH = ROOT + "/advertisement0"
SERVICE_UUID = "6e6f6f62-6961-4c59-4e58-000000000001"
REQUEST_UUID = "6e6f6f62-6961-4c59-4e58-000000000002"
RESPONSE_UUID = "6e6f6f62-6961-4c59-4e58-000000000003"
REQUEST_PATTERN = re.compile(rb"NRP/1 ([0-9]{1,10}) (PING|INFO)\n")


def forward_read_only(request, path="/run/lynx/noobd.sock", timeout=1.5):
    """Validate before crossing the privileged local NRP socket boundary."""
    if len(request) > 128 or not REQUEST_PATTERN.fullmatch(request):
        raise ValueError("only one complete PING or INFO line is accepted")
    request_id = REQUEST_PATTERN.fullmatch(request).group(1)
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as conn:
        conn.settimeout(timeout)
        conn.connect(path)
        conn.sendall(request)
        received = bytearray()
        while len(received) < 512:
            chunk = conn.recv(512 - len(received))
            if not chunk:
                break
            received.extend(chunk)
            if b"\n" in received:
                break
    line, sep, rest = received.partition(b"\n")
    if not sep or rest or not line.startswith(b"NRP/1 " + request_id + b" OK "):
        raise RuntimeError("unexpected local NRP response")
    return bytes(line + b"\n")


class ObjectManager(ServiceInterface):
    def __init__(self):
        super().__init__("org.freedesktop.DBus.ObjectManager")

    @method()
    def GetManagedObjects(self) -> "a{oa{sa{sv}}}":
        return {
            SERVICE_PATH: {"org.bluez.GattService1": {
                "UUID": Variant("s", SERVICE_UUID),
                "Primary": Variant("b", True)}},
            REQUEST_PATH: {"org.bluez.GattCharacteristic1": {
                "UUID": Variant("s", REQUEST_UUID),
                "Service": Variant("o", SERVICE_PATH),
                "Flags": Variant("as", ["write"])}},
            RESPONSE_PATH: {"org.bluez.GattCharacteristic1": {
                "UUID": Variant("s", RESPONSE_UUID),
                "Service": Variant("o", SERVICE_PATH),
                "Flags": Variant("as", ["read"])}}
        }


class GattService(ServiceInterface):
    def __init__(self):
        super().__init__("org.bluez.GattService1")

    @dbus_property(access=PropertyAccess.READ)
    def UUID(self) -> "s":
        return SERVICE_UUID

    @dbus_property(access=PropertyAccess.READ)
    def Primary(self) -> "b":
        return True


class RequestCharacteristic(ServiceInterface):
    def __init__(self, reply):
        super().__init__("org.bluez.GattCharacteristic1")
        self.reply = reply

    @dbus_property(access=PropertyAccess.READ)
    def UUID(self) -> "s":
        return REQUEST_UUID

    @dbus_property(access=PropertyAccess.READ)
    def Service(self) -> "o":
        return SERVICE_PATH

    @dbus_property(access=PropertyAccess.READ)
    def Flags(self) -> "as":
        return ["write"]

    @method()
    async def WriteValue(self, value: "ay", options: "a{sv}"):
        if options.get("offset", Variant("q", 0)).value != 0 or \
                options.get("prepare-authorize", Variant("b", False)).value:
            raise DBusError("org.bluez.Error.NotSupported", "fragmented writes are disabled")
        try:
            answer = await asyncio.to_thread(forward_read_only, bytes(value))
        except ValueError as exc:
            raise DBusError("org.bluez.Error.NotPermitted", str(exc)) from exc
        except (OSError, RuntimeError) as exc:
            raise DBusError("org.bluez.Error.Failed", type(exc).__name__) from exc
        self.reply.value = answer


class ResponseCharacteristic(ServiceInterface):
    def __init__(self):
        super().__init__("org.bluez.GattCharacteristic1")
        self.value = b"NRP/1 0 ERR NO_REQUEST\n"

    @dbus_property(access=PropertyAccess.READ)
    def UUID(self) -> "s":
        return RESPONSE_UUID

    @dbus_property(access=PropertyAccess.READ)
    def Service(self) -> "o":
        return SERVICE_PATH

    @dbus_property(access=PropertyAccess.READ)
    def Flags(self) -> "as":
        return ["read"]

    @method()
    def ReadValue(self, options: "a{sv}") -> "ay":
        offset = options.get("offset", Variant("q", 0)).value
        if offset > len(self.value):
            raise DBusError("org.bluez.Error.InvalidOffset", "past response")
        return self.value[offset:]


class Advertisement(ServiceInterface):
    def __init__(self):
        super().__init__("org.bluez.LEAdvertisement1")

    @method()
    def Release(self):
        pass

    @dbus_property(access=PropertyAccess.READ)
    def Type(self) -> "s":
        return "peripheral"

    @dbus_property(access=PropertyAccess.READ)
    def ServiceUUIDs(self) -> "as":
        return [SERVICE_UUID]

    @dbus_property(access=PropertyAccess.READ)
    def LocalName(self) -> "s":
        return "Lynx"


async def run(seconds):
    if os.geteuid() != 0:
        raise RuntimeError("root required for local NRP socket")
    bus = await MessageBus(bus_type=BusType.SYSTEM).connect()
    response = ResponseCharacteristic()
    bus.export(ROOT, ObjectManager())
    bus.export(SERVICE_PATH, GattService())
    bus.export(REQUEST_PATH, RequestCharacteristic(response))
    bus.export(RESPONSE_PATH, response)
    bus.export(ADV_PATH, Advertisement())
    manager = bus.get_proxy_object("org.bluez", "/org/bluez/hci0",
                                   await bus.introspect("org.bluez", "/org/bluez/hci0"))
    gatt = manager.get_interface("org.bluez.GattManager1")
    adv = manager.get_interface("org.bluez.LEAdvertisingManager1")
    app_registered = False
    adv_registered = False
    try:
        await gatt.call_register_application(ROOT, {})
        app_registered = True
        await adv.call_register_advertisement(ADV_PATH, {})
        adv_registered = True
        print("GATT_READY", flush=True)
        stop = asyncio.Event()
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(sig, stop.set)
        if seconds == 0:
            await stop.wait()
        else:
            try:
                await asyncio.wait_for(stop.wait(), timeout=seconds)
            except asyncio.TimeoutError:
                pass
    finally:
        if adv_registered:
            await adv.call_unregister_advertisement(ADV_PATH)
        if app_registered:
            await gatt.call_unregister_application(ROOT)
        bus.disconnect()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seconds", type=int, required=True)
    args = parser.parse_args()
    if not 0 <= args.seconds <= 120:
        parser.error("seconds must be 0..120; 0 runs until SIGTERM")
    asyncio.run(run(args.seconds))
