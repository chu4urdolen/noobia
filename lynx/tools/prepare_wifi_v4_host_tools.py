"""Create separate, pinned v4 host tools; preserve reviewed v3 tools verbatim."""
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
T = ROOT / 'tools'
SHA = '0abe578cdc82a8f42b6bd812f3217dcc622f2a980d93e3c3418bc6dadf731af7'


def replace_once(source, before, after):
    assert source.count(before) == 1, before
    return source.replace(before, after, 1)


def save(name, source):
    target = T / name
    assert not target.exists(), 'Preserve generated tools: ' + name
    target.write_text(source)


def main():
    source = (T / 'test_wifi_image_vm.py').read_text()
    source = source.replace('busybox-wifi-ssh-twostage-v3', 'busybox-wifi-ssh-twostage-v4')
    source = source.replace("prefix='emulated-wifi-image-'", "prefix='emulated-wifi-v4-image-'")
    save('test_wifi_v4_image_vm.py', source)

    source = (T / 'validate_wifi_image.py').read_text()
    source = source.replace('busybox-wifi-ssh-twostage-v3', 'busybox-wifi-ssh-twostage-v4')
    source = source.replace('3a1c2ddacac0c6fdf7e152a2db30add1b1b4fbab881346d6d346faf584abf94c', SHA)
    source = replace_once(source, "'etc/lynx/payload-sha256'}", "'etc/lynx/payload-sha256','etc/lynx/session-token','etc/lynx/diag-stage.sh','etc/lynx/diag-hooks.sh','etc/lynx/diag-codebook.json'}")
    source = replace_once(source,
        " require((P/'lynx-boot-payload-readonly.sh').read_bytes() in init and (P/'lynx-wifi-bootstrap-runtime.sh').read_bytes() in init,'Bootstrap source changed')",
        """ expected_bootstrap=(P/'lynx-wifi-bootstrap-runtime.sh').read_bytes().replace(b'lynx_wifi_bootstrap_child() {',b'lynx_wifi_bootstrap_child_unlogged() {',1).replace(b'    boot_seen=0\\n',b\"    log 'BOOTSTRAP_PARTITION_DISCOVERY'\\n    boot_seen=0\\n\",1)
 require((P/'lynx-boot-payload-readonly.sh').read_bytes() in init and expected_bootstrap in init,'Bootstrap source changed')
 require(first['etc/lynx/diag-stage.sh']['data']==(P/'lynx-diag-stage.sh').read_bytes(),'Logger source changed')
 require(first['etc/lynx/diag-hooks.sh']['data']==(F/'diag-hooks.sh').read_bytes(),'Frozen hooks changed')
 require(b'. /etc/lynx/diag-stage.sh || stop' in init and b'. /etc/lynx/diag-hooks.sh || stop' in init,'Diagnostic integration missing')""")
    source = replace_once(source,
        " require(extra['etc/lynx/wifi-runtime.sh']['data']==(P/'lynx-wifi-runtime.sh').read_bytes(),'Wi-Fi runtime source changed')",
        " require(extra['etc/lynx/wifi-runtime.sh']['data']==(P/'lynx-wifi-runtime.sh').read_bytes().replace(b'lynx_wifi_worker() {',b'lynx_wifi_worker_unlogged() {',1)==(F/'wifi-runtime.sh').read_bytes(),'Wi-Fi runtime source changed')")
    source = replace_once(source, "'emulated-wifi-image-*/result.json'", "'emulated-wifi-v4-image-*/result.json'")
    source = replace_once(source, "out=P/'docs/wifi-image-validation.json'", "out=P/'docs/wifi-v4-image-validation.json'")
    marker = " model=ROOT/'tools/avb-host/avb-boot-model'"
    add = """ supplier=json.loads((P/'docs/ufs-reset-supplier-audit.json').read_text());require(supplier['passed'] and not supplier['imported_symbol_crc_conflicts'],'Reset supplier ABI failed')
 require(storage[0]=='reset-ti-syscon.ko' and digest(combined['lib/modules/reset-ti-syscon.ko']['data'])==supplier['reset_module_sha256'],'Reset supplier load/bytes changed')
 require(first['etc/lynx/session-token']['data'].decode().strip()==report['session_token'] and json.loads(first['etc/lynx/diag-codebook.json']['data'])==report['diagnostic_codebook'],'Session/codebook differs')
 integrations=sorted((P/'artifacts').glob('emulated-wifi-v4-journals-*/result.json'));require(integrations,'Native journal integration test missing');integration=json.loads(integrations[-1].read_text())
 require(integration['passed'] and integration['candidate_sha256']==IMAGE_SHA and integration['logger_sha256']==digest(first['etc/lynx/diag-stage.sh']['data']) and integration['hooks_sha256']==digest(first['etc/lynx/diag-hooks.sh']['data']) and integration['wifi_runtime_sha256']==digest(extra['etc/lynx/wifi-runtime.sh']['data']),'Journal integration tested source mismatch')
"""
    source = replace_once(source, marker, add + marker)
    save('validate_wifi_v4_image.py', source)

    source = (T / 'lynx_boot_a_wifi_trial.py').read_text()
    source = source.replace('busybox-wifi-ssh-twostage-v3', 'busybox-wifi-ssh-twostage-v4')
    source = source.replace('3a1c2ddacac0c6fdf7e152a2db30add1b1b4fbab881346d6d346faf584abf94c', SHA)
    source = source.replace('validate_wifi_image.py', 'validate_wifi_v4_image.py')
    source = source.replace("'boot-a-wifi-trial-'", "'boot-a-wifi-v4-trial-'")
    source = replace_once(source, "report = {'network_goal':", "report = {'diagnostic_journals':['supervisor','bootstrap','wifi'], 'physical_log_persistence_verified':False, 'network_goal':")
    save('lynx_boot_a_wifi_v4_trial.py', source)

    source = (T / 'lynx_wifi_contact.py').read_text()
    source = source.replace('busybox-wifi-ssh-twostage-v3', 'busybox-wifi-ssh-twostage-v4')
    source = source.replace("'wifi-contact-'", "'wifi-v4-contact-'")
    source = replace_once(source, 'from pathlib import Path', 'from pathlib import Path\nfrom lynx_decode_stages import decode')
    source = replace_once(source,
        "   a=subprocess.run(ssh_command(ip,ack),capture_output=True,timeout=15);(out/'ack.raw').write_bytes(a.stdout+a.stderr);report['fallback_cancel_ack_exit_code']=a.returncode;save()",
        """   try:
    a=subprocess.run(ssh_command(ip,ack),capture_output=True,timeout=15);(out/'ack.raw').write_bytes(a.stdout+a.stderr);report['fallback_cancel_ack_exit_code']=a.returncode;save()
   except subprocess.TimeoutExpired as e:
    (out/'ack.raw').write_bytes((e.stdout or b'')+(e.stderr or b''));report.update(state='identity-proved-ack-timeout',fallback_cancel_ack_timed_out=True);save();return
   if a.returncode!=0:report['state']='identity-proved-ack-failed';save();return""")
    marker = "   report['state']='native-ssh-available';save();print('Saved diagnostics:',out,flush=True);return"
    add = """   report['journals']={}
   for owner in ['supervisor','bootstrap','wifi']:
    entry={};report['journals'][owner]=entry
    try:
     j=subprocess.run(ssh_command(ip,'cat /run/lynx/stages-'+owner+'.hex'),capture_output=True,timeout=15)
     (out/(owner+'.hex')).write_bytes(j.stdout);(out/(owner+'-stderr.raw')).write_bytes(j.stderr);entry['retrieval_exit_code']=j.returncode
     if j.returncode==0:
      decoded=decode(j.stdout,BUILD['session_token']);decoded['identity_authenticated']=True
      for record in decoded['records']:record['stage']=BUILD['diagnostic_codebook'].get(str(int(record['stage_hex'],16)),record['stage'])
      (out/(owner+'-decoded.json')).write_text(json.dumps(decoded,indent=2)+'\\n');entry.update(records=len(decoded['records']),valid=decoded['complete_sequences_and_checksums'])
    except subprocess.TimeoutExpired as e:
     (out/(owner+'.hex')).write_bytes(e.stdout or b'');(out/(owner+'-stderr.raw')).write_bytes(e.stderr or b'');entry['retrieval_timed_out']=True
    save()
"""
    source = replace_once(source, marker, add + marker)
    save('lynx_wifi_v4_contact.py', source)
    print('Created separate pinned v4 validation, VM, trial and journal collector tools; no phone contacted.')


if __name__ == '__main__':
    main()
