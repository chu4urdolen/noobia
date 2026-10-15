"""Seal the working image locally; export a credential-free reconstruction recipe."""
import hashlib,json,os,shutil,struct,sys,time
from pathlib import Path
R=Path(__file__).resolve().parent.parent;P=R/'linux-port';sys.path.insert(0,str(P))
from image_formats import read_boot_v4,read_newc,require
from ramdisk_codec import decompress
def sha(data):return hashlib.sha256(data).hexdigest()
def main():
 os.umask(0o077)
 F=P/'artifacts/busybox-wifi-ssh-twostage-v19';raw=(F/'nord3-busybox-candidate.img').read_bytes();expected='5ce2dbf8a7c132fa7e31f6be70aa76f83afe8c293e2cd5f02251a532486fd851';require(sha(raw)==expected,'Working image differs')
 stockpath=P/'artifacts/stock-cph2493-August-eu-ota/boot.img';stock=stockpath.read_bytes();require(sha(stock)=='a67f03d7b826b834c23653b67eaa6efa971eb70ef8af19eee4d33fb5fc7fe995','Stock differs')
 private=R/'checkpoints/native-wifi-ssh-v19';public=P/'known-good-v19';require(not private.exists() and not public.exists(),'Preserve existing checkpoint')
 objects=private/'objects';objects.mkdir(parents=True,mode=0o700);public.mkdir(mode=0o755);runtime=public/'runtime';runtime.mkdir(mode=0o755)
 b=read_boot_v4(raw);payload=(F/'supplement.cpio.gz').read_bytes();coverage=struct.unpack('!4sIIQQQ28x',stock[-64:])[3];off=25165824
 require(raw[coverage:off]==stock[coverage:off] and raw[off+len(payload):]==stock[off+len(payload):],'Unexpected template differences')
 recipe={'version':1,'candidate_sha256':expected,'stock_boot_sha256':sha(stock),'image_bytes':len(raw),'coverage_bytes':coverage,'payload_offset':off,'header_changes':[[i,raw[i]] for i in range(1584) if raw[i]!=stock[i]],'kernel_sha256':sha(b['kernel']),'ramdisk_sha256':sha(b['ramdisk']),'supplement_sha256':sha(payload),'archives':{},'limits':'Private objects include credentials and proprietary assets; never publish the checkpoint or a bootable image. Source snapshots and hashes alone do not include firmware or keys.'}
 for label,data in [('primary',b['ramdisk']),('supplement',payload)]:
  entries=read_newc(decompress(data));records=[]
  for name,item in entries.items():
   content=item['data'];digest=sha(content);obj=objects/digest
   if not obj.exists():obj.write_bytes(content)
   rec={'name':name,**{k:v for k,v in item.items() if k!='data'},'sha256':digest,'bytes':len(content)}
   # Publish only our executable runtime source and module order lists.
   ours=(name=='init' or name in ['bin/boot-proof-reboot','bin/lynx-dhcp'] or name.startswith('etc/lynx/') and name.endswith(('.sh','.awk')) or name.endswith('modules.load'))
   if ours and item['mode']&0o170000==0o100000 and not content.startswith(b'\x7fELF'):
    content.decode('utf-8');dest=runtime/label/name;dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(content);dest.chmod(0o644);rec['public_source']=str(dest.relative_to(public))
   records.append(rec)
  recipe['archives'][label]=records
 for source,name in [(F/'nord3-busybox-candidate.img','working-boot.img'),(stockpath,'stock-boot.img'),(F/'build-validation.json','build-validation.json')]:shutil.copyfile(source,private/name)
 (public/'recipe.json').write_text(json.dumps(recipe,indent=2)+'\n');(public/'recipe.json').chmod(0o644)
 receipt={'created_ns':time.time_ns(),'working_image_sha256':expected,'stock_image_sha256':sha(stock),'private_object_count':len(list(objects.iterdir())),'public_recipe_sha256':sha((public/'recipe.json').read_bytes()),'phone_contacted':False,'private_checkpoint':str(private)}
 (private/'checkpoint.json').write_text(json.dumps(receipt,indent=2)+'\n');print(json.dumps(receipt,indent=2))
if __name__=='__main__':main()
