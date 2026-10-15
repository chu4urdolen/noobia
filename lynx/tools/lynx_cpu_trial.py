"""Short, supervised sensor-then-CPU-frequency RAM trial after pinned SSH.

Preserves boot_a. No battery/charger modules, manual governor settings,
stress test, thermal-limit writes or automatic module unloads.
"""
from pathlib import Path
import lynx_sensor_trial as trial
R=Path(__file__).resolve().parent.parent
trial.PACK=R/'linux-port/artifacts/thermal-ssh-pack-1792101216718173026'
trial.EXPECTED='43ef800701f518317780b6c8afe1623740be0f22799822f0e912ff2286aba5de'
trial.TRIAL_SCOPE=['soc-temperature','cpu-frequency']
trial.REMOTE='/run/lynx/thermal-cpu-trial'
if __name__=='__main__':trial.main()
