"""Offline inventory of diagnostic strings in Lynx's verified stock LK."""
import hashlib
import json
from pathlib import Path
import re

ROOT=Path(__file__).resolve().parent.parent
IMAGE=ROOT/'linux-port/artifacts/stock-cph2493-August-eu-ota/lk.img'
EXPECTED='78db9e36426faa5f20487a39f136eecea785a9122cfe1fc25056a758953d7231'

def inventory(data):
    records=[]
    for match in re.finditer(rb'[\x20-\x7e]{6,}',data):
        value=match.group().decode('ascii')
        if re.search(r'oem |pstore|expdb|ramconsole|kernel.{0,30}log|dump.{0,30}log|boot.{0,20}log',value,re.I):
            records.append(dict(file_offset=hex(match.start()),text=value))
    return records

def main():
    assert inventory(b'\x00oem dump_pllk_log\x00unrelated string\x00')==[
        dict(file_offset='0x1',text='oem dump_pllk_log')]
    data=IMAGE.read_bytes()
    digest=hashlib.sha256(data).hexdigest()
    if digest!=EXPECTED: raise RuntimeError('Stock LK image changed')
    strings=inventory(data)
    report=dict(phone_contacted=False,stock_lk_sha256=digest,strings=strings,
                limits='Strings alone do not prove command registration, read-only semantics or retrieval of kernel logs.')
    target=ROOT/'linux-port/docs/stock-lk-log-string-inventory.json'
    target.write_text(json.dumps(report,indent=2)+'\n')
    print('Preserved',len(strings),'diagnostic strings:',target)
    for record in strings:
        if record['text'].startswith('oem '): print(record['file_offset'],record['text'])

if __name__=='__main__': main()
