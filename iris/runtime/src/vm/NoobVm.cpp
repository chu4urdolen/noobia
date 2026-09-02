#include "vm/NoobVm.h"
#include <cstring>

namespace {
const char *stateName(VmState state) {
  switch (state) {
    case VmState::EMPTY: return "EMPTY";
    case VmState::READY: return "READY";
    case VmState::RUNNING: return "RUNNING";
    case VmState::WAITING: return "WAITING";
    case VmState::HALTED: return "HALTED";
    case VmState::STOPPED: return "STOPPED";
    case VmState::FAULT: return "FAULT";
  }
  return "UNKNOWN";
}
}

NoobVm::NoobVm(NativeRegistry &natives) : natives_(natives) {}

bool NoobVm::load(const uint8_t *program, size_t length, String &error) {
  if (!program || !length || length > PROGRAM_BYTES) {
    error = "program size must be 1..1024 bytes";
    return false;
  }
  if (state_ == VmState::RUNNING || state_ == VmState::WAITING) {
    error = "stop VM before replacing program";
    return false;
  }
  memcpy(program_, program, length);
  programLength_ = length;
  pc_ = 0;
  stackDepth_ = 0;
  memset(registers_, 0, sizeof(registers_));
  memset(memory_, 0, sizeof(memory_));
  faultMessage_ = "";
  state_ = VmState::READY;
  return true;
}

bool NoobVm::run(String &error) {
  if (!programLength_) {
    error = "no program loaded";
    return false;
  }
  if (state_ == VmState::RUNNING || state_ == VmState::WAITING) {
    error = "VM already running";
    return false;
  }
  pc_ = 0;
  stackDepth_ = 0;
  state_ = VmState::RUNNING;
  return true;
}

void NoobVm::stop() {
  if (state_ == VmState::RUNNING || state_ == VmState::WAITING) {
    state_ = VmState::STOPPED;
  }
}

void NoobVm::reset() {
  programLength_ = 0;
  pc_ = 0;
  stackDepth_ = 0;
  memset(program_, 0, sizeof(program_));
  memset(memory_, 0, sizeof(memory_));
  memset(registers_, 0, sizeof(registers_));
  faultMessage_ = "";
  state_ = VmState::EMPTY;
}

void NoobVm::tick(size_t instructionBudget) {
  if (state_ == VmState::WAITING) {
    if (static_cast<int32_t>(millis() - wakeAt_) < 0) return;
    state_ = VmState::RUNNING;
  }
  while (state_ == VmState::RUNNING && instructionBudget--) executeOne();
}

VmState NoobVm::state() const { return state_; }

String NoobVm::status() const {
  String result = String("state=") + stateName(state_) + " pc=" + pc_ +
                  " bytes=" + programLength_ + " regs=";
  for (size_t index = 0; index < REGISTER_COUNT; ++index) {
    if (index) result += ',';
    result += String(registers_[index]);
  }
  if (!faultMessage_.isEmpty()) result += " fault=" + faultMessage_;
  return result;
}

int32_t NoobVm::reg(uint8_t index) const {
  return index < REGISTER_COUNT ? registers_[index] : 0;
}

bool NoobVm::need(size_t bytes) {
  if (pc_ + bytes <= programLength_) return true;
  fault("truncated instruction");
  return false;
}

uint8_t NoobVm::read8() { return program_[pc_++]; }

uint16_t NoobVm::read16() {
  const uint16_t value = program_[pc_] | (program_[pc_ + 1] << 8);
  pc_ += 2;
  return value;
}

int32_t NoobVm::read32() {
  uint32_t value = 0;
  for (uint8_t shift = 0; shift < 32; shift += 8) value |= uint32_t(read8()) << shift;
  return static_cast<int32_t>(value);
}

bool NoobVm::validRegister(uint8_t index) {
  if (index < REGISTER_COUNT) return true;
  fault("invalid register");
  return false;
}

