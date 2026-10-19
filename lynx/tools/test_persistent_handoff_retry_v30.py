"""Exercise V30's real wait function with a transient and persistent guard refusal."""
from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parent.parent
SOURCE = (ROOT / 'linux-port/persistent-openrc-handoff-v30.sh').read_text()
FUNCTION = 'lynx_persistent_openrc_wait_and_handoff() {' + SOURCE.split(
    'lynx_persistent_openrc_wait_and_handoff() {', 1)[1]


def run_case(always_refuse):
    with tempfile.TemporaryDirectory(prefix='lynx-v30-retry-') as directory:
        temp = Path(directory)
        token = temp / 'session-token'
        token.write_text('test-token\n')
        marker = temp / 'openrc-handoff-ready'
        marker.write_text('test-token\n')
        attempts = temp / 'attempts'
        attempts.write_text('0\n')
        body = FUNCTION.replace('/etc/lynx/session-token', str(token)).replace(
            '/run/lynx/openrc-handoff-ready', str(marker)).replace(
            '$BB sleep 5', '$BB sleep 0')
        mock = '''lynx_persistent_openrc_handoff() {
  n=$($BB cat "$ATTEMPTS")
  n=$((n+1))
  printf '%s\\n' "$n" > "$ATTEMPTS"
  if [ "$ALWAYS_REFUSE" = 1 ] || [ "$n" = 1 ]; then return 2; fi
  return 0
}
'''
        script = ('set -eu\nBB=/usr/bin/busybox\nATTEMPTS=' + str(attempts) +
                  '\nALWAYS_REFUSE=' + ('1' if always_refuse else '0') +
                  '\nlog() { :; }\n' + mock + body +
                  '\nlynx_persistent_openrc_wait_and_handoff\n')
        process = subprocess.run(['sh'], input=script, text=True, capture_output=True,
                                 timeout=10)
        count = int(attempts.read_text())
        assert (process.returncode, count) == ((2, 4) if always_refuse else (0, 2)), (
            process.returncode, count, process.stderr)
        return {'refusals_persist': always_refuse, 'exit_code': process.returncode,
                'attempts': count}


if __name__ == '__main__':
    print(run_case(False))
    print(run_case(True))
