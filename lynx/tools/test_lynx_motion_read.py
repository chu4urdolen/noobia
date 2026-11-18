"""Independent tests for the Lynx motion_read agent reader."""

import io
import json
import subprocess
import sys
import types
import unittest

import lynx_motion_read as mr


class FakeDev:
    def __init__(self, char_device=True):
        self.char_device = char_device

    def is_char_device(self):
        return self.char_device


class FakeProc:
    def __init__(self, text="bmi2xy acc\nbmi2xy gyro\n"):
        self.text = text

    def read_text(self):
        return self.text


def valid_sample(choice, axes=(1, 2, 3)):
    spec = mr.SENSORS[choice]
    return {
        'sensor_type': spec['sensor_type'],
        'disabled': True,
        'info': {'name': spec['name'], 'gain': spec['gain']},
        'events': [{'raw_xyz': list(axes)}],
    }


def fake_runner(sample, returncode=0):
    def runner(cmd, **kwargs):
        return types.SimpleNamespace(returncode=returncode,
                                     stdout=json.dumps(sample))
    return runner


class ReadRequestTests(unittest.TestCase):
    def test_accel_request(self):
        self.assertEqual(mr.read_request('{"choice": "accel"}'), 'accel')

    def test_gyro_request(self):
        self.assertEqual(mr.read_request('{"choice": "gyro"}'), 'gyro')

    def test_empty_string_rejected(self):
        with self.assertRaises(ValueError):
            mr.read_request('')

    def test_empty_object_rejected(self):
        with self.assertRaises(ValueError):
            mr.read_request('{}')

    def test_malformed_json_rejected(self):
        with self.assertRaises(ValueError):
            mr.read_request('{"choice": ')

    def test_non_object_rejected(self):
        with self.assertRaises(ValueError):
            mr.read_request('["accel"]')

    def test_wrong_choice_rejected(self):
        with self.assertRaises(ValueError):
            mr.read_request('{"choice": "magnet"}')

    def test_bool_choice_rejected(self):
        with self.assertRaises(ValueError):
            mr.read_request('{"choice": true}')

    def test_unhashable_list_choice_rejected(self):
        with self.assertRaises(ValueError):
            mr.read_request('{"choice": ["accel"]}')

    def test_unhashable_dict_choice_rejected(self):
        with self.assertRaises(ValueError):
            mr.read_request('{"choice": {"choice": "accel"}}')

    def test_extra_keys_rejected(self):
        with self.assertRaises(ValueError):
            mr.read_request('{"choice": "accel", "gain": 1000}')

    def test_oversized_input_rejected(self):
        with self.assertRaises(ValueError):
            mr.read_request('x' * (mr.MAX_INPUT + 1))


class ValidSensorTests(unittest.TestCase):
    def test_accel_valid(self):
        out = mr.read_motion('accel', runner=fake_runner(valid_sample('accel',
                              (100, -200, 300))),
                             dev=FakeDev(), proc=FakeProc())
        self.assertEqual(out['raw'], [100, -200, 300])
        self.assertEqual(out['gain'], 1000)
        self.assertEqual(out['sensor'], 'bmi2xy acc')
        self.assertEqual(out['unit'], 'driver_raw')
        self.assertFalse(out['calibrated'])
        self.assertTrue(out['sensor_disabled_after_sample'])

    def test_gyro_valid(self):
        out = mr.read_motion('gyro', runner=fake_runner(valid_sample('gyro',
                              (1000000, -500, 7))),
                             dev=FakeDev(), proc=FakeProc())
        self.assertEqual(out['raw'], [1000000, -500, 7])
        self.assertEqual(out['gain'], 1000000)
        self.assertEqual(out['sensor'], 'bmi2xy gyro')

    def test_helper_args_bounded(self):
        seen = []

        def runner(cmd, **kwargs):
            seen.append((cmd, kwargs))
            return types.SimpleNamespace(
                returncode=0, stdout=json.dumps(valid_sample('accel')))

        mr.read_motion('accel', runner=runner, dev=FakeDev(), proc=FakeProc())
        cmd, kwargs = seen[0]
        self.assertEqual(cmd[1], mr.HELPER)
        self.assertIn('--sensor', cmd)
        self.assertIn('1', cmd)
        self.assertIn('--seconds', cmd)
        self.assertIn('1', cmd)
        self.assertIn('--events', cmd)
        self.assertIn('3', cmd)
        self.assertEqual(kwargs['timeout'], mr.TIMEOUT)


