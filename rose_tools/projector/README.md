# Rose projector tool

`projector_cast.py` displays a local image or video on the Noobia HY300/HCCast projector.

```sh
./projector_cast.py /absolute/path/to/image.png
./projector_cast.py /absolute/path/to/video.mp4
```

The tool locates `Hccast-079426` by its MAC address (`30:4a:26:07:94:26`), verifies the DLNA renderer identity, converts media with `ffmpeg`, serves it only on the local Noobia interface, and launches playback with UPnP AVTransport. `--host IP` provides a manual override.

Requirements: Python 3, `ffmpeg`, `ffprobe`, and local access to the projector. The projector's HCCast background service must be active.