void NoobVm::fault(const String &message) {
  faultMessage_ = message;
  state_ = VmState::FAULT;
}

void NoobVm::executeOne() {
  // Bytecode is intentionally compact and little-endian. Opcodes are grouped
  // by purpose: 0x0 arithmetic, 0x1 control flow, 0x2 services/timing, and
  // 0x3 memory. See VM.md for the stable version-1 encoding.
  if (!need(1)) return;
  const uint8_t opcode = read8();
  if (opcode == 0x00) { state_ = VmState::HALTED; return; }
  if (opcode == 0x01) {
    if (!need(5)) return; uint8_t d = read8(); int32_t v = read32();
    if (validRegister(d)) registers_[d] = v; return;
  }
  if (opcode == 0x02) {
    if (!need(2)) return; uint8_t d = read8(), s = read8();
    if (validRegister(d) && validRegister(s)) registers_[d] = registers_[s]; return;
  }
  if (opcode >= 0x03 && opcode <= 0x06) {
    if (!need(3)) return; uint8_t d=read8(),a=read8(),b=read8();
    if (!validRegister(d)||!validRegister(a)||!validRegister(b)) return;
    if (opcode==0x03) registers_[d]=registers_[a]+registers_[b];
    if (opcode==0x04) registers_[d]=registers_[a]-registers_[b];
    if (opcode==0x05) registers_[d]=registers_[a]*registers_[b];
    if (opcode==0x06) { if (!registers_[b]) { fault("division by zero"); return; } registers_[d]=registers_[a]/registers_[b]; }
    return;
  }
  if (opcode == 0x10) {
    if (!need(2)) return; uint16_t target=read16();
    if (target>=programLength_) { fault("jump outside program"); return; } pc_=target; return;
  }
  if (opcode == 0x11 || opcode == 0x12) {
    if (!need(3)) return; uint8_t r=read8(); uint16_t target=read16();
    if (!validRegister(r)) return; bool take=opcode==0x11?registers_[r]==0:registers_[r]!=0;
    if (take) { if (target>=programLength_) { fault("jump outside program"); return; } pc_=target; } return;
  }
  if (opcode == 0x13) {
    if (!need(2)) return; uint16_t target=read16();
    if (target>=programLength_||stackDepth_>=CALL_DEPTH) { fault("invalid call"); return; }
    returnStack_[stackDepth_++]=pc_; pc_=target; return;
  }
  if (opcode == 0x14) {
    if (!stackDepth_) { fault("return stack empty"); return; }
    pc_=returnStack_[--stackDepth_]; return;
  }
  if (opcode == 0x20) {
    if (!need(4)) return; uint8_t d=read8(); uint16_t id=read16(); uint8_t count=read8();
    if (!validRegister(d)||count>REGISTER_COUNT||!need(count)) return;
    int32_t args[REGISTER_COUNT]={};
    for (uint8_t i=0;i<count;++i) { uint8_t r=read8(); if (!validRegister(r)) return; args[i]=registers_[r]; }
    // Hardware never appears in the VM switch. A numeric ID resolves through
    // the registry populated by the physical Noob during initialization.
    const NativeEntry *entry=natives_.find(id); if (!entry) { fault("unknown syscall"); return; }
    NativeResult result=entry->function(args,count); if (!result.ok) { fault("syscall "+String(id)+": "+result.detail); return; }
    registers_[d]=result.value; return;
  }
  if (opcode == 0x21) {
    if (!need(2)) return; wakeAt_=millis()+read16(); state_=VmState::WAITING; return;
  }
  if (opcode == 0x30) {
    if (!need(2)) return; uint8_t d=read8(),address=read8(); if (validRegister(d)) registers_[d]=memory_[address]; return;
  }
  if (opcode == 0x31) {
    if (!need(2)) return; uint8_t address=read8(),s=read8(); if (validRegister(s)) memory_[address]=registers_[s]&0xff; return;
  }
  fault("unknown opcode " + String(opcode));
}
