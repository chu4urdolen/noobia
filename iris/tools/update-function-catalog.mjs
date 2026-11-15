#!/usr/bin/env node
// Generate metadata and its boot plan together; no names, IDs or test policies drift.
import fs from 'node:fs';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../..');
const board = 'iris/firmware/iris_noob/src/noobs/iris/';
const policy = JSON.parse(fs.readFileSync(path.join(root, 'iris/config/test-policies.json'), 'utf8'));
function codes(file) {
  const out = new Map();
  for (const m of fs.readFileSync(path.join(root, file), 'utf8').matchAll(/constexpr\s+(?:unsigned|uint16_t)\s+(\w+)\s*=\s*(\d+)\s*;/g))
    out.set(m[1], Number(m[2]));
  return out;
}
const ids = {IrisFunctions: codes(board + 'iris_config.h'),
  CommonFunctionIds: codes('esp/common/src/core/noob_function_ids.h')};
const functions = [];
for (const file of [board + 'iris.cpp', 'esp/common/src/core/noob_runtime_core.cpp']) {
  const text = fs.readFileSync(path.join(root, file), 'utf8');
  const pattern = /natives(?:\(\)|_)\.add(Text|Mixed)?\(\s*(IrisFunctions|CommonFunctionIds)::(\w+)\s*,\s*"([^"]+)"/g;
  for (const m of text.matchAll(pattern)) {
    const code = ids[m[2]].get(m[3]);
    if (code === undefined) throw new Error(`missing code: ${m[3]}`);
    const group = (policy.groups || []).find(g => new RegExp(g.pattern).test(m[4]));
    const testing = policy.functions[m[4]] || group?.policy || policy.default;
    functions.push({code, name: m[4], owner: m[2] === 'CommonFunctionIds' ? 'common' : 'Iris',
      source: file, arguments: m[4] === 'SEQUENCE_SET' ? 'numbers_or_text_config_or_mixed' :
        ['RSSI_THREAD_START', 'ENV_THREAD_START'].includes(m[4]) ? 'numbers_and_optional_ascii' :
        m[1] === 'Mixed' ? 'numbers_and_ascii' : m[1] === 'Text' ? 'ascii' : 'numbers',
      availability: m[4].startsWith('GPIO_') ? 'disabled_in_current_build' : 'registered_when_service_enabled',
      testable: testing.testable, auto_testable: testing.mode === 'boot_read_only' || testing.mode === 'boot_sensor',
      test: {mode: testing.mode, args: testing.args || [], ascii: testing.ascii || "", assertion: testing.assertion,
             review_required: !policy.functions[m[4]] && !group},
      recovery: testing.recovery || {action: 'none', max_attempts: 1, automatic: false}});
  }
}
functions.sort((a,b) => a.code - b.code);
if (new Set(functions.map(f => f.code)).size !== functions.length ||
    new Set(functions.map(f => f.name)).size !== functions.length) throw new Error('duplicate function');
for (const name of Object.keys(policy.functions))
  if (!functions.some(f => f.name === name)) throw new Error(`policy for missing function: ${name}`);
const dispatcher = fs.readFileSync(path.join(root, 'esp/common/src/commands/noob_command_dispatcher.cpp'), 'utf8');
const protocol_commands = [...new Set([...dispatcher.matchAll(/request\.command == "(\w+)"/g)].map(m => m[1]))];
const catalog = {schema_version: 1, noob: 'Iris',
  catalog_scope: 'Source registry inventory; use live CAPS to verify availability',
  protocol_commands,
  access: {native_vm: 'SYS/SYS_MIXED resolve registered IDs; disabled functions fail',
    sequence_channels: 'Numeric plus ASCII via SEQUENCE_SET mixed form; requires channel-capable firmware',
    protocol_controls: 'Host/transport commands, not sequence channel functions'},
  test_modes: {boot_read_only: 'No persistent mutation; API-level assertions only',
    boot_sensor: 'Bounded sensor read; ultrasonic emits a normal ranging pulse',
    on_demand: 'Needs arguments or can affect concurrent activity',
    manual_fixture: 'Needs user observation, a signal source or a disposable fixture',
    destructive_opt_in: 'Never run at boot; explicit disposable target and approval required',
    disabled: 'Not compiled into the normal firmware'}, functions};
const json = JSON.stringify(catalog, null, 2) + '\n';
const lines = ['#pragma once', '// Generated from iris/config/test-policies.json; do not hand-edit.',
  '#include "iris.h"', 'inline bool irisAddSelfTestPlan(NoobRuntime &runtime) {', '  bool ok = true;'];
let count = 0;
for (const f of functions.filter(f => f.auto_testable)) {
  const p = policy.functions[f.name];
  if (p.args?.length > 4 || !p.args?.every(Number.isInteger)) throw new Error(`bad arguments: ${f.name}`);
  const name = `args_${f.code}`;
  if (p.args.length) lines.push(`  const int32_t ${name}[] = {${p.args.join(', ')}};`);
  const retries = f.recovery;
  lines.push(`  ok &= runtime.selfTest().addProbe("${f.name}", ${f.code}, ${p.args.length ? name : 'nullptr'}, ${p.args.length}, ${retries.max_attempts}, ${retries.delay_ms || 0}, ${p.pending_on_failure ? 'true' : 'false'}, ${JSON.stringify(p.ascii || '')});`);
  ++count;
}
if (count > 40) throw new Error('boot plan exceeds probe budget');
lines.push('  return ok;', '}', '');
const outputs = [[path.join(root, 'iris/config/functions.json'), json],
  [path.join(root, board, 'iris_self_test_plan.h'), lines.join('\n')]];
const reference = ['# Iris command reference', '',
  'Generated from the source registry and test policies. Do not hand-edit.', '',
  '## Protocol controls', '',
  protocol_commands.map(name => '`' + name + '`').join(', ') + '.', '',
  'These control/inspect the runtime. START_THREAD/STOP_THREAD/THREAD_STATUS are',
  'aliases for RUN/STOP/STATUS; they do not select individual native sensor threads.', '',
  '## Native functions', '',
  'Invoke by name or ID with CALL, CALL_TEXT or CALL_MIXED. VM SYS/SYS_MIXED uses',
  'the same registry. Updated sequence channels support numeric plus ASCII',
  'arguments and optional bit forwarding. See CHANNEL_CALLS.md for the required',
  'firmware version and live-test results.',
  'Live CAPS is authoritative: a source entry does not guarantee enabled hardware.', '',
  '| ID | Function | Arguments | Test mode | Availability |',
  '| --- | --- | --- | --- | --- |',
  ...functions.map(f => `| ${f.code} | ${f.name} | ${f.arguments} | ${f.test.mode} | ${f.availability} |`), '',
  'Full test assertions and recovery limits: [functions.json](config/functions.json).',
  'Command framing/examples: [PROTOCOL.md](firmware/iris_noob/PROTOCOL.md).', '',
  'Regenerate with `node iris/tools/update-function-catalog.mjs` from the repo root.', ''];
outputs.push([path.join(root, 'iris/COMMANDS.md'), reference.join('\n')]);
const check = process.argv.includes('--check');
for (const [file, value] of outputs) {
  if (check) { if (fs.readFileSync(file, 'utf8') !== value) throw new Error(`stale generated file: ${file}`); }
  else fs.writeFileSync(file, value);
}
console.log(`${functions.length} functions; ${count} bounded boot probes; ${check ? 'catalog current' : 'catalog generated'}`);
