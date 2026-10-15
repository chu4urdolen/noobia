"""Extract named ELF of_device_id objects with checked ARM64 layout."""
import struct,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent.parent/'linux-port'))
from image_formats import elf64
def of_match_tables(raw):
    parsed=elf64(raw);symbols=parsed['sections'].get('.symtab',b'');names=parsed['sections'].get('.strtab',b'')
    shoff=struct.unpack_from('<Q',raw,40)[0];shsize,shcount=struct.unpack_from('<HH',raw,58)
    tables=[]
    for offset in range(0,len(symbols),24):
        no,info,_,section,value,size=struct.unpack_from('<IBBHQQ',symbols,offset)
        end=names.find(b'\0',no)
        if end<0:continue
        name=names[no:end].decode(errors='replace')
        if 'of_match' not in name or info&15!=1 or not 0<section<shcount or not size or size%200:continue
        header=struct.unpack_from('<IIQQQQIIQQ',raw,shoff+section*shsize)
        if value+size>header[5]:continue
        data=raw[header[4]+value:header[4]+value+size];rows=[]
        try:
            for start in range(0,size,200):
                item=data[start:start+200];compatible=item[64:192].split(b'\0',1)[0].decode('ascii')
                if compatible and ',' not in compatible:raise ValueError('Unexpected compatible')
                if compatible:rows.append(compatible)
        except (ValueError,UnicodeError):continue
        if rows:tables.append({'symbol':name,'size':size,'compatibles':rows})
    return tables
