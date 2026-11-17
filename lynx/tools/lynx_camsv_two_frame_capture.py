#!/usr/bin/env python3
"""Capture two sensor4 frames; stage exposure on the first media request.

Requires the RAM-only camera module and sensor4 -> seninf-1 -> CAMSV-0 links.
Run under a host-side watchdog and IRQ monitor; this helper has no reboot logic.
"""

import argparse
import ctypes as C
import json
import mmap
import os
from pathlib import Path
import select
import struct
import sys
import time


class Timeval(C.Structure):
    _fields_ = [("tv_sec", C.c_long), ("tv_usec", C.c_long)]


class Timecode(C.Structure):
    _fields_ = [("type", C.c_uint32), ("flags", C.c_uint32),
                ("frames", C.c_uint8), ("seconds", C.c_uint8),
                ("minutes", C.c_uint8), ("hours", C.c_uint8),
                ("userbits", C.c_uint8 * 4)]


class PlaneMemory(C.Union):
    _fields_ = [("mem_offset", C.c_uint32), ("userptr", C.c_ulong),
                ("fd", C.c_int32)]


class Plane(C.Structure):
    _fields_ = [("bytesused", C.c_uint32), ("length", C.c_uint32),
                ("m", PlaneMemory), ("data_offset", C.c_uint32),
                ("reserved", C.c_uint32 * 11)]


class BufferMemory(C.Union):
    _fields_ = [("offset", C.c_uint32), ("userptr", C.c_ulong),
                ("planes", C.POINTER(Plane)), ("fd", C.c_int32)]


class Buffer(C.Structure):
    _fields_ = [("index", C.c_uint32), ("type", C.c_uint32),
                ("bytesused", C.c_uint32), ("flags", C.c_uint32),
                ("field", C.c_uint32), ("timestamp", Timeval),
                ("timecode", Timecode), ("sequence", C.c_uint32),
                ("memory", C.c_uint32), ("m", BufferMemory),
                ("length", C.c_uint32), ("reserved2", C.c_uint32),
                ("request_fd", C.c_int32)]


class RequestBuffers(C.Structure):
    _fields_ = [("count", C.c_uint32), ("type", C.c_uint32),
                ("memory", C.c_uint32), ("capabilities", C.c_uint32),
                ("flags", C.c_uint8), ("reserved", C.c_uint8 * 3)]


class HeapAlloc(C.Structure):
    _fields_ = [("length", C.c_uint64), ("fd", C.c_uint32),
                ("fd_flags", C.c_uint32), ("heap_flags", C.c_uint64)]


class BufSync(C.Structure):
    _fields_ = [("flags", C.c_uint64)]


class V4L2ExtControlValue(C.Union):
    _pack_ = 1
    _fields_ = [("value", C.c_int32), ("value64", C.c_int64),
                ("ptr", C.c_void_p)]


class V4L2ExtControl(C.Structure):
    _pack_ = 1
    _fields_ = [("id", C.c_uint32), ("size", C.c_uint32),
                ("reserved2", C.c_uint32), ("v", V4L2ExtControlValue)]


class V4L2ExtControls(C.Structure):
    _fields_ = [("which", C.c_uint32), ("count", C.c_uint32),
                ("error_idx", C.c_uint32), ("request_fd", C.c_int32),
                ("reserved", C.c_uint32),
                ("controls", C.POINTER(V4L2ExtControl))]


def ioctl_code(direction, kind, number, size):
    return (direction << 30) | (size << 16) | (ord(kind) << 8) | number


VIDIOC_REQBUFS = ioctl_code(3, "V", 8, C.sizeof(RequestBuffers))
VIDIOC_QBUF = ioctl_code(3, "V", 15, C.sizeof(Buffer))
VIDIOC_DQBUF = ioctl_code(3, "V", 17, C.sizeof(Buffer))
VIDIOC_STREAMON = ioctl_code(1, "V", 18, C.sizeof(C.c_int))
VIDIOC_STREAMOFF = ioctl_code(1, "V", 19, C.sizeof(C.c_int))
VIDIOC_S_EXT_CTRLS = ioctl_code(3, "V", 72, C.sizeof(V4L2ExtControls))
V4L2_CID_EXPOSURE = 0x00980911
V4L2_CID_MTK_STAGGER_AE_CTRL = 0x00981bdf
V4L2_CTRL_WHICH_REQUEST_VAL = 0x0f010000
MEDIA_IOC_REQUEST_ALLOC = ioctl_code(2, "|", 5, C.sizeof(C.c_int))
MEDIA_REQUEST_IOC_QUEUE = ioctl_code(0, "|", 0x80, 0)
DMA_HEAP_IOCTL_ALLOC = ioctl_code(3, "H", 0, C.sizeof(HeapAlloc))
DMA_BUF_IOCTL_SYNC = ioctl_code(1, "b", 0, C.sizeof(BufSync))
CAPTURE_TYPE = 9
DMABUF_MEMORY = 4
REQUEST_FLAG = 0x00800000
IMAGE_BYTES = 1600 * 1200
ALLOC_BYTES = 1920024
FRAME_HEADER_BYTES = ALLOC_BYTES - IMAGE_BYTES

