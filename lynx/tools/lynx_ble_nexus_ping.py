#!/usr/bin/env python3
"""Bounded Nexus-authenticated BLE NRP/1 and VM smoke test for Lynx."""

import argparse
import asyncio
import json
from pathlib import Path
import re

from dbus_next import DBusError, Variant
from dbus_next.aio import MessageBus
from dbus_next.constants import BusType

from lynx_ble_auth import envelope, fragments, load_key
from lynx_ble_gatt_probe import CHALLENGE_UUID, REQUEST_UUID, RESPONSE_UUID, SERVICE_UUID


async def trial(address, seconds, key, vm_smoke=False, audible_smoke=False):
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
                if uuid in (REQUEST_UUID, RESPONSE_UUID, CHALLENGE_UUID) and any(
                        candidate.startswith(service + "/") for service in service_paths):
                    chars[uuid] = candidate
            if len(chars) == 3:
                break
            await asyncio.sleep(0.3)
        if len(chars) != 3:
            result["state"] = "service-not-resolved"
            return result
        result["service_resolved"] = True
        request_path = chars[REQUEST_UUID]
        response_path = chars[RESPONSE_UUID]
        challenge_path = chars[CHALLENGE_UUID]
        request_obj = bus.get_proxy_object("org.bluez", request_path,
                                           await bus.introspect("org.bluez", request_path))
        response_obj = bus.get_proxy_object("org.bluez", response_path,
                                            await bus.introspect("org.bluez", response_path))
        challenge_obj = bus.get_proxy_object("org.bluez", challenge_path,
                                             await bus.introspect("org.bluez", challenge_path))
        request = request_obj.get_interface("org.bluez.GattCharacteristic1")
        response = response_obj.get_interface("org.bluez.GattCharacteristic1")
        challenge = challenge_obj.get_interface("org.bluez.GattCharacteristic1")
        challenge_frame = bytes(await asyncio.wait_for(challenge.call_read_value({}), timeout=5))
        match = re.fullmatch(rb"AUTH/1 CHALLENGE ([0-9a-f]{64})\n", challenge_frame)
        if not match:
            result["state"] = "invalid-challenge"
            return result
        nonce = bytes.fromhex(match.group(1).decode())
        sequence = 0

        async def exchange(rid, command):
            nonlocal sequence
            sequence += 1
            line = f"NRP/1 {rid} {command}\n".encode("ascii")
            frame = envelope(key, nonce, sequence, line)
            for chunk in fragments(frame):
                await asyncio.wait_for(request.call_write_value(
                    chunk, {"type": Variant("s", "request")}), timeout=10)
            reply = bytes(await asyncio.wait_for(response.call_read_value({}), timeout=5))
            if not reply.startswith(f"NRP/1 {rid} ".encode()):
                raise RuntimeError("BLE response request ID mismatch")
            return reply

        answer = await exchange(52, "PING")
        result["pong"] = answer == b"NRP/1 52 OK PONG\n"
        if not result["pong"]:
            result["state"] = "unexpected-ping-reply"
            return result
        info = await exchange(53, "INFO")
        result["info_ok"] = info == (b"NRP/1 53 OK name=Lynx "
                                        b"firmware=alpine-native protocol=1 vm=1\n")
        if not result["info_ok"]:
            result["state"] = "unexpected-info-reply"
            return result
        if vm_smoke or audible_smoke:
            status = await exchange(54, "STATUS")
            if b"state=EMPTY" not in status:
                result["state"] = "vm-not-empty"
                return result
            try:
                await asyncio.wait_for(request.call_write_value(
                    b"NRP/1 66 STATUS\n", {"type": Variant("s", "request")}), timeout=5)
            except DBusError:
                result["unsigned_rejected"] = True
            else:
                result["unsigned_rejected"] = False
                result["state"] = "unsigned-request-accepted"
                return result
            if audible_smoke:
                ready = await exchange(67, "CALL AUDIO_READY")
                result["audio_ready"] = b"value=1 detail=card=1 firmware=1" in ready
                if not result["audio_ready"]:
                    result["state"] = "audio-not-ready"
                    return result
                direct = await exchange(68, 'CALL_MIXED SOUND_PLAY "beep"')
                result["direct_beep_accepted"] = b"value=1 detail=name=beep" in direct
                if not result["direct_beep_accepted"]:
                    result["state"] = "direct-beep-rejected"
                    return result
                # VM: SOUND_PLAY("beep"), WAIT 1200 ms, SOUND_PLAY("beep"), HALT.
                # The direct command gives one beep; the VM gives two more.
                await asyncio.sleep(1.8)
                program = "2200540100046265657021b0042200540100046265657000"
            else:
                program = "00"
            loaded = await exchange(55, "LOAD " + program)
            result["vm_loaded"] = loaded == f"NRP/1 55 OK loaded={len(program) // 2}\n".encode()
            started = await exchange(56, "RUN")
            result["vm_started"] = started == b"NRP/1 56 OK started\n"
            if audible_smoke:
                await asyncio.sleep(2.0)
            halted = await exchange(57, "STATUS")
            result["vm_halted"] = b"state=HALTED" in halted
            if audible_smoke:
                result["vm_beep_calls_succeeded"] = b"regs=1," in halted
            reset = await exchange(58, "RESET_VM")
            result["vm_reset"] = b"state=EMPTY" in reset
            checks = ["unsigned_rejected", "vm_loaded", "vm_started", "vm_halted", "vm_reset"]
            if audible_smoke:
                checks += ["audio_ready", "direct_beep_accepted", "vm_beep_calls_succeeded"]
            result["state"] = (("audible-smoke-complete" if audible_smoke else "vm-smoke-complete")
                               if all(result.get(k) for k in checks) else "vm-smoke-failed")
        else:
            result["state"] = "ping-info-complete"
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
    parser.add_argument("--nexus-key-file", type=Path,
                        default=Path("/noobia/lynx/private/nrp-nexus.key"))
    parser.add_argument("--vm-smoke", action="store_true")
    parser.add_argument("--audible-smoke", action="store_true")
    parser.add_argument("--seconds", type=int, default=25)
    args = parser.parse_args()
    receipt = json.loads(args.factory_address_receipt.read_text())
    if receipt.get("partition") != "nvdata" or receipt.get("partition_writes") is not False:
        parser.error("factory address receipt is not a read-only nvdata read")
    if not 5 <= args.seconds <= 45:
        parser.error("seconds must be 5..45")
    key = load_key(args.nexus_key_file)
    print(json.dumps(asyncio.run(trial(receipt["address"], args.seconds, key,
                                       vm_smoke=args.vm_smoke,
                                       audible_smoke=args.audible_smoke))))
