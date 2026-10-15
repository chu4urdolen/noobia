"""Preserve the passing bare-root test; add the actual stock vendor ramdisk."""
from pathlib import Path
R=Path(__file__).resolve().parent.parent
s=(R/'tools/test_native_payload_step_loop.py').read_text()
s=s.replace('emulated-native-payload-step-loop-','emulated-native-vendor-payload-loop-')
anchor="(out/'initramfs').write_bytes(pack(entries))"
assert s.count(anchor)==1
s=s.replace(anchor,"(out/'initramfs').write_bytes((P/'artifacts/stock-cph2493-August-eu-ota/unpacked-vendor-boot/vendor_ramdisk00').read_bytes()+pack(entries))")
out=R/'tools/test_native_vendor_payload_loop.py'
assert not out.exists();compile(s,str(out),'exec');out.write_text(s);print(out)
