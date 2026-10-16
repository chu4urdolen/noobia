"""Compile the real reader C against mocks; test its guards and read count.

Tests driver logic only, not kernel ABI/CFI, bus timing, or physical hardware.
"""
import argparse
import hashlib
import json
import os
import subprocess
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SOURCE = ROOT / 'linux-port/lynx-gauge-sample.c'

MOCKS = r'''
#include <assert.h>
#include <stdbool.h>
#include <stdio.h>
#include <stdint.h>
#include <string.h>
#include <errno.h>
typedef int32_t s32;
typedef long ssize_t;
#define __init
#define __exit
#define PAGE_SIZE 4096
#define I2C_CLIENT_TEN 0x10
#define module_param(...)
#define MODULE_PARM_DESC(...)
#define MODULE_LICENSE(...)
#define MODULE_DESCRIPTION(...)
#define module_init(...)
#define module_exit(...)
#define scnprintf snprintf
struct device_node { int marker; };
struct device { struct device_node *of_node; };
struct i2c_adapter { int nr; };
struct i2c_client { struct device dev; unsigned short addr, flags; struct i2c_adapter *adapter; };
struct attribute { const char *name; };
struct device_attribute { struct attribute attr; ssize_t (*show)(struct device *, struct device_attribute *, char *); };
#define DEVICE_ATTR_RO(n) struct device_attribute dev_attr_##n = { { #n }, n##_show }
#define ATTRIBUTE_GROUPS(n) static void *n##_groups[] = { n##_attrs, NULL }
struct of_device_id { const char *compatible; };
struct i2c_driver { struct { const char *name; const struct of_device_id *of_match_table; void **dev_groups; } driver; int (*probe_new)(struct i2c_client *); };
static struct device_node expected_node, other_node;
static int path_present, compatible, bq_flag, read_calls, read_result;
static int registered, released, node_puts;
static struct device_node *of_find_node_by_path(const char *p) {
 assert(!strcmp(p, "/i2c@11d04000/bq27541-battery@55"));
 return path_present ? &expected_node : NULL;
}
static void of_node_put(struct device_node *n) { if(n) node_puts++; }
static bool of_device_is_compatible(struct device_node *n, const char *s) {
 assert(n == &expected_node); assert(!strcmp(s,"oplus,bq27541-battery")); return compatible;
}
static bool of_property_read_bool(struct device_node *n, const char *s) {
 assert(n == &expected_node); assert(!strcmp(s,"qcom,batt_bq28z610")); return bq_flag;
}
static int i2c_smbus_read_word_data(struct i2c_client *c, unsigned char reg) {
 assert(c->addr == 0x55 && c->adapter->nr == 7 && reg == 0x06);
 read_calls++; return read_result;
}
#define dev_info(...) ((void)0)
#define dev_err(...) ((void)0)
static int i2c_add_driver(struct i2c_driver *d) { assert(d->probe_new); registered++; return 0; }
static void i2c_del_driver(struct i2c_driver *d) { assert(d->probe_new); released++; }
'''

