# Rose projector tool

`projector-cast` is a C tool that displays a local image or video on the Noobia HY300/HCCast projector.

```sh
make
./projector-cast /absolute/path/to/image.png
./projector-cast /absolute/path/to/video.mp4
```

The media file is the only argument. The tool locates `Hccast-079426` by its MAC address (`30:4a:26:07:94:26`), verifies the DLNA renderer identity, converts media with `ffmpeg`, serves it only on the local Noobia interface, and launches playback with UPnP AVTransport.

Requirements: a C11 compiler, `ffmpeg`, and local access to the projector. The projector's HCCast background service must be active.
