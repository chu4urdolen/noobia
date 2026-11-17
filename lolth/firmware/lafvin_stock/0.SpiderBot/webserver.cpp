#include <EEPROM.h>
#include "webserver.h"

const char* password = "12345678";

int Servo_PROGRAM = 0;
int GPIO_ID = 100;
String ival;

ESP8266WebServer server(80);

const RobotDeviceInfo kRobotDeviceInfo = {
    "QuadBot-E",
    "1.0.0",
    "v1"
};

static String g_deviceName = "Robot";
static int g_currentActionId = PROGRAM_NONE;
static bool g_robotBusy = false;
static bool g_stopRequested = false;
static int g_stopTargetProgram = PROGRAM_STANDBY;
static bool g_debugUiEnabled = false;

static const RobotActionInfo kRobotActions[] = {
    {PROGRAM_STANDBY, "standby", "待机"},
    {PROGRAM_FORWARD, "forward", "前进"},
    {PROGRAM_BACKWARD, "backward", "后退"},
    {PROGRAM_LEFTSHIFT, "leftshift", "左移"},
    {PROGRAM_RIGHTSHIFT, "rightshift", "右移"},
    {PROGRAM_TURNLEFT, "turnleft", "左转"},
    {PROGRAM_TURNRIGHT, "turnright", "右转"},
    {PROGRAM_LIE, "lie", "躺下"},
    {PROGRAM_HELLO, "hello", "打招呼"},
    {PROGRAM_FIGHTING, "fighting", "战斗"},
    {PROGRAM_PUSHUP, "pushup", "俯卧撑"},
    {PROGRAM_SLEEP, "sleep", "睡眠"},
    {PROGRAM_DANCE1, "dance1", "舞步1"},
    {PROGRAM_DANCE2, "dance2", "舞步2"},
    {PROGRAM_DANCE3, "dance3", "舞步3"},
    {PROGRAM_AVOID, "avoid", "避障"},
    {PROGRAM_CENTER, "center", "中位"},
    {PROGRAM_ZERO, "zero", "归零"}
};