TESTS = r'''
static struct i2c_adapter adapter;
static struct i2c_client client;
static void reset(void) {
 path_present = compatible = bq_flag = 1; read_calls = node_puts = 0;
 read_result = 2981; sampled_device = NULL; allow_raw_read = true;
 adapter.nr = 7; client = (struct i2c_client) { { &expected_node }, 0x55, 0, &adapter };
}
#define REFUSE(change) do { reset(); change; assert(lynx_gauge_probe(&client) < 0); assert(read_calls == 0); } while(0)
int main(void) {
 char buf[4096];
 allow_raw_read = false;
 assert(lynx_gauge_init() == -EPERM && registered == 0);
 REFUSE(allow_raw_read = false);
 REFUSE(path_present = 0);
 REFUSE(client.dev.of_node = &other_node);
 REFUSE(client.addr = 0x54);
 REFUSE(adapter.nr = 6);
 REFUSE(client.flags = I2C_CLIENT_TEN);
 REFUSE(compatible = 0);
 REFUSE(bq_flag = 0);
 REFUSE(sampled_device = &client.dev);
 reset(); read_result = -EIO;
 assert(lynx_gauge_probe(&client) == -EIO && read_calls == 1 && !sampled_device);
 reset(); assert(lynx_gauge_probe(&client) == 0 && read_calls == 1 && node_puts == 1);
 assert(raw_temperature_word_show(&client.dev, NULL, buf) == 5 && !strcmp(buf,"2981\n"));
 assert(read_calls == 1); /* sysfs returns the cached word, no new bus transaction */
 assert(lynx_gauge_probe(&client) == -EPERM && read_calls == 1);
 assert(raw_temperature_word_show(&(struct device){0}, NULL, buf) == -ENODATA);
 lynx_gauge_exit(); assert(!sampled_device && released == 1);
 reset(); assert(lynx_gauge_init() == 0 && registered == 1 && read_calls == 0);
 lynx_gauge_exit();
 /* Raw sentinel values remain raw; this reader makes no safety interpretation. */
 reset(); read_result = 65535; assert(lynx_gauge_probe(&client) == 0);
 assert(raw_temperature_word_show(&client.dev,NULL,buf) == 6 && !strcmp(buf,"65535\n"));
 puts("PASS: default init refusal; nine probe guards; one read; no retry; cached sysfs; raw sentinel retained");
 return 0;
}
'''


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--identity-query', action='store_true')
    args = parser.parse_args()
    source_path = ROOT / 'linux-port/lynx-gauge-identity.c' if args.identity_query else SOURCE
    out = ROOT / 'linux-port/artifacts' / ('gauge-reader-logic-' + str(time.time_ns()))
    out.mkdir(mode=0o700)
    raw = source_path.read_bytes()
    body = '\n'.join(line for line in raw.decode().splitlines() if not line.startswith('#include '))
    mocks, tests = MOCKS, TESTS
    if args.identity_query:
        mocks = mocks.replace('reg == 0x06', 'reg == 0x00')
        mocks += r'''
static int write_calls, write_result, delay_calls;
static int i2c_smbus_write_word_data(struct i2c_client *c, unsigned char reg, unsigned short word) {
 assert(c->addr == 0x55 && c->adapter->nr == 7 && reg == 0x00 && word == 0x0001);
 write_calls++; return write_result;
}
static void msleep(unsigned int millis) { assert(millis == 20); delay_calls++; }
'''
        tests = tests.replace('allow_raw_read', 'allow_identity_query').replace('raw_temperature_word_show', 'raw_device_type_show')
        tests = tests.replace('read_result = 2981;', 'read_result = 2981; write_calls = write_result = delay_calls = 0;')
        tests = tests.replace('assert(read_calls == 0);', 'assert(read_calls == 0 && write_calls == 0);')
        tests = tests.replace('reset(); read_result = -EIO;', 'reset(); write_result = -EIO; assert(lynx_gauge_probe(&client) == -EIO && write_calls == 1 && read_calls == 0 && delay_calls == 0);\n reset(); read_result = -EIO;')
        tests = tests.replace('assert(read_calls == 1); /* sysfs', 'assert(read_calls == 1 && write_calls == 1 && delay_calls == 1); /* sysfs')
    source = out / 'harness.c'
    source.write_text(mocks + '\n' + body + '\n' + tests)
    env = dict(os.environ, TMPDIR=str(out))
    build = subprocess.run(['cc', '-std=c11', '-Wall', '-Wextra', '-Werror',
                            '-Wno-unused-parameter', str(source), '-o', str(out / 'test')],
                           capture_output=True, timeout=30, env=env)
    (out / 'build.stdout').write_bytes(build.stdout)
    (out / 'build.stderr').write_bytes(build.stderr)
    result = {'source_sha256': hashlib.sha256(raw).hexdigest(),
              'identity_query_variant': args.identity_query,
              'phone_contacted': False, 'kernel_abi_or_cfi_tested': False,
              'build_exit_code': build.returncode, 'passed': False}
    if build.returncode == 0:
        run = subprocess.run([str(out / 'test')], capture_output=True, timeout=5)
        (out / 'run.stdout').write_bytes(run.stdout)
        (out / 'run.stderr').write_bytes(run.stderr)
        result.update(run_exit_code=run.returncode, passed=run.returncode == 0)
    (out / 'result.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps({'receipt': str(out / 'result.json'), **result}, indent=2))
    if not result['passed']:
        raise SystemExit('Logic test failed; inspect saved compiler/test output')


if __name__ == '__main__':
    main()
