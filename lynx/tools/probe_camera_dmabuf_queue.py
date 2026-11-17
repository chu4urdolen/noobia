#!/usr/bin/env python3
"""Probe V4L2 DMA-BUF buffer setup without starting the camera stream.

Run on Lynx. The queue is released before exit; no sensor power is requested.
"""

import fcntl
import json
import os
import struct

DEVICE = "/dev/video145"
V4L2_BUF_TYPE_VIDEO_CAPTURE_MPLANE = 9
V4L2_MEMORY_DMABUF = 4
VIDIOC_REQBUFS = 0xC0145608  # _IOWR('V', 8, struct v4l2_requestbuffers)


def reqbufs(fd, count):
    data = bytearray(struct.pack("=IIIII", count, V4L2_BUF_TYPE_VIDEO_CAPTURE_MPLANE,
                                 V4L2_MEMORY_DMABUF, 0, 0))
    fcntl.ioctl(fd, VIDIOC_REQBUFS, data, True)
    count, kind, memory, capabilities, flags = struct.unpack("=IIIII", data)
    return {"count": count, "type": kind, "memory": memory,
            "capabilities": capabilities, "flags": flags}


def main():
    result = {"device": DEVICE, "stream_requested": False}
    fd = os.open(DEVICE, os.O_RDWR | os.O_CLOEXEC)
    try:
        result["allocation"] = reqbufs(fd, 1)
    except OSError as exc:
        result["error"] = {"errno": exc.errno, "message": str(exc)}
    finally:
        try:
            result["release"] = reqbufs(fd, 0)
        except OSError as exc:
            result["release_error"] = {"errno": exc.errno, "message": str(exc)}
        os.close(fd)
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
