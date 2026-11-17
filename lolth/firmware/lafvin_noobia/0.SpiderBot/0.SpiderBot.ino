#include <Servo.h>
#include <EEPROM.h>
#include <IRrecv.h>
#include <IRutils.h>
#include "spiderbot_motion.h"
#include "webserver.h"

// IR receiver pin differs between the ESP32-C3 test target and the ESP8266 robot board.
#ifdef ARDUINO_ESP32C3_DEV
const uint16_t kRecvPin = 10;
#else
const uint16_t kRecvPin = D3;
#endif

IRrecv irrecv(kRecvPin);
decode_results results;

uint32_t irnum = 0;

// Avoidance distance threshold in centimeters.
#define AVOIDDIS 40
#define ENABLE_DEBUG_SERIAL 0

// The current avoidance wiring uses TX as TRIG and RX as ECHO.
static const uint8_t ULTRASONIC_TRIG_PIN = 1;  // TX
static const uint8_t ULTRASONIC_ECHO_PIN = 3;  // RX
static const unsigned long ULTRASONIC_TIMEOUT_US = 30000;

#if ENABLE_DEBUG_SERIAL
#define DEBUG_SERIAL_BEGIN(baud) Serial.begin(baud)
#define DEBUG_PRINT(value) Serial.print(value)
#define DEBUG_PRINTLN(value) Serial.println(value)
#define DEBUG_PRINT_HEX64(value) serialPrintUint64((value), HEX)
#else
#define DEBUG_SERIAL_BEGIN(baud) do {} while (0)
#define DEBUG_PRINT(value) do {} while (0)
#define DEBUG_PRINTLN(value) do {} while (0)
#define DEBUG_PRINT_HEX64(value) do {} while (0)
#endif

float distance = 0;

// Main robot motion object plus a few local helpers used by setup/loop.
SpiderBotMotion robot;
static int decodeIrProgram(uint32_t code);
static void runRobotProgram(int programId);
float measureDistanceCm();

// Board startup order:
// 1. bring up debug / IR / ultrasonic pins
// 2. start Wi-Fi + web server
// 3. attach servos and move to a known pose
void setup()
{
  DEBUG_SERIAL_BEGIN(9600);
  irrecv.enableIRIn();
  pinMode(ULTRASONIC_TRIG_PIN, OUTPUT);
  pinMode(ULTRASONIC_ECHO_PIN, INPUT);
  digitalWrite(ULTRASONIC_TRIG_PIN, LOW);
  DEBUG_PRINTLN("QuadBot-E Start!");
  delay(1000);

  webinit();
  robot.init();
  robot.Servo_PROGRAM_Zero();
  enableWebServer();
}

// Main loop responsibilities:
// 1. consume IR commands
// 2. serve HTTP requests
// 3. execute queued web/API actions
// 4. apply direct single-servo debug commands
void loop()
{
  if (irrecv.decode(&results)) {
    int programId = PROGRAM_NONE;

    DEBUG_PRINT_HEX64(results.value);
    irnum = (uint32_t)results.value;
    delay(150);
    irrecv.resume();

    programId = decodeIrProgram(irnum);
    if (programId != PROGRAM_NONE) {
      DEBUG_PRINTLN(getActionLabel(programId));
      runRobotProgram(programId);
    }

    DEBUG_PRINTLN(irnum);
    irnum = 0;
  }

  handleClient();

  if (Servo_PROGRAM >= 1) {
    DEBUG_PRINTLN(getActionLabel(Servo_PROGRAM));
    runRobotProgram(Servo_PROGRAM);
    Servo_PROGRAM = 0;
  }

  if (GPIO_ID < 100) {
    DEBUG_PRINT("GPIO_ID=");
    DEBUG_PRINTLN(GPIO_ID);
    DEBUG_PRINT("ival=");
    DEBUG_PRINTLN(ival);
    robot.DirectServoSet(GPIO_ID, ival.toInt());
    GPIO_ID = 100;
    ival = "";
  }
}

// Trigger a standard HC-SR04 style measurement and convert it to centimeters.
// Returns -1 when no echo is received before timeout.
float measureDistanceCm()
{
  digitalWrite(ULTRASONIC_TRIG_PIN, LOW);
  delayMicroseconds(2);
  digitalWrite(ULTRASONIC_TRIG_PIN, HIGH);
  delayMicroseconds(10);
  digitalWrite(ULTRASONIC_TRIG_PIN, LOW);

  const unsigned long durationUs = pulseIn(ULTRASONIC_ECHO_PIN, HIGH, ULTRASONIC_TIMEOUT_US);
  if (durationUs == 0) {
    return -1.0f;
  }

  return durationUs / 58.0f;
}

// Blocking avoidance mode:
// keep moving forward while the path is clear, otherwise stop and turn left.
// It exits when a stop request arrives, when the IR exit key is pressed,
// or when Servo_PROGRAM is set to the legacy break value 22.
void Avoid(void)
{
  while (1) {
    distance = measureDistanceCm();

    if (distance < AVOIDDIS && distance > 0) {
      robot.center();
      delay(100);
      robot.turnleft();
      robot.turnleft();
    } else if (distance >= AVOIDDIS) {
      robot.forward();
    }

    handleClient();

    if (isRobotStopRequested()) {
      break;
    }

    if (irrecv.decode(&results)) {
      DEBUG_PRINT_HEX64(results.value);
      irnum = (uint32_t)results.value;
      delay(150);
      irrecv.resume();
      if (irnum == 0xFF02FD) {
        break;
      }
    }

    if (Servo_PROGRAM == 22) {
      break;
    }
  }

  delay(1000);
}


