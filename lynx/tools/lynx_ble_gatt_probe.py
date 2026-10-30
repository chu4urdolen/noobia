#!/usr/bin/env python3
"""Nexus-authenticated Lynx NRP/1 GATT endpoint for a guarded BlueZ trial."""

import argparse
import asyncio
import os
import re
import signal
import socket
import time

from dbus_next import DBusError, Variant
from dbus_next.aio import MessageBus
from dbus_next.constants import BusType, PropertyAccess
from dbus_next.service import ServiceInterface, dbus_property, method

from lynx_ble_auth import Authenticator, FragmentAssembler, load_key


ROOT = "/org/noobia/lynx"
SERVICE_PATH = ROOT + "/service0"
REQUEST_PATH = SERVICE_PATH + "/request"
RESPONSE_PATH = SERVICE_PATH + "/response"
CHALLENGE_PATH = SERVICE_PATH + "/challenge"
ADV_PATH = ROOT + "/advertisement0"
SERVICE_UUID = "6e6f6f62-6961-4c59-4e58-000000000001"
REQUEST_UUID = "6e6f6f62-6961-4c59-4e58-000000000002"
RESPONSE_UUID = "6e6f6f62-6961-4c59-4e58-000000000003"
CHALLENGE_UUID = "6e6f6f62-6961-4c59-4e58-000000000004"
REQUEST_PATTERN = re.compile(rb"NRP/1 ([0-9]{1,10}) [A-Z_]+(?: [^\n]*)?\n")


def forward_nrp(request, path="/run/lynx/noobd.sock", timeout=9):
    """Forward one authenticated request to the existing root-only runtime."""
    match = REQUEST_PATTERN.fullmatch(request)
    if len(request) > 512 or not match:
        raise ValueError("invalid bounded NRP request")
    request_id = match.group(1)
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as conn:
        conn.settimeout(timeout)
        conn.connect(path)
        conn.sendall(request)
        with conn.makefile("rb") as stream:
            for _ in range(32):
                answer = stream.readline(4097)
                if not answer.endswith(b"\n") or len(answer) > 4096:
                    raise RuntimeError("incomplete local NRP response")
                if answer.startswith(b"NRP/1 0 EVENT "):
                    continue
                if answer.startswith(b"NRP/1 " + request_id + b" OK") or \
                        answer.startswith(b"NRP/1 " + request_id + b" ERR"):
                    return answer
                raise RuntimeError("unexpected local NRP response")
    raise RuntimeError("too many local NRP events")


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
                "Flags": Variant("as", ["read"])}},
            CHALLENGE_PATH: {"org.bluez.GattCharacteristic1": {
                "UUID": Variant("s", CHALLENGE_UUID),
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
    def __init__(self, reply, auth):
        super().__init__("org.bluez.GattCharacteristic1")
        self.reply = reply
        self.auth = auth
        self.fragments = FragmentAssembler()

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
        device = options.get("device")
        if device is None or options.get("type", Variant("s", "request")).value != "request":
            raise DBusError("org.bluez.Error.NotAuthorized", "device request required")
        try:
            frame = self.fragments.add(device.value, bytes(value))
            if frame is None:
                return
            request = self.auth.accept(frame)
        except ValueError as exc:
            raise DBusError("org.bluez.Error.NotAuthorized", str(exc)) from exc
        try:
            answer = await asyncio.to_thread(forward_nrp, request)
        except (OSError, RuntimeError) as exc:
            raise DBusError("org.bluez.Error.Failed", type(exc).__name__) from exc
        self.reply.set_reply(device.value, answer)


class ResponseCharacteristic(ServiceInterface):
    def __init__(self):
        super().__init__("org.bluez.GattCharacteristic1")
        self.replies = {}

    def set_reply(self, device, answer):
        if len(self.replies) >= 16:
            self.replies = {peer: item for peer, item in self.replies.items()
                            if item[1] > time.monotonic()}
            if len(self.replies) >= 16:
                self.replies.pop(min(self.replies, key=lambda peer: self.replies[peer][1]))
        self.replies[device] = (answer, time.monotonic() + 30)

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
        device = options.get("device")
        if device is None or device.value not in self.replies:
            raise DBusError("org.bluez.Error.NotAuthorized", "no response for device")
        value, expiry = self.replies[device.value]
        if time.monotonic() > expiry:
            self.replies.pop(device.value, None)
            raise DBusError("org.bluez.Error.NotAuthorized", "response expired")
        offset = options.get("offset", Variant("q", 0)).value
        if offset > len(value):
            raise DBusError("org.bluez.Error.InvalidOffset", "past response")
        return value[offset:]


class ChallengeCharacteristic(ServiceInterface):
    def __init__(self, auth):
        super().__init__("org.bluez.GattCharacteristic1")
        self.auth = auth

    @dbus_property(access=PropertyAccess.READ)
    def UUID(self) -> "s":
        return CHALLENGE_UUID

    @dbus_property(access=PropertyAccess.READ)
    def Service(self) -> "o":
        return SERVICE_PATH

    @dbus_property(access=PropertyAccess.READ)
    def Flags(self) -> "as":
        return ["read"]

    @method()
    def ReadValue(self, options: "a{sv}") -> "ay":
        value = self.auth.challenge_line()
        offset = options.get("offset", Variant("q", 0)).value
        if offset > len(value):
            raise DBusError("org.bluez.Error.InvalidOffset", "past challenge")
        return value[offset:]


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


async def run(seconds, key_file):
    if os.geteuid() != 0:
        raise RuntimeError("root required for local NRP socket")
    auth = Authenticator(load_key(key_file))
    bus = await MessageBus(bus_type=BusType.SYSTEM).connect()
    response = ResponseCharacteristic()
    bus.export(ROOT, ObjectManager())
    bus.export(SERVICE_PATH, GattService())
    bus.export(REQUEST_PATH, RequestCharacteristic(response, auth))
    bus.export(RESPONSE_PATH, response)
    bus.export(CHALLENGE_PATH, ChallengeCharacteristic(auth))
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
    parser.add_argument("--nexus-key-file", default="/etc/lynx/nrp-nexus.key")
    args = parser.parse_args()
    if not 0 <= args.seconds <= 120:
        parser.error("seconds must be 0..120; 0 runs until SIGTERM")
    asyncio.run(run(args.seconds, args.nexus_key_file))
