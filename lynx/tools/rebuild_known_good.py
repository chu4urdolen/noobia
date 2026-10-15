"""Reconstruct the exact hardware-proven V19 image offline; never flash.

Requires the private checkpoint's object cache and matching stock boot image.
Public runtime snapshots are verified against the recipe before packaging.
"""
import argparse,gzip,hashlib,json,os,struct,sys,time
from pathlib import Path
R=Path(__file__).resolve().parent.parent;P=R/'linux-port';sys.path.insert(0,str(P))
from image_formats import read_boot_v4,require
from prepare_busybox_diagnostics import pack
from ramdisk_codec import decompress
def sha(data):return hashlib.sha256(data).hexdigest()
def main():
 parser=argparse.ArgumentParser(description=__doc__)
 parser.add_argument('--objects',type=Path,default=R/'checkpoints/native-wifi-ssh-v19/objects')
 parser.add_argument('--stock-boot',type=Path,default=R/'checkpoints/native-wifi-ssh-v19/stock-boot.img')
 parser.add_argument('--output-dir',type=Path,required=True)
 args=parser.parse_args();os.umask(0o077)
 base=P/'known-good-v19';recipe=json.loads((base/'recipe.json').read_text());stock=args.stock_boot.read_bytes();require(sha(stock)==recipe['stock_boot_sha256'],'Wrong stock image');require(not args.output_dir.exists(),'Refuse to replace an output directory')
 archives={}
 for label,records in recipe['archives'].items():
  entries={}
  for rec in records:
   name=rec['name'];require(not name.startswith('/') and '..' not in Path(name).parts,'Invalid archive path')
   data=(args.objects/rec['sha256']).read_bytes();require(len(data)==rec['bytes'] and sha(data)==rec['sha256'],'Private input differs: '+name)
   if 'public_source' in rec:
    source=(base/rec['public_source']).resolve();require(source.is_relative_to(base.resolve()) and source.read_bytes()==data,'Public runtime source differs: '+name)
   entries[name]={k:rec[k] for k in ['mode','uid','gid','rdevmajor','rdevminor']};entries[name]['data']=data
  archives[label]=pack(entries)
 rd=archives['primary'];payload=gzip.compress(decompress(archives['supplement']),mtime=0)
 require(sha(rd)==recipe['ramdisk_sha256'] and sha(payload)==recipe['supplement_sha256'],'Compression differs from proven image')
 b=read_boot_v4(stock);require(sha(b['kernel'])==recipe['kernel_sha256'],'Kernel differs');header=bytearray(stock[:1584])
 for index,value in recipe['header_changes']:header[index]=value
 require(struct.unpack_from('<I',header,12)[0]==len(rd),'Ramdisk header differs')
 align=lambda n:(n+4095)//4096*4096
 loaded=bytes(header).ljust(4096,b'\0')+b['kernel'].ljust(align(len(b['kernel'])),b'\0')+rd.ljust(align(len(rd)),b'\0');coverage=recipe['coverage_bytes'];require(len(loaded)<=coverage,'Boot data overlaps metadata')
 image=bytearray(loaded.ljust(coverage,b'\0')+stock[coverage:]);off=recipe['payload_offset'];require(coverage<=off and off+len(payload)<len(image)-4096,'Supplement bounds differ');image[off:off+len(payload)]=payload;image=bytes(image)
 require(len(image)==recipe['image_bytes'] and sha(image)==recipe['candidate_sha256'],'Reconstruction is not byte-identical to the proven image')
 args.output_dir.mkdir(parents=True,mode=0o700);path=args.output_dir/'nord3-busybox-candidate.img';path.write_bytes(image)
 report={'created_ns':time.time_ns(),'passed':True,'candidate_sha256':sha(image),'bytes':len(image),'byte_identical_to_hardware_proven_v19':True,'recipe_sha256':sha((base/'recipe.json').read_bytes()),'phone_contacted':False,'flash_performed':False,'contains_private_credentials':True}
 (args.output_dir/'rebuild-result.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))
if __name__=='__main__':main()