class InvalidSensorTests(unittest.TestCase):
    def expect_error(self, choice, mutator, **kw):
        sample = valid_sample(choice)
        mutator(sample)
        with self.assertRaises(RuntimeError):
            mr.read_motion(choice, runner=fake_runner(sample),
                           dev=FakeDev(), proc=FakeProc(), **kw)

    def test_sensor_type_mismatch(self):
        self.expect_error('accel', lambda s: s.update(sensor_type=4))

    def test_name_mismatch(self):
        self.expect_error('gyro', lambda s: s['info'].update(name='bmi2xy acc'))

    def test_gain_mismatch(self):
        self.expect_error('accel', lambda s: s['info'].update(gain=1000000))

    def test_disabled_false(self):
        self.expect_error('accel', lambda s: s.update(disabled=False))

    def test_disabled_string_rejected(self):
        self.expect_error('accel', lambda s: s.update(disabled='true'))

    def test_no_events(self):
        self.expect_error('accel', lambda s: s.update(events=[]))

    def test_malformed_event_not_dict(self):
        self.expect_error('accel', lambda s: s.update(events=[42]))

    def test_malformed_event_string(self):
        self.expect_error('gyro', lambda s: s.update(events=['raw']))

    def test_too_many_events(self):
        self.expect_error('accel', lambda s: s.update(
            events=[{'raw_xyz': [1, 2, 3]}] * 4))

    def test_two_axes_rejected(self):
        self.expect_error('accel', lambda s: s['events'][0].update(raw_xyz=[1, 2]))

    def test_float_axis_rejected(self):
        self.expect_error('accel', lambda s: s['events'][0].update(
            raw_xyz=[1.0, 2, 3]))

    def test_bool_axis_rejected(self):
        self.expect_error('accel', lambda s: s['events'][0].update(
            raw_xyz=[True, 2, 3]))

    def test_string_axis_rejected(self):
        self.expect_error('gyro', lambda s: s['events'][0].update(
            raw_xyz=['1', 2, 3]))

    def test_accel_out_of_range(self):
        self.expect_error('accel', lambda s: s['events'][0].update(
            raw_xyz=[100001, 0, 0]))

    def test_gyro_in_range_ok(self):
        out = mr.read_motion('gyro',
                             runner=fake_runner(valid_sample('gyro', (1000000, 0, 0))),
                             dev=FakeDev(), proc=FakeProc())
        self.assertEqual(out['raw'], [1000000, 0, 0])

    def test_gyro_out_of_range(self):
        self.expect_error('gyro', lambda s: s['events'][0].update(
            raw_xyz=[-1000001, 0, 0]))

    def test_helper_failure(self):
        with self.assertRaises(RuntimeError):
            mr.read_motion('accel', runner=fake_runner(None, returncode=1),
                           dev=FakeDev(), proc=FakeProc())

    def test_helper_bad_output(self):
        def runner(cmd, **kwargs):
            return types.SimpleNamespace(returncode=0, stdout='not json')

        with self.assertRaises(RuntimeError):
            mr.read_motion('accel', runner=runner, dev=FakeDev(), proc=FakeProc())

    def test_helper_timeout_propagates(self):
        def runner(cmd, **kwargs):
            raise subprocess.TimeoutExpired(cmd, mr.TIMEOUT)

        with self.assertRaises(subprocess.TimeoutExpired):
            mr.read_motion('accel', runner=runner, dev=FakeDev(), proc=FakeProc())


class DeviceTests(unittest.TestCase):
    def test_absent_device_rejected(self):
        with self.assertRaises(RuntimeError):
            mr.read_motion('accel', runner=fake_runner(valid_sample('accel')),
                           dev=FakeDev(char_device=False), proc=FakeProc())

    def test_not_registered_rejected(self):
        with self.assertRaises(RuntimeError):
            mr.read_motion('accel', runner=fake_runner(valid_sample('accel')),
                           dev=FakeDev(), proc=FakeProc(text='tcs3408 als\n'))

    def test_proc_read_error_rejected(self):
        class BrokenProc:
            def read_text(self):
                raise OSError('proc unavailable')

        with self.assertRaises(RuntimeError):
            mr.read_motion('gyro', runner=fake_runner(valid_sample('gyro')),
                           dev=FakeDev(), proc=BrokenProc())


class MainTests(unittest.TestCase):
    def run_main(self, stdin_text):
        old_stdin, old_stdout = sys.stdin, sys.stdout
        out = io.StringIO()
        sys.stdin, sys.stdout = io.StringIO(stdin_text), out
        try:
            with self.assertRaises(SystemExit) as ctx:
                mr.main()
        finally:
            sys.stdin, sys.stdout = old_stdin, old_stdout
        return ctx.exception.code, out.getvalue()

    def test_unhashable_choice_bounded_error_exit_1(self):
        code, text = self.run_main('{"choice": ["accel"]}')
        self.assertEqual(code, 1)
        payload = json.loads(text)
        self.assertEqual(set(payload), {'error'})


if __name__ == '__main__':
    unittest.main(verbosity=2)
