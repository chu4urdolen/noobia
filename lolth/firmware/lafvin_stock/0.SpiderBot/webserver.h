#ifndef webserver_h
#define webserver_h
#include <ESP8266WiFi.h>
#include <ESP8266WebServer.h>
#include "spiderbot_motion.h"

enum RobotProgramId {
    PROGRAM_NONE = 0,
    PROGRAM_STANDBY = 1,
    PROGRAM_FORWARD = 2,
    PROGRAM_BACKWARD = 3,
    PROGRAM_LEFTSHIFT = 4,
    PROGRAM_RIGHTSHIFT = 5,
    PROGRAM_TURNLEFT = 6,
    PROGRAM_TURNRIGHT = 7,
    PROGRAM_LIE = 8,
    PROGRAM_HELLO = 9,
    PROGRAM_FIGHTING = 10,
    PROGRAM_PUSHUP = 11,
    PROGRAM_SLEEP = 12,
    PROGRAM_DANCE1 = 13,
    PROGRAM_DANCE2 = 14,
    PROGRAM_DANCE3 = 15,
    PROGRAM_AVOID = 21,
    PROGRAM_CENTER = 99,
    PROGRAM_ZERO = 100
};

struct RobotActionInfo {
    int id;
    const char* name;
    const char* label;
};

struct RobotDeviceInfo {
    const char* model;
    const char* firmwareVersion;
    const char* protocolVersion;
};

extern int Servo_PROGRAM;
extern int GPIO_ID;
extern String ival;
extern const RobotDeviceInfo kRobotDeviceInfo;

void webinit();
void enableWebServer();
void handleClient();

void writeKeyValue(int8_t key, int8_t value);
int8_t readKeyValue(int8_t key);
const RobotActionInfo* getRobotActions(size_t& count);
const RobotActionInfo* findRobotActionById(int actionId);
const RobotActionInfo* findRobotActionByName(const String& actionName);
const char* getActionName(int actionId);
const char* getActionLabel(int actionId);
String getDeviceName();
void setCurrentAction(int actionId, bool busy);
void clearCurrentAction();
int getCurrentActionId();
const char* getCurrentActionName();
bool isRobotBusy();
void requestRobotStop(int targetProgram);
void clearRobotStopRequest();
bool isRobotStopRequested();
int getRobotStopTargetProgram();

#endif
