"""Prepare a separate exact-stock VM activation test for the audited offsets."""
from pathlib import Path
R=Path(__file__).resolve().parent.parent;T=R/'tools'
def main():
    source=(T/'test_native_ufs_trace_registration.py').read_text().replace('ufs-persistent-trace-setup.sh','ufs-refclk-persistent-trace-setup.sh').replace('emulated-native-ufs-trace-registration-','emulated-native-refclk-trace-')
    labels=['refclk-enter','before-firmware','after-firmware','before-request-store','after-request-store','before-ack-read','after-ack-read','refclk-return','crypto-enter']
    source=source.replace("TARGETS+['platform_drv_probe','dev_pm_domain_attach','genpd_dev_pm_attach']",repr(labels)).replace('targets=TARGETS','targets='+repr(labels))
    out=T/'test_native_refclk_trace.py';assert not out.exists();compile(source,str(out),'exec');out.write_text(source)
    source=(T/'test_ufs_controlled_probe.py').read_text().replace('ufs-persistent-trace-setup.sh','ufs-refclk-persistent-trace-setup.sh').replace('ufs-controlled-probe-','refclk-controlled-probe-')
    out=T/'test_refclk_controlled_probe.py';assert not out.exists();compile(source,str(out),'exec');out.write_text(source)
    print('Separate offset activation and unchanged probe-safety tests prepared.')
if __name__=='__main__':main()
