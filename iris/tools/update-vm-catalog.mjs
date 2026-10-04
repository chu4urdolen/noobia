#!/usr/bin/env node
import fs from 'node:fs';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../..');
const descriptions = JSON.parse(fs.readFileSync(path.join(root, 'iris/programs/descriptions.json'), 'utf8'));
const natives = JSON.parse(fs.readFileSync(path.join(root, 'iris/config/functions.json'), 'utf8'));
const nativeNames = new Map(natives.functions.map(f => [f.code, f.name]));
const retired = new Map([[107, 'CAMERA_VIDEO'], [112, 'RSSI_ON'], [113, 'RSSI_OFF']]);
const programs = [];
for (const [directory, notes] of [['iris/programs', descriptions.programs], ['esp/common/programs', descriptions.common_programs]]) {
  const files = fs.readdirSync(path.join(root, directory)).filter(f => f.endsWith('.hex')).sort();
  for (const file of files) {
    const name = file.slice(0, -4);
    if (!notes[name]) throw new Error(`missing VM description: ${name}`);
    const hex = fs.readFileSync(path.join(root, directory, file), 'utf8').trim();
    if (!/^(?:[a-f0-9]{2})+$/i.test(hex)) throw new Error(`bad hex: ${file}`);
    const bytes = Buffer.from(hex, 'hex'), boundaries = new Set(), jumps = [], calls = new Set();
    let pc = 0;
    while (pc < bytes.length) {
      const start = pc; boundaries.add(start);
      const op = bytes[pc++];
      const fixed = new Map([[0,0],[1,5],[2,2],[3,3],[4,3],[5,3],[6,3],[0x10,2],[0x11,3],[0x12,3],[0x13,2],[0x14,0],[0x21,2],[0x30,2],[0x31,2]]);
      if (op === 0x20 || op === 0x22) {
        if (pc + 4 > bytes.length) throw new Error(`truncated syscall: ${file}`);
        calls.add(bytes.readUInt16LE(pc+1));
        pc += 4 + bytes[pc+3];
        if (op === 0x22) pc += 1 + bytes[pc];
      } else if (fixed.has(op)) {
        if ([0x10,0x11,0x12,0x13].includes(op)) {
          const offset = pc + (op === 0x11 || op === 0x12 ? 1 : 0);
          if (offset+2 > bytes.length) throw new Error(`truncated jump: ${file}`);
          jumps.push(bytes.readUInt16LE(offset));
        }
        pc += fixed.get(op);
      } else throw new Error(`unknown opcode ${op}: ${file}`);
      if (!Number.isFinite(pc) || pc > bytes.length) throw new Error(`truncated instruction: ${file}`);
    }
    for (const target of jumps) if (!boundaries.has(target)) throw new Error(`invalid jump ${target}: ${file}`);
    const unknown = [...calls].filter(id => !nativeNames.has(id) && !retired.has(id));
    if (unknown.length) throw new Error(`unknown syscall ${unknown}: ${file}`);
    programs.push({name, path: `${directory}/${file}`, bytes: bytes.length, description: notes[name],
      status: [...calls].some(id => retired.has(id)) ? 'retired' : 'available_in_source',
      requires: [...calls].sort((a,b)=>a-b).map(code => ({code, name: nativeNames.get(code) || retired.get(code)}))});
  }
  for (const name of Object.keys(notes)) if (!files.includes(name+'.hex')) throw new Error(`description without VM: ${name}`);
}
const content = JSON.stringify({schema_version:1, programs}, null, 2)+'\n';
const output = path.join(root, 'iris/programs/catalog.json');
if (process.argv.includes('--check')) {
  if (fs.readFileSync(output, 'utf8') !== content) throw new Error('stale VM catalog');
} else fs.writeFileSync(output, content);
console.log(`${programs.length} VMs documented; bytecode boundaries, jumps and syscall IDs checked`);
