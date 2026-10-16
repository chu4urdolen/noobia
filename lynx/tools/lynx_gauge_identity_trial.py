"""Supervised fixed DeviceType query; no image or charging changes.

One write of information selector 0x0001 to control register 0x00, then one
read of register 0x00 after 20 ms, following the matching OEM driver's path.
This is not the temperature-only profile; its proven binary stays preserved.
"""
import sys
import lynx_gauge_trial as gauge

OLD_MODULE_SHA = gauge.MODULE_SHA
gauge.BASIS = gauge.PORT / 'artifacts/gauge-module-basis-1792105646594458259'
gauge.MODULE = gauge.BASIS / 'module/lynx-gauge-sample.ko'
gauge.SOURCE = gauge.PORT / 'lynx-gauge-identity.c'
gauge.MODULE_SHA = '93f4fc1e15ece375dfabdedff9dd460fc513a752845f1e902dd08d8248b06df6'
gauge.SOURCE_SHA = '92289b3be59b6ed71d7862e280874e87f54d16a9afb0c1634550e1bed33465d4'
gauge.VM = gauge.PORT / 'artifacts/emulated-gauge-sample-1792105712214035956/result.json'
gauge.LOGIC = gauge.PORT / 'artifacts/gauge-reader-logic-1792105646466821751/result.json'
gauge.COMMAND_TEST = gauge.PORT / 'artifacts/gauge-command-check-1792105758653461063/result.json'
gauge.COMMAND = (gauge.COMMAND.replace(OLD_MODULE_SHA, gauge.MODULE_SHA)
                 .replace('allow_raw_read=1', 'allow_identity_query=1')
                 .replace('raw_temperature_word', 'raw_device_type')
                 .replace('GAUGE_RAW_MODEL_UNVERIFIED=1', 'GAUGE_DEVICE_TYPE_REPLY=1'))
if '--keep-running' in sys.argv:
    gauge.COMMAND = gauge.COMMAND.replace('thermal-stop.pid', 'thermal-watch.pid')


if __name__ == '__main__':
    gauge.validate_extra()
    trial = gauge.trial
    trial.TRIAL_PREFIX = 'gauge-identity-trial-'
    trial.POST_CPU_HOOK = gauge.sample
    trial.EXTRA_DIAGNOSTIC = {'kind': 'stock DeviceType query: fixed selector write and response read',
                              'module_sha256': gauge.MODULE_SHA,
                              'source_sha256': gauge.SOURCE_SHA,
                              'stock_kernel_vm_passed': True,
                              'physical_probe_previously_tested': False,
                              'control_register': '0x00', 'information_selector': '0x0001',
                              'reset_unseal_calibration_or_charging_commands': False}
    trial.main()
