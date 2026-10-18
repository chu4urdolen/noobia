"""Record Lynx USB mode changes without sending commands to the phone."""
import argparse
import json
from pathlib import Path
import time

from lynx_trial_observer_v1 import USBObserver


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--seconds', type=int, default=900)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if not 1 <= args.seconds <= 3600:
        parser.error('seconds must be 1..3600')
    if args.output.exists():
        parser.error('output already exists')
    args.output.parent.mkdir(parents=True, exist_ok=True)
    observer = USBObserver(args.output)
    observer.start()
    print(json.dumps({'state': 'watching-fastboot-departure',
                      'result': str(args.output)}), flush=True)
    deadline = time.monotonic() + args.seconds
    try:
        while time.monotonic() < deadline and not observer.departed:
            time.sleep(0.5)
        if observer.departed:
            time.sleep(2)
    finally:
        observer.stop()
    print(json.dumps({'state': 'departed' if observer.departed else 'deadline',
                      'result': str(args.output)}), flush=True)


if __name__ == '__main__':
    main()