libc = C.CDLL(None, use_errno=True)
libc.ioctl.argtypes = (C.c_int, C.c_ulong, C.c_void_p)
libc.ioctl.restype = C.c_int


def ioctl(fd, code, value=None):
    pointer = C.byref(value) if value is not None else None
    if libc.ioctl(fd, code, pointer) < 0:
        number = C.get_errno()
        raise OSError(number, os.strerror(number), f"ioctl 0x{code:x}")


def reqbufs(fd, count):
    req = RequestBuffers(count=count, type=CAPTURE_TYPE, memory=DMABUF_MEMORY)
    ioctl(fd, VIDIOC_REQBUFS, req)
    return req


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--settle-ms", type=int, default=750)
    parser.add_argument("--request-exposure-lines", type=int, required=True)
    parser.add_argument("--request-raw-gain", type=int,
                        help="vendor AE request gain, 1024 is 1x")
    parser.add_argument("--output", type=Path, default=Path("/run/lynx/camera-camsv-trial/sensor4.bayer"))
    args = parser.parse_args()
    if not 0 <= args.settle_ms <= 1500:
        parser.error("--settle-ms must be between 0 and 1500")
    if not 1005 <= args.request_exposure_lines <= 3000:
        parser.error("--request-exposure-lines must be between 1005 and 3000")
    if args.request_raw_gain is not None and not 1024 <= args.request_raw_gain <= 4096:
        parser.error("--request-raw-gain must be between 1x and 4x")
    report = {"schema": 1, "stream_requested": False, "frame_bytes": 0,
              "device": "/dev/video145", "heap": "/dev/dma_heap/system"}
    video = heap = media = dmabuf = request = request2 = sensor = None
    mapping = None
    streaming = False
    queue_allocated = False
    try:
        if (C.sizeof(Plane), C.sizeof(Buffer), C.sizeof(RequestBuffers), C.sizeof(HeapAlloc),
                C.sizeof(V4L2ExtControl), C.sizeof(V4L2ExtControls)) != (64, 88, 20, 24, 20, 32):
            raise RuntimeError("unexpected aarch64 V4L2 structure layout")
        video = os.open(report["device"], os.O_RDWR | os.O_NONBLOCK | os.O_CLOEXEC)
        heap = os.open(report["heap"], os.O_RDWR | os.O_CLOEXEC)
        alloc = HeapAlloc(length=ALLOC_BYTES, fd_flags=os.O_RDWR | os.O_CLOEXEC)
        ioctl(heap, DMA_HEAP_IOCTL_ALLOC, alloc)
        dmabuf = alloc.fd
        report["dmabuf_allocated"] = True
        queue = reqbufs(video, 1)
        queue_allocated = True
        report["queue_count"] = queue.count
        report["queue_capabilities"] = queue.capabilities
        if queue.count != 1 or (queue.capabilities & 0x0c) != 0x0c:
            raise RuntimeError("DMA-BUF/media-request queue unavailable")
        media = os.open("/dev/media1", os.O_RDWR | os.O_CLOEXEC)
        request_value = C.c_int(-1)
        ioctl(media, MEDIA_IOC_REQUEST_ALLOC, request_value)
        request = request_value.value
        if request < 0:
            raise RuntimeError("media request fd invalid")
        sensor = os.open("/dev/v4l-subdev4", os.O_RDWR | os.O_CLOEXEC)
        if args.request_raw_gain is None:
            ext_control = V4L2ExtControl(id=V4L2_CID_EXPOSURE)
            ext_control.v.value = args.request_exposure_lines
        else:
            # Matching imgsensor-user.h has five u32 exposure fields, five
            # gain fields, then actions, subsample_tags, and req_id. Dushich
            # independently encoded/tested this 52-byte layout in commit
            # 52a2f81 in his separate Nexus workspace.
            ae_bytes = struct.pack("<13I", args.request_exposure_lines,
                                   0, 0, 0, 0, args.request_raw_gain,
                                   0, 0, 0, 0, 0, 0, 0)
            ae_buffer = C.create_string_buffer(ae_bytes, len(ae_bytes))
            ext_control = V4L2ExtControl(id=V4L2_CID_MTK_STAGGER_AE_CTRL,
                                          size=len(ae_bytes))
            ext_control.v.ptr = C.addressof(ae_buffer)
        ext_controls = V4L2ExtControls(which=V4L2_CTRL_WHICH_REQUEST_VAL,
                                       count=1, request_fd=request,
                                       controls=C.pointer(ext_control))
        ioctl(sensor, VIDIOC_S_EXT_CTRLS, ext_controls)
        report["request_exposure_lines"] = args.request_exposure_lines
        if args.request_raw_gain is not None:
            report["request_raw_gain"] = args.request_raw_gain
            report["ae_payload_hex"] = ae_bytes.hex()
        report["request_exposure_staged"] = True
        os.close(sensor)
        sensor = None
        planes = (Plane * 1)()
        planes[0].length = ALLOC_BYTES
        planes[0].m.fd = dmabuf
        buffer = Buffer(index=0, type=CAPTURE_TYPE, memory=DMABUF_MEMORY,
                        flags=REQUEST_FLAG, length=1, request_fd=request)
        buffer.m.planes = C.cast(planes, C.POINTER(Plane))
        ioctl(video, VIDIOC_QBUF, buffer)
        report["buffer_queued"] = True
        kind = C.c_int(CAPTURE_TYPE)
        report["stream_requested"] = True
        ioctl(video, VIDIOC_STREAMON, kind)
        streaming = True
        report["stream_on"] = True
        if args.settle_ms:
            time.sleep(args.settle_ms / 1000)
            report["settle_ms"] = args.settle_ms
        ioctl(request, MEDIA_REQUEST_IOC_QUEUE)
        report["request_queued"] = True
        poller = select.poll()
        poller.register(video, select.POLLIN | select.POLLERR)
        def retrieve_frame(label, destination):
            events = poller.poll(9000)
            if not events:
                raise TimeoutError(f"no {label} frame within 9 seconds")
            dequeue = Buffer(type=CAPTURE_TYPE, memory=DMABUF_MEMORY, length=1)
            dequeue.m.planes = C.cast(planes, C.POINTER(Plane))
            ioctl(video, VIDIOC_DQBUF, dequeue)
            size = planes[0].bytesused
            if size < FRAME_HEADER_BYTES + IMAGE_BYTES or size > ALLOC_BYTES or dequeue.flags & 0x40:
                raise RuntimeError(f"invalid {label} frame: bytesused={size}, flags=0x{dequeue.flags:x}")
            nonlocal mapping
            if mapping is None:
                mapping = mmap.mmap(dmabuf, ALLOC_BYTES, access=mmap.ACCESS_READ)
            ioctl(dmabuf, DMA_BUF_IOCTL_SYNC, BufSync(flags=1))
            try:
                header = mapping[:FRAME_HEADER_BYTES].hex()
                destination.parent.mkdir(parents=True, exist_ok=True)
                destination.write_bytes(mapping[FRAME_HEADER_BYTES:FRAME_HEADER_BYTES + IMAGE_BYTES])
            finally:
                ioctl(dmabuf, DMA_BUF_IOCTL_SYNC, BufSync(flags=5))
            report[label] = {"bytesused": size, "sequence": dequeue.sequence,
                             "buffer_flags": dequeue.flags, "header_hex": header,
                             "frame_bytes": destination.stat().st_size}

        first_output = args.output.with_name(args.output.stem + "-first" + args.output.suffix)
        retrieve_frame("first", first_output)
        request_value = C.c_int(-1)
        ioctl(media, MEDIA_IOC_REQUEST_ALLOC, request_value)
        request2 = request_value.value
        if request2 < 0:
            raise RuntimeError("second media request fd invalid")
        planes[0].bytesused = 0
        buffer = Buffer(index=0, type=CAPTURE_TYPE, memory=DMABUF_MEMORY,
                        flags=REQUEST_FLAG, length=1, request_fd=request2)
        buffer.m.planes = C.cast(planes, C.POINTER(Plane))
        ioctl(video, VIDIOC_QBUF, buffer)
        ioctl(request2, MEDIA_REQUEST_IOC_QUEUE)
        report["second_request_queued"] = True
        retrieve_frame("second", args.output)
        report["frame_bytes"] = args.output.stat().st_size
        report["state"] = "two_frames_captured"
    except Exception as exc:
        report["state"] = "failed"
        report["error"] = repr(exc)
    finally:
        if streaming:
            try:
                ioctl(video, VIDIOC_STREAMOFF, C.c_int(CAPTURE_TYPE))
                report["stream_off"] = True
            except Exception as exc:
                report["stream_off_error"] = repr(exc)
        if queue_allocated:
            try:
                reqbufs(video, 0)
                report["queue_released"] = True
            except Exception as exc:
                report["queue_release_error"] = repr(exc)
        if mapping is not None:
            mapping.close()
        for fd in (sensor, request2, request, dmabuf, media, heap, video):
            if fd is not None:
                os.close(fd)
        print(json.dumps(report, sort_keys=True))
    if report["state"] == "failed":
        sys.exit(1)


if __name__ == "__main__":
    main()
