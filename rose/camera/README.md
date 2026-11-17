# Nyx AI Camera tools

Two bounded C tools operate the official Raspberry Pi AI Camera (Sony IMX500),
mounted upside down on Rose. Both request a 180-degree camera transform, so JPEG
pixels and object overlays share the corrected orientation without re-encoding.

```sh
make
make install-user
rose-nyx-snapshot
rose-nyx-detect
```

`rose-nyx-snapshot` prints the path of a temporary JPEG.

`rose-nyx-detect` accepts a ranked model set and prints one JSON manifest. With
no arguments it uses `object0`.

```sh
rose-nyx-detect --list
rose-nyx-detect object0 object1 object2
rose-nyx-detect object0 pose0
```

- `object0`: MobileNet SSD, broad balanced default.
- `object1`: EfficientDet Lite0, stronger/heavier general detector.
- `object2`: NanoDet Plus, compact general detector.
- `pose0`: PoseNet human skeleton overlay.

The IMX500 loads one network at a time and inference happens during capture. A
set therefore produces sequential live frames, labelled `live-sequential`; it
does not process one saved JPEG repeatedly. Object runs return an annotated
JPEG, decoded detection JSON, and raw metadata. Pose runs return an annotated
JPEG and metadata. Boxes use normalized `ymin,xmin,ymax,xmax` coordinates. Set
`ROSE_NYX_THRESHOLD` from `0` to `1` to override the default `0.55`.

Snapshot capture is limited to 30 seconds. Detection is limited to 300 seconds
because the first IMX500 model upload can take several minutes. Failed runs
remove their temporary outputs.

Prerequisite package:

```sh
sudo apt install imx500-all
```
