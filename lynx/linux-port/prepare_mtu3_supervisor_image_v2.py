"""Build corrected supervisor separately; preserve the defective historical image."""
from pathlib import Path
import prepare_mtu3_supervisor_image as builder

builder.OUTPUT = Path(__file__).resolve().parent / 'artifacts/busybox-mtu3-timed-supervisor-v2'
builder.main()
