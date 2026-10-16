"""Execute real battery-monitor C with mocked I2C and exact register checks."""
import hashlib
import json
import os
import subprocess
import time
from pathlib import Path

from test_gauge_sample_logic import MOCKS, ROOT

TESTS = r'''
static struct i2c_adapter adapter;
static struct i2c_client client;
static void reset(void) {
 path_present=compatible=bq_flag=1; read_calls=node_puts=0; lock_depth=0;
 sampled_device=NULL; allow_reads=true; confirmed_device_type=0xa5ff;
 adapter.nr=7; client=(struct i2c_client){{&expected_node},0x55,0,&adapter};
 values[0]=2937; values[1]=7800; values[2]=64053; values[3]=52;
}
#define REFUSE(change) do { reset(); change; assert(battery_probe(&client)<0); assert(read_calls==0); } while(0)
int main(void) {
 char buf[4096];
 assert(battery_init()==-EPERM && registered==0);
 reset(); confirmed_device_type=0xffa5; assert(battery_init()==-EPERM && registered==0);
 REFUSE(allow_reads=false); REFUSE(confirmed_device_type=0); REFUSE(path_present=0);
 REFUSE(client.dev.of_node=&other_node); REFUSE(client.addr=0x54); REFUSE(adapter.nr=6);
 REFUSE(client.flags=I2C_CLIENT_TEN); REFUSE(compatible=0); REFUSE(bq_flag=0);
 REFUSE(sampled_device=&client.dev);
 reset(); assert(battery_probe(&client)==0 && read_calls==0);
 assert(battery_snapshot_show(&client.dev,NULL,buf)>0 && read_calls==4 && lock_depth==0);
 assert(strstr(buf,"temperature_millidegrees_celsius=20600\n"));
 assert(strstr(buf,"gauge_current_ma_signed=-1483\n"));
 assert(strstr(buf,"pack_voltage_mv=7800\n") && strstr(buf,"capacity_percent=52\n"));
 assert(strstr(buf,"temperature_error=0\n") && strstr(buf,"capacity_error=0\n"));
 values[0]=2940; values[2]=2;
 assert(battery_snapshot_show(&client.dev,NULL,buf)>0 && read_calls==8);
 assert(strstr(buf,"temperature_millidegrees_celsius=20900\n") && strstr(buf,"gauge_current_ma_signed=2\n"));
 assert(battery_snapshot_show(&(struct device){0},NULL,buf)==-ENODATA && read_calls==8);
 reset(); assert(battery_probe(&client)==0);
 values[0]=-EIO; values[1]=-ENXIO; values[2]=-EREMOTEIO; values[3]=-EINVAL;
 assert(battery_snapshot_show(&client.dev,NULL,buf)>0 && read_calls==4);
 assert(strstr(buf,"temperature_error=-5\n") && strstr(buf,"voltage_error=-6\n"));
 assert(strstr(buf,"current_error=-121\n") && strstr(buf,"capacity_error=-22\n"));
 reset(); assert(battery_probe(&client)==0);
 values[0]=65535; values[1]=0; values[2]=65535; values[3]=101;
 assert(battery_snapshot_show(&client.dev,NULL,buf)>0);
 assert(strstr(buf,"temperature_error=-34\n") && strstr(buf,"voltage_error=-34\n") && strstr(buf,"capacity_error=-34\n"));
 assert(strstr(buf,"gauge_current_ma_signed=-1\n") && strstr(buf,"current_error=0\n"));
 values[0]=2731; values[1]=8000; values[2]=32768; values[3]=0;
 assert(battery_snapshot_show(&client.dev,NULL,buf)>0);
 assert(strstr(buf,"temperature_millidegrees_celsius=0\n") && strstr(buf,"temperature_error=0\n"));
 assert(strstr(buf,"gauge_current_ma_signed=-32768\n") && strstr(buf,"capacity_error=0\n"));
 values[0]=3981; values[2]=32767; values[3]=100;
 assert(battery_snapshot_show(&client.dev,NULL,buf)>0);
 assert(strstr(buf,"temperature_millidegrees_celsius=125000\n") && strstr(buf,"temperature_error=0\n"));
 assert(strstr(buf,"gauge_current_ma_signed=32767\n"));
 battery_exit(); assert(!sampled_device && released==1);
 reset(); assert(battery_init()==0 && registered==1 && read_calls==0); battery_exit();
 puts("PASS: ten client guards; model/default refusal; fixed four-register reads under mutex; live refresh; partial errors; signed current and temperature/range boundaries");
 return 0;
}
'''


def main():
    source = ROOT / 'linux-port/lynx-battery-monitor.c'
    raw = source.read_bytes()
    mocks = MOCKS.replace('read_calls, read_result', 'read_calls')
    start = mocks.index('static int i2c_smbus_read_word_data(')
    end = mocks.index('#define dev_info', start)
    mocks = mocks[:start] + r'''
typedef unsigned char u8;
#define ARRAY_SIZE(a) (sizeof(a)/sizeof((a)[0]))
#define DEFINE_MUTEX(n) int n
static int lock_depth;
static int values[4];
static void mutex_lock(int *m) { (void)m; assert(lock_depth==0); lock_depth=1; }
static void mutex_unlock(int *m) { (void)m; assert(lock_depth==1); lock_depth=0; }
static struct i2c_client *to_i2c_client(struct device *d) { return (struct i2c_client *)d; }
static int i2c_smbus_read_word_data(struct i2c_client *c, unsigned char reg) {
 static const unsigned char allowed[]={0x06,0x08,0x0c,0x2c};
 assert(lock_depth==1 && c->addr==0x55 && c->adapter->nr==7 && reg==allowed[read_calls%4]);
 return values[(read_calls++)%4];
}
''' + mocks[end:]
    body='\n'.join(l for l in raw.decode().splitlines() if not l.startswith('#include '))
    out=ROOT/'linux-port/artifacts'/('battery-monitor-logic-'+str(time.time_ns()));out.mkdir(mode=0o700)
    (out/'harness.c').write_text(mocks+'\n'+body+'\n'+TESTS)
    build=subprocess.run(['cc','-std=c11','-Wall','-Wextra','-Werror','-Wno-unused-parameter',str(out/'harness.c'),'-o',str(out/'test')],capture_output=True,timeout=30,env=dict(os.environ,TMPDIR=str(out)))
    (out/'build.stdout').write_bytes(build.stdout);(out/'build.stderr').write_bytes(build.stderr)
    result={'passed':False,'source_sha256':hashlib.sha256(raw).hexdigest(),'build_exit_code':build.returncode,'phone_contacted':False,'kernel_abi_or_hardware_tested':False}
    if build.returncode==0:
        p=subprocess.run([str(out/'test')],capture_output=True,timeout=5);(out/'run.stdout').write_bytes(p.stdout);(out/'run.stderr').write_bytes(p.stderr);result.update(passed=p.returncode==0,run_exit_code=p.returncode)
    (out/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps({'result':str(out/'result.json'),**result},indent=2))
    if not result['passed']:raise SystemExit(1)


if __name__=='__main__':main()
