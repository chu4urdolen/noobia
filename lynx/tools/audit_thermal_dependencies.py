"""Offline audit of missing stock power/thermal drivers against saved live modules."""
import hashlib,json,re,sys,time
from pathlib import Path
R=Path(__file__).resolve().parent.parent;P=R/'linux-port';sys.path.insert(0,str(P))
from image_formats import module_metadata,require
STOCK=P/'artifacts/stock-cph2493-August-eu-ota'
TARGETS=['mediatek-cpufreq-hw.ko','soc_temp_lvts.ko','thermal_interface.ko','thermal-generic-adc.ko','mt6375-battery.ko','oplus_chg.ko','tcpc_mt6375.ko']
def normalized(n):return n.removesuffix('.ko').replace('-','_')
def main():
 inventory=R/'logs/live-inventory-1792098110330311623/inventory.stdout';text=inventory.read_text();loaded=set(line.split()[0] for line in text.split('MODULES\n',1)[1].splitlines() if re.match(r'^\w+ \d+ ',line))
 roots=[STOCK/'vendor-ramdisk-unpacked/lib/modules',STOCK/'wifi-reference/vendor-dlkm-unpacked/lib/modules'];index={};dep={}
 for root in roots:
  for f in root.glob('*.ko'):index.setdefault(normalized(f.name),f)
 records=[]
 for target in TARGETS:
  path=index[normalized(target)];raw=path.read_bytes();meta=module_metadata(raw)['values'];direct=[n for value in meta.get('depends',[]) for n in value.split(',') if n];order=[];active=set();missing=[]
  def visit(name):
   name=normalized(name)
   if name in order:return
   require(name not in active,'Dependency cycle: '+name);active.add(name)
   if name not in index:missing.append(name);active.remove(name);return
   if name not in dep:
    values=module_metadata(index[name].read_bytes())['values'];dep[name]=[n for value in values.get('depends',[]) for n in value.split(',') if n]
   for child in dep[name]:visit(child)
   order.append(name);active.remove(name)
  visit(normalized(target))
  records.append({'module':target,'stock_path':str(path.relative_to(STOCK)),'sha256':hashlib.sha256(raw).hexdigest(),'vermagic':meta['vermagic'],'aliases':meta.get('alias',[]),'direct_dependencies':direct,'dependency_order':order,'unresolved_dependencies':sorted(set(missing)),'loaded_in_saved_session':normalized(target) in loaded,'missing_from_live_dependency_closure':[n for n in order if n not in loaded]})
 config=(STOCK/'kernel-config.txt').read_text();flags={}
 for name in ['CONFIG_ARM_MEDIATEK_CPUFREQ_HW','CONFIG_MTK_SOC_THERMAL_LVTS','CONFIG_MTK_BOARD_THERMAL','CONFIG_MTK_PMIC_THERMAL','CONFIG_MTK_THERMAL_INTERFACE','CONFIG_CPU_FREQ_THERMAL','CONFIG_CPU_IDLE','CONFIG_THERMAL']:
  flags[name]=next((s.split('=',1)[1] for s in config.splitlines() if s.startswith(name+'=')),None)
 out=P/'docs'/('thermal-dependency-audit-'+str(time.time_ns())+'.json');report={'phone_contacted':False,'module_loads':False,'partition_writes':False,'saved_inventory':str(inventory),'kernel_config':flags,'targets':records,'limits':'Missing matched stock modules are a concrete explanation for unavailable interfaces, not proof of the heat source or a validated safe load plan. DT, clocks, regulators, firmware and side effects still require review.'};out.write_text(json.dumps(report,indent=2)+'\n');print(out);print(json.dumps({'config':flags,'targets':[{'module':r['module'],'loaded':r['loaded_in_saved_session'],'missing_dependencies':len(r['missing_from_live_dependency_closure']),'unresolved':r['unresolved_dependencies']} for r in records]},indent=2))
if __name__=='__main__':main()