// Legacy mapping kept here as a reference for the older unnamed IR remote.
/* static int decodeIrProgram(uint32_t code)
{
  switch (code)
  {
    case 0xFF18E7:
      return PROGRAM_FORWARD; // 上
    case 0xFF4AB5:
      return PROGRAM_BACKWARD; // 下
    case 0xFF10EF:
      return PROGRAM_LEFTSHIFT; // 左
    case 0xFF5AA5:
      return PROGRAM_RIGHTSHIFT; // 右
    case 0xFF38C7:
      return PROGRAM_ZERO; // OK
    case 0xFFB04F:
      return PROGRAM_CENTER; // #
    case 0xFF6897:
      return PROGRAM_SLEEP; //  *
    case 0xFFA25D:
      return PROGRAM_TURNLEFT; // 1
    case 0xFF629D:
      return PROGRAM_TURNRIGHT; // 2
    case 0xFFE21D:
      return PROGRAM_LIE; // 3
    case 0xFF22DD:
      return PROGRAM_HELLO; // 4
    case 0xFF02FD:
      return PROGRAM_FIGHTING; // 5
    case 0xFFC23D:
      return PROGRAM_PUSHUP; // 6
    case 0xFFE01F:
      return PROGRAM_DANCE1; // 7
    case 0xFFA857:
      return PROGRAM_DANCE2; // 8
    case 0xFF906F:
      return PROGRAM_DANCE3; // 9
    case 0xFF9867:
      return PROGRAM_AVOID; // 0
    default:
      return PROGRAM_NONE;
  }
} */
// Active IR mapping for the current remote controller.
// This converts raw IR values into the shared RobotProgramId enum.
static int decodeIrProgram(uint32_t code)
{
  switch (code)
  {
    case 0xFF629D:
      return PROGRAM_FORWARD;// ok
    case 0xFFA857:
      return PROGRAM_BACKWARD;// ok
    case 0xFF22DD:
      return PROGRAM_LEFTSHIFT;// ok
    case 0xFFC23D:
      return PROGRAM_RIGHTSHIFT;// ok
    case 0xFF02FD:
      return PROGRAM_ZERO;// ok
    case 0xFF52AD:
      return PROGRAM_CENTER;// ok
    case 0xFF42BD:
      return PROGRAM_SLEEP;// ok
    case 0xFF6897:
      return PROGRAM_TURNLEFT; // ok
    case 0xFF9867:
      return PROGRAM_TURNRIGHT; // ok
    case 0xFFB04F:
      return PROGRAM_LIE;// ok
    case 0xFF30CF:
      return PROGRAM_HELLO;// ok
    case 0xFF18E7:
      return PROGRAM_FIGHTING;// ok
    case 0xFF7A85:
      return PROGRAM_PUSHUP;// ok
    case 0xFF10EF:
      return PROGRAM_DANCE1;// ok
    case 0xFF38C7:
      return PROGRAM_DANCE2;// ok
    case 0xFF5AA5:
      return PROGRAM_DANCE3;// ok
    case 0xFF4AB5:
      return PROGRAM_AVOID;
    default:
      return PROGRAM_NONE;
  }
}

// Single dispatch point used by IR, Web UI and API commands.
// Every control source eventually resolves to one RobotProgramId and lands here.
static void runRobotProgram(int programId)
{
  setCurrentAction(programId, true);

  switch (programId)
  {
    case PROGRAM_STANDBY:
      robot.standby();
      break;
    case PROGRAM_FORWARD:
      robot.forward();
      break;
    case PROGRAM_BACKWARD:
      robot.backward();
      break;
    case PROGRAM_LEFTSHIFT:
      robot.leftshift();
      break;
    case PROGRAM_RIGHTSHIFT:
      robot.rightshift();
      break;
    case PROGRAM_TURNLEFT:
      robot.turnleft();
      break;
    case PROGRAM_TURNRIGHT:
      robot.turnright();
      break;
    case PROGRAM_LIE:
      robot.lie();
      break;
    case PROGRAM_HELLO:
      robot.hello();
      break;
    case PROGRAM_FIGHTING:
      robot.fighting();
      break;
    case PROGRAM_PUSHUP:
      robot.pushup();
      break;
    case PROGRAM_SLEEP:
      robot.sleep();
      break;
    case PROGRAM_DANCE1:
      robot.dance1();
      break;
    case PROGRAM_DANCE2:
      robot.dance2();
      break;
    case PROGRAM_DANCE3:
      robot.dance3();
      break;
    case PROGRAM_AVOID:
      Avoid();
      break;
    case PROGRAM_CENTER:
      robot.center();
      break;
    case PROGRAM_ZERO:
      robot.zero();
      break;
    default:
      break;
  }

  if (isRobotStopRequested()) {
    int stopTargetProgram = getRobotStopTargetProgram();
    clearRobotStopRequest();

    if (stopTargetProgram == PROGRAM_CENTER) {
      robot.center();
    } else if (stopTargetProgram == PROGRAM_ZERO) {
      robot.zero();
    } else {
      robot.standby();
    }
  }

  clearCurrentAction();
}