// ── Single-page UI stored in Flash (PROGMEM) ─────────────────────────────────
static const char INDEX_HTML[] PROGMEM = R"rawliteral(
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<title>QuadBot Debug</title>
<style>
*{box-sizing:border-box;margin:0;padding:0;-webkit-tap-highlight-color:transparent}
body{font-family:Arial,sans-serif;background:#0f172a;color:#e5e7eb;min-height:100vh;overflow:auto}
.page{min-height:100vh;display:flex;flex-direction:column}
.bar{position:sticky;top:0;z-index:10;display:flex;align-items:center;justify-content:space-between;gap:8px;padding:12px 14px;background:#111827;border-bottom:1px solid #243041}
.title{font-size:1rem;font-weight:700;color:#93c5fd}
.bar-actions{display:flex;gap:8px}
.tool-btn{border:none;border-radius:10px;padding:9px 12px;font-size:.88rem;font-weight:700;cursor:pointer;color:#f8fafc;background:#1f3b64;touch-action:manipulation}
.tool-btn.alt{background:#374151}
.main{flex:1;display:flex;flex-direction:column;gap:14px;padding:14px;padding-bottom:max(18px,env(safe-area-inset-bottom))}
.panel{background:#111827;border:1px solid #243041;border-radius:16px;padding:12px}
.panel-title{font-size:.84rem;font-weight:700;color:#93c5fd;margin-bottom:10px;text-transform:uppercase;letter-spacing:.04em}
.grid{display:grid;gap:10px}
.grid3{grid-template-columns:repeat(3,minmax(0,1fr))}
.btn{min-height:56px;width:100%;border:none;border-radius:12px;font-size:.92rem;font-weight:700;cursor:pointer;color:#1f2937;touch-action:manipulation}
.btn:active{opacity:.72}
.dir{background:#bfdbfe}
.turn{background:#bbf7d0}
.state{background:#fde68a}
.act{background:#fed7aa}
.sleep{background:#fecaca}
.dance{background:#ddd6fe}
.overlay{position:fixed;inset:0;z-index:30;display:flex;align-items:flex-end;justify-content:center;background:rgba(0,0,0,.72);opacity:0;pointer-events:none;transition:opacity .16s ease}
.overlay.show{opacity:1;pointer-events:auto}
.sheet{width:min(560px,100%);max-height:88vh;background:#111827;border-radius:18px 18px 0 0;border:1px solid #243041;border-bottom:none;display:flex;flex-direction:column}
.sheet-head{display:flex;align-items:center;justify-content:space-between;padding:14px 16px;border-bottom:1px solid #243041}
.sheet-title{font-size:.95rem;font-weight:700;color:#93c5fd}
.sheet-body{padding:12px;overflow:auto}
.close-btn{border:none;background:none;color:#9ca3af;font-size:1.4rem;line-height:1;cursor:pointer}
table{width:100%;border-collapse:collapse;font-size:.84rem}
th,td{padding:8px 6px;text-align:center;border-bottom:1px solid #1f2937}
th{color:#9ca3af;font-weight:600}
.group td{padding-top:12px;padding-bottom:6px;text-align:left;color:#93c5fd;font-size:.78rem;font-weight:700;border-bottom:none}
input[type=number]{width:68px;padding:6px 4px;border-radius:8px;border:1px solid #334155;background:#0f172a;color:#f8fafc;text-align:center}
.set-btn{border:none;border-radius:8px;background:#14532d;color:#dcfce7;padding:7px 10px;font-size:.8rem;font-weight:700;cursor:pointer}
.wide-btn{width:100%;margin-top:12px;padding:11px;border:none;border-radius:10px;background:#1d4ed8;color:#eff6ff;font-size:.9rem;font-weight:700;cursor:pointer}
.hint{font-size:.78rem;color:#94a3b8;margin-top:8px}
</style>
</head>
<body>
<div class="page">
  <div class="bar">
    <div class="title">QuadBot Debug</div>
    <div class="bar-actions">
      <button class="tool-btn" onclick="openCal()">Calibration</button>
      <button class="tool-btn alt" onclick="hideDebug()">Hide</button>
    </div>
  </div>

  <div class="main">
    <div class="panel">
      <div class="panel-title">Directional Control</div>
      <div class="grid grid3">
        <button class="btn turn" onclick="pm(6)">Turn Left</button>
        <button class="btn dir" onclick="pm(2)">Forward</button>
        <button class="btn turn" onclick="pm(7)">Turn Right</button>
        <button class="btn dir" onclick="pm(4)">Left Shift</button>
        <button class="btn dir" onclick="pm(3)">Backward</button>
        <button class="btn dir" onclick="pm(5)">Right Shift</button>
      </div>
    </div>

    <div class="panel">
      <div class="panel-title">Actions</div>
      <div class="grid grid3">
        <button class="btn state" onclick="pm(1)">Standby</button>
        <button class="btn act" onclick="pm(9)">Hello</button>
        <button class="btn act" onclick="pm(11)">Push Up</button>
        <button class="btn act" onclick="pm(8)">Lie</button>
        <button class="btn act" onclick="pm(10)">Fighting</button>
        <button class="btn sleep" onclick="pm(12)">Sleep</button>
        <button class="btn dance" onclick="pm(13)">Dance 1</button>
        <button class="btn dance" onclick="pm(14)">Dance 2</button>
        <button class="btn dance" onclick="pm(15)">Dance 3</button>
      </div>
    </div>
  </div>
</div>

<div id="overlay" class="overlay" onclick="bgClose(event)">
  <div class="sheet">
    <div class="sheet-head">
      <div class="sheet-title">Calibration</div>
      <button class="close-btn" onclick="closeCal()">&times;</button>
    </div>
    <div class="sheet-body">
      <table>
        <thead>
          <tr><th>Pin</th><th>Part</th><th>Axis</th><th>Offset</th><th></th></tr>
        </thead>
        <tbody>
          <tr class="group"><td colspan="5">Right Front</td></tr>
          <tr><td>D14</td><td>Foot</td><td>Swing</td><td><input type="number" id="s0" min="-30" max="30" value="0"></td><td><button class="set-btn" onclick="save(0)">SET</button></td></tr>
          <tr><td>D12</td><td>Leg</td><td>Lift</td><td><input type="number" id="s1" min="-30" max="30" value="0"></td><td><button class="set-btn" onclick="save(1)">SET</button></td></tr>

          <tr class="group"><td colspan="5">Right Rear</td></tr>
          <tr><td>D13</td><td>Leg</td><td>Lift</td><td><input type="number" id="s2" min="-30" max="30" value="0"></td><td><button class="set-btn" onclick="save(2)">SET</button></td></tr>
          <tr><td>D15</td><td>Foot</td><td>Swing</td><td><input type="number" id="s3" min="-30" max="30" value="0"></td><td><button class="set-btn" onclick="save(3)">SET</button></td></tr>

          <tr class="group"><td colspan="5">Left Front</td></tr>
          <tr><td>D16</td><td>Foot</td><td>Swing</td><td><input type="number" id="s4" min="-30" max="30" value="0"></td><td><button class="set-btn" onclick="save(4)">SET</button></td></tr>
          <tr><td>D5</td><td>Leg</td><td>Lift</td><td><input type="number" id="s5" min="-30" max="30" value="0"></td><td><button class="set-btn" onclick="save(5)">SET</button></td></tr>

          <tr class="group"><td colspan="5">Left Rear</td></tr>
          <tr><td>D4</td><td>Leg</td><td>Lift</td><td><input type="number" id="s6" min="-30" max="30" value="0"></td><td><button class="set-btn" onclick="save(6)">SET</button></td></tr>
          <tr><td>D2</td><td>Foot</td><td>Swing</td><td><input type="number" id="s7" min="-30" max="30" value="0"></td><td><button class="set-btn" onclick="save(7)">SET</button></td></tr>
        </tbody>
      </table>
      <button class="wide-btn" onclick="pm(100)">Go To Zero Pose</button>
      <div class="hint">Offset range: -30 to +30 is recommended for quick calibration.</div>
    </div>
  </div>
</div>

<script>
function pm(v){ fetch('/controller?pm=' + v, { cache: 'no-store' }); }
function closeCal(){ document.getElementById('overlay').classList.remove('show'); }
function bgClose(e){ if(e.target.id === 'overlay') closeCal(); }
function save(id){
  var value = document.getElementById('s' + id).value;
  fetch('/save?key=' + id + '&value=' + value, { cache: 'no-store' });
}
function hideDebug(){ window.location = '/debug/close'; }
function openCal(){
  fetch('/setting1', { cache: 'no-store' })
    .then(function(r){ return r.json(); })
    .then(function(values){
      for (var i = 0; i < 8; i++) {
        document.getElementById('s' + i).value = values[i] || 0;
      }
      document.getElementById('overlay').classList.add('show');
    });
}
</script>
</body>
</html>
)rawliteral";

static const char DEBUG_LOCKED_HTML[] PROGMEM = R"rawliteral(
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>QuadBot Debug Locked</title>
<style>
body{margin:0;font-family:Arial,sans-serif;background:#0f172a;color:#e5e7eb;min-height:100vh;display:flex;align-items:center;justify-content:center;padding:20px}
.card{width:min(420px,100%);background:#111827;border:1px solid #243041;border-radius:16px;padding:22px}
h1{margin:0 0 12px;font-size:1.15rem;color:#93c5fd}
p{margin:0 0 10px;line-height:1.5;color:#cbd5e1}
code{background:#0b1220;padding:2px 6px;border-radius:6px}
</style>
</head>
<body>
  <div class="card">
    <h1>Debug UI Disabled</h1>
    <p>The legacy debug web page is currently hidden.</p>
    <p>Open <code>/debug/open</code> when you want to use it, or keep using the <code>/api/v1</code> endpoints.</p>
  </div>
</body>
</html>
)rawliteral";

// ── EEPROM helpers ────────────────────────────────────────────────────────────

void writeKeyValue(int8_t key, int8_t value)
{
    EEPROM.write(key, value);
    EEPROM.commit();
}

// BUG FIX: was always returning 0 instead of the stored value
int8_t readKeyValue(int8_t key)
{
    return (int8_t)EEPROM.read(key);
}

const RobotActionInfo* getRobotActions(size_t& count)
{
    count = sizeof(kRobotActions) / sizeof(kRobotActions[0]);
    return kRobotActions;
}

const RobotActionInfo* findRobotActionById(int actionId)
{
    size_t count = 0;
    const RobotActionInfo* actions = getRobotActions(count);

    for (size_t i = 0; i < count; i++) {
        if (actions[i].id == actionId) {
            return &actions[i];
        }
    }

    return nullptr;
}

const RobotActionInfo* findRobotActionByName(const String& actionName)
{
    size_t count = 0;
    const RobotActionInfo* actions = getRobotActions(count);

    for (size_t i = 0; i < count; i++) {
        if (actionName.equalsIgnoreCase(actions[i].name)) {
            return &actions[i];
        }
    }

    return nullptr;
}

const char* getActionName(int actionId)
{
    const RobotActionInfo* action = findRobotActionById(actionId);
    return action != nullptr ? action->name : "idle";
}

const char* getActionLabel(int actionId)
{
    const RobotActionInfo* action = findRobotActionById(actionId);
    return action != nullptr ? action->label : "空闲";
}

String getDeviceName()
{
    return g_deviceName;
}

void setCurrentAction(int actionId, bool busy)
{
    g_currentActionId = actionId;
    g_robotBusy = busy;
}

void clearCurrentAction()
{
    g_currentActionId = PROGRAM_NONE;
    g_robotBusy = false;
}

int getCurrentActionId()
{
    return g_currentActionId;
}

const char* getCurrentActionName()
{
    return getActionName(g_currentActionId);
}

bool isRobotBusy()
{
    return g_robotBusy;
}

void requestRobotStop(int targetProgram)
{
    g_stopRequested = true;
    g_stopTargetProgram = targetProgram;
}

void clearRobotStopRequest()
{
    g_stopRequested = false;
    g_stopTargetProgram = PROGRAM_STANDBY;
}

bool isRobotStopRequested()
{
    return g_stopRequested;
}

int getRobotStopTargetProgram()
{
    return g_stopTargetProgram;
}

static bool ensureDebugUiEnabled()
{
    if (g_debugUiEnabled) {
        return true;
    }

    server.send(403, "text/plain", "DEBUG_UI_DISABLED");
    return false;
}

static void sendJsonResponse(int statusCode, bool ok, int code, const char* message, const String& data)
{
    String payload = "{\"ok\":";
    payload += ok ? "true" : "false";
    payload += ",\"code\":";
    payload += String(code);
    payload += ",\"message\":\"";
    payload += message;
    payload += "\"";
    if (data != "") {
        payload += ",\"data\":";
        payload += data;
    }
    payload += "}";

    server.send(statusCode, "application/json", payload);
}

static void sendJsonError(int statusCode, int code, const char* message)
{
    sendJsonResponse(statusCode, false, code, message, "");
}

static String buildCalibrationJsonArray()
{
    String offsets = "[";
    for (int i = 0; i < ALLSERVOS; i++) {
        if (i > 0) {
            offsets += ",";
        }
        offsets += String((int8_t)EEPROM.read(i));
    }
    offsets += "]";
    return offsets;
}

static String buildActionsJsonArray()
{
    String actions = "[";
    size_t count = 0;
    const RobotActionInfo* actionList = getRobotActions(count);

    for (size_t i = 0; i < count; i++) {
        if (i > 0) {
            actions += ",";
        }

        actions += "{\"id\":";
        actions += String(actionList[i].id);
        actions += ",\"name\":\"";
        actions += actionList[i].name;
        actions += "\",\"label\":\"";
        actions += actionList[i].label;
        actions += "\"}";
    }

    actions += "]";
    return actions;
}

static bool extractJsonInt(const String& body, const char* key, int& value)
{
    String token = "\"";
    token += key;
    token += "\"";

    int keyPos = body.indexOf(token);
    if (keyPos < 0) {
        return false;
    }

    int colonPos = body.indexOf(':', keyPos + token.length());
    if (colonPos < 0) {
        return false;
    }

    int start = colonPos + 1;
    while (start < body.length() && isspace(body[start])) {
        start++;
    }

    int end = start;
    if (end < body.length() && body[end] == '-') {
        end++;
    }

    while (end < body.length() && isdigit(body[end])) {
        end++;
    }

    if (start == end) {
        return false;
    }

    value = body.substring(start, end).toInt();
    return true;
}

static bool extractJsonString(const String& body, const char* key, String& value)
{
    String token = "\"";
    token += key;
    token += "\"";

    int keyPos = body.indexOf(token);
    if (keyPos < 0) {
        return false;
    }

    int colonPos = body.indexOf(':', keyPos + token.length());
    if (colonPos < 0) {
        return false;
    }

    int firstQuote = body.indexOf('"', colonPos + 1);
    if (firstQuote < 0) {
        return false;
    }

    int secondQuote = body.indexOf('"', firstQuote + 1);
    if (secondQuote < 0) {
        return false;
    }

    value = body.substring(firstQuote + 1, secondQuote);
    return true;
}

static bool resolveActionRequest(int& actionId)
{
    actionId = PROGRAM_NONE;
    String body = server.arg("plain");
    int parsedId = PROGRAM_NONE;
    String actionName;

    if (body != "") {
        if (extractJsonInt(body, "id", parsedId)) {
            actionId = parsedId;
        } else if (extractJsonString(body, "action", actionName)) {
            const RobotActionInfo* action = findRobotActionByName(actionName);
            if (action != nullptr) {
                actionId = action->id;
            }
        }
    }

    if (actionId == PROGRAM_NONE && server.hasArg("id")) {
        actionId = server.arg("id").toInt();
    }

    if (actionId == PROGRAM_NONE && server.hasArg("action")) {
        const RobotActionInfo* action = findRobotActionByName(server.arg("action"));
        if (action != nullptr) {
            actionId = action->id;
        }
    }

    return findRobotActionById(actionId) != nullptr;
}

static bool parseCalibrationOffsets(int8_t offsets[ALLSERVOS])
{
    String body = server.arg("plain");
    if (body == "") {
        return false;
    }

    int keyPos = body.indexOf("\"offsets\"");
    if (keyPos < 0) {
        return false;
    }

    int startBracket = body.indexOf('[', keyPos);
    int endBracket = body.indexOf(']', startBracket);
    if (startBracket < 0 || endBracket < 0 || endBracket <= startBracket) {
        return false;
    }

    String values = body.substring(startBracket + 1, endBracket);
    values.trim();

    for (int i = 0; i < ALLSERVOS; i++) {
        int commaPos = values.indexOf(',');
        String item;

        if (commaPos >= 0) {
            item = values.substring(0, commaPos);
            values = values.substring(commaPos + 1);
        } else {
            item = values;
            values = "";
        }

        item.trim();
        if (item == "") {
            return false;
        }

        int value = item.toInt();
        if (value < -124 || value > 124) {
            return false;
        }

        offsets[i] = (int8_t)value;
    }

    return values.indexOf(',') < 0 && values == "";
}

static bool parseServoCommand(int& servoId, int& servoValue)
{
    servoId = -1;
    servoValue = 0;

    String body = server.arg("plain");
    if (body != "") {
        extractJsonInt(body, "servo", servoId);
        extractJsonInt(body, "value", servoValue);
    }

    if (servoId < 0 && server.hasArg("servo")) {
        servoId = server.arg("servo").toInt();
    }

    if (!server.hasArg("value") && body == "") {
        return false;
    }

    if (body == "" && server.hasArg("value")) {
        servoValue = server.arg("value").toInt();
    }

    if (servoId < 0 || servoId >= ALLSERVOS) {
        return false;
    }

    if (servoValue < PWMRES_Min || servoValue > PWMRES_Max) {
        return false;
    }

    return true;
}

static bool resolveStopMode(int& targetProgram)
{
    targetProgram = PROGRAM_STANDBY;
    String mode;
    String body = server.arg("plain");

    if (body != "") {
        extractJsonString(body, "mode", mode);
    }

    if (mode == "" && server.hasArg("mode")) {
        mode = server.arg("mode");
    }

    if (mode == "" || mode.equalsIgnoreCase("standby")) {
        targetProgram = PROGRAM_STANDBY;
        return true;
    }

    if (mode.equalsIgnoreCase("center")) {
        targetProgram = PROGRAM_CENTER;
        return true;
    }

    if (mode.equalsIgnoreCase("zero")) {
        targetProgram = PROGRAM_ZERO;
        return true;
    }

    return false;
}

// ── WiFi / EEPROM init ────────────────────────────────────────────────────────

void webinit()
{
    uint8_t mac[WL_MAC_ADDR_LENGTH];
    WiFi.softAPmacAddress(mac);
    String macID = String(mac[WL_MAC_ADDR_LENGTH - 2], HEX) + String(mac[WL_MAC_ADDR_LENGTH - 1], HEX);
    macID.toUpperCase();

    String AP_NameString = "Robot - " + macID;
    g_deviceName = AP_NameString;
    char AP_NameChar[AP_NameString.length() + 1];
    memset(AP_NameChar, 0, AP_NameString.length() + 1);
    for (int i = 0; i < (int)AP_NameString.length(); i++)
        AP_NameChar[i] = AP_NameString.charAt(i);

    WiFi.softAP(AP_NameChar, password);

    EEPROM.begin(512);
    delay(10);
}

// ── HTTP handlers ─────────────────────────────────────────────────────────────

void handleClient()
{
    server.handleClient();
}

// Main page: serve PROGMEM HTML directly (no String allocation)
void handleIndex()
{
    if (!g_debugUiEnabled) {
        server.send_P(200, "text/html", DEBUG_LOCKED_HTML);
        return;
    }

    server.send_P(200, "text/html", INDEX_HTML);
}

// Returns calibration offsets as JSON array [s0, s1, ..., s7]
// Index i = servo i = EEPROM key i
void handleSetting1()
{
    if (!ensureDebugUiEnabled()) {
        return;
    }

    String content = "[";
    for (int i = 0; i < 8; i++) {
        if (i > 0) content += ",";
        content += String((int8_t)EEPROM.read(i));
    }
    content += "]";
    server.send(200, "application/json", content);
}

static void handleApiInfo()
{
    String data = "{";
    data += "\"device_name\":\"" + getDeviceName() + "\",";
    data += "\"model\":\"";
    data += kRobotDeviceInfo.model;
    data += "\",\"firmware_version\":\"";
    data += kRobotDeviceInfo.firmwareVersion;
    data += "\",\"protocol_version\":\"";
    data += kRobotDeviceInfo.protocolVersion;
    data += "\",\"wifi_mode\":\"AP\",";
    data += "\"servo_count\":";
    data += String(ALLSERVOS);
    data += ",\"actions\":";
    data += buildActionsJsonArray();
    data += "}";

    sendJsonResponse(200, true, 0, "OK", data);
}

static void handleApiState()
{
    int requestedActionId = Servo_PROGRAM;
    bool avoidEnabled = (getCurrentActionId() == PROGRAM_AVOID) || (requestedActionId == PROGRAM_AVOID);
    String data = "{";
    data += "\"device_name\":\"" + getDeviceName() + "\",";
    data += "\"current_action_id\":";
    data += String(getCurrentActionId());
    data += ",\"current_action\":\"";
    data += getCurrentActionName();
    data += "\",\"current_action_label\":\"";
    data += getActionLabel(getCurrentActionId());
    data += "\",\"requested_action_id\":";
    data += String(requestedActionId);
    data += ",\"requested_action\":\"";
    data += getActionName(requestedActionId);
    data += "\",\"busy\":";
    data += isRobotBusy() ? "true" : "false";
    data += ",\"avoid_enabled\":";
    data += avoidEnabled ? "true" : "false";
    data += ",\"stop_requested\":";
    data += isRobotStopRequested() ? "true" : "false";
    data += ",\"stop_target\":\"";
    data += getActionName(getRobotStopTargetProgram());
    data += "\",\"debug_ui_enabled\":";
    data += g_debugUiEnabled ? "true" : "false";
    data += ",\"wifi_mode\":\"AP\"}";

    sendJsonResponse(200, true, 0, "OK", data);
}

static void handleApiAction()
{
    int actionId = PROGRAM_NONE;
    if (!resolveActionRequest(actionId)) {
        sendJsonError(400, 4001, "invalid action");
        return;
    }

    Servo_PROGRAM = actionId;
    setCurrentAction(actionId, false);

    String data = "{";
    data += "\"id\":";
    data += String(actionId);
    data += ",\"action\":\"";
    data += getActionName(actionId);
    data += "\",\"label\":\"";
    data += getActionLabel(actionId);
    data += "\"}";

    sendJsonResponse(200, true, 0, "accepted", data);
}

static void handleApiCalibrationGet()
{
    String data = "{\"offsets\":";
    data += buildCalibrationJsonArray();
    data += "}";

    sendJsonResponse(200, true, 0, "OK", data);
}

static void handleApiCalibrationPost()
{
    int8_t offsets[ALLSERVOS];
    if (!parseCalibrationOffsets(offsets)) {
        sendJsonError(400, 4002, "invalid calibration payload");
        return;
    }

    for (int i = 0; i < ALLSERVOS; i++) {
        writeKeyValue(i, offsets[i]);
    }

    String data = "{\"offsets\":";
    data += buildCalibrationJsonArray();
    data += "}";

    sendJsonResponse(200, true, 0, "saved", data);
}

static void handleApiServo()
{
    int servoId = -1;
    int servoValue = 0;
    if (!parseServoCommand(servoId, servoValue)) {
        sendJsonError(400, 4003, "invalid servo payload");
        return;
    }

    GPIO_ID = servoId;
    ival = String(servoValue);

    String data = "{";
    data += "\"servo\":";
    data += String(servoId);
    data += ",\"value\":";
    data += String(servoValue);
    data += "}";

    sendJsonResponse(200, true, 0, "accepted", data);
}

static void handleApiStop()
{
    int targetProgram = PROGRAM_STANDBY;
    if (!resolveStopMode(targetProgram)) {
        sendJsonError(400, 4004, "invalid stop mode");
        return;
    }

    Servo_PROGRAM = PROGRAM_NONE;
    requestRobotStop(targetProgram);

    String data = "{";
    data += "\"mode\":\"";
    data += getActionName(targetProgram);
    data += "\",\"target_program\":";
    data += String(targetProgram);
    data += "}";

    sendJsonResponse(200, true, 0, "stop requested", data);
}

static void handleDebugUiOpen()
{
    g_debugUiEnabled = true;
    server.sendHeader("Location", "/", true);
    server.send(302, "text/plain", "");
}

static void handleDebugUiClose()
{
    g_debugUiEnabled = false;
    server.sendHeader("Location", "/", true);
    server.send(302, "text/plain", "");
}

// Save calibration offset: key=servo index (0-7), value=offset (-124~124)
// key=100 resets all offsets to 0
void handleSave()
{
    if (!ensureDebugUiEnabled()) {
        return;
    }

    String key   = server.arg("key");
    String value = server.arg("value");

    int8_t keyInt   = (int8_t)key.toInt();
    int8_t valueInt = (int8_t)value.toInt();

    delay(50);

    if (keyInt == 100) {
        for (int i = 0; i < 8; i++) writeKeyValue(i, 0);
    } else if (valueInt >= -124 && valueInt <= 124) {
        writeKeyValue(keyInt, valueInt);
    }

    delay(10);
    server.send(200, "text/plain", "OK");
}

// Robot motion control: pm=program number, or servo=index&value=angle
void handleController()
{
    if (!ensureDebugUiEnabled()) {
        return;
    }

    String pm    = server.arg("pm");
    String servo = server.arg("servo");

    if (pm != "") {
        int requestedProgram = pm.toInt();
        if (findRobotActionById(requestedProgram) == nullptr) {
            server.send(400, "text/plain", "INVALID_ACTION");
            return;
        }
        Servo_PROGRAM = requestedProgram;
    }

    if (servo != "") {
        int requestedServo = servo.toInt();
        String value = server.arg("value");

        if (requestedServo < 0 || requestedServo >= ALLSERVOS || value == "") {
            server.send(400, "text/plain", "INVALID_SERVO");
            return;
        }

        GPIO_ID = requestedServo;
        ival    = value;
    }

    server.send(200, "text/plain", "OK");
}

// ── Route registration ────────────────────────────────────────────────────────

void enableWebServer()
{
    server.on("/",           HTTP_GET, handleIndex);
    server.on("/debug/open", HTTP_GET, handleDebugUiOpen);
    server.on("/debug/close", HTTP_GET, handleDebugUiClose);
    server.on("/controller", HTTP_GET, handleController);
    server.on("/save",       HTTP_GET, handleSave);
    server.on("/setting1",   HTTP_GET, handleSetting1);
    server.on("/api/v1/info",        HTTP_GET, handleApiInfo);
    server.on("/api/v1/state",       HTTP_GET, handleApiState);
    server.on("/api/v1/action",      HTTP_POST, handleApiAction);
    server.on("/api/v1/calibration", HTTP_GET, handleApiCalibrationGet);
    server.on("/api/v1/calibration", HTTP_POST, handleApiCalibrationPost);
    server.on("/api/v1/servo",       HTTP_POST, handleApiServo);
    server.on("/api/v1/stop",        HTTP_POST, handleApiStop);

    server.begin();
}
