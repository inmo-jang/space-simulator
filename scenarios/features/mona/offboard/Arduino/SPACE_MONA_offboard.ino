#include <WiFi.h>
#include <WiFiUdp.h>
#include "Mona_ESP_lib.h"
#include <math.h>
#include <strings.h>
#include <Arduino.h>
#include <WiFiClient.h>
#include <WiFiServer.h>
#include <esp_now.h>
#include <esp_wifi.h>
#include <ArduinoJson.h>
#include <vector>
#include <map>
#include <algorithm>
#include <freertos/FreeRTOS.h>
#include <freertos/semphr.h>
#include <freertos/task.h>

// ====== USER CONFIG ======
const char* SSID        = "Your SSID";
const char* PASSWORD    = "Your Password";
const String SELF_ID    = "11";           // Change this for each robot (0-11)
const uint16_t TCP_PORT = 8080;
const int UDP_PORT      = 8080;  // UDP: PC → ESP32 이동 명령 (TCP와 프로토콜 달라 포트 공유 가능)

// JSON buffer size
const size_t JSON_SIZE = 2048;

WiFiServer tcpServer(TCP_PORT);
std::vector<WiFiClient> clients;

DynamicJsonDocument selfMessageDoc(JSON_SIZE);
std::map<String, DynamicJsonDocument*> receivedJSON_MAP;
std::map<String, unsigned long> CommRecvTime_MAP;
SemaphoreHandle_t mapLock;

unsigned long lastBroadcast_ms       = 0;
unsigned long lastTcpSend_ms         = 0;
unsigned long lastMemoryCleanup_ms   = 0;
unsigned long lastStatsPrint_ms      = 0;

unsigned long p2p_loopCount          = 0;
unsigned long p2p_maxLoopTime_us     = 0;
unsigned long p2p_minLoopTime_us     = 999999;
unsigned long p2p_totalLoopTime_us   = 0;

size_t currentMemoryUsage_bytes      = 0;
size_t peakMemoryUsage_bytes         = 0;

static char    g_jsonBuf[JSON_SIZE];

// ============================================================
// ====== Puppet Config (Core 0 - puppetTask) =================
// ====== UDP 이동 명령 수신, 모터/IR/엔코더 제어 =============
// ============================================================

WiFiUDP udp;
char packetBuffer[255];

// --- 상태 머신 ---
enum RobotState {
  STATE_IDLE,
  STATE_TURNING,
  STATE_MOVING,
  STATE_AVOID,
  STATE_ESCAPING,
  STATE_EMERGENCY
};
volatile RobotState state = STATE_IDLE;

const uint32_t BROADCAST_MIN_INTERVAL_MS  = 100;
const uint32_t BROADCAST_MAX_INTERVAL_MS  = 100;
const uint32_t PEER_LINK_DROP_MS          = 900;
const uint32_t WIFI_RECONNECT_INTERVAL_MS = 300;
const uint32_t WIFI_TIMEOUT_MS            = 10000;
const uint32_t WIFI_RETRY_DELAY_MS        = 200;
const uint32_t TCP_MONITORING_INTERVAL_MS = 100;
const uint32_t MEMORY_CLEANUP_INTERVAL_MS = 5000;
const uint32_t STATS_PRINT_INTERVAL_MS    = 5000;
const uint32_t SERIAL_STABILIZE_DELAY_MS  = 1000;

static const int ESPNOW_MAX_PAYLOAD       = 1470;

uint32_t currentBroadcastInterval_ms      = BROADCAST_MIN_INTERVAL_MS;
const uint32_t Peer_LinkDrop_MS           = 900;
static uint8_t g_pkt[ESPNOW_MAX_PAYLOAD];


// 펄스/제어 상수
static const float PULSES_PER_MM     = 18.0f;
static const float PULSES_PER_DEGREE = 12.8f;
static const int   FWD_SPD           = 100;
static const int   TURN_SPD          = 100;

// 900펄스마다 새로운 명령을 받음
static const long  UPDATE_THRESHOLD_PULSES = 900;   
static const float MIN_DIST_MM             = 40.0f; 

// IR/회피
static const int TH        = 80;
static const int TH_OUTER  = 100;
static const int DELTA     = 15;

// 핀 번호 정의
static const int PIN_ENCODER_LEFT  = 35;
static const int PIN_ENCODER_RIGHT = 39;

// 제어 관련 임계값
static const float ROTATION_DEADBAND_DEG = 5.0f;    // 미세 회전 무시 각도
static const int   MIN_MOTOR_PWM         = 60;      // 모터 구동 최소 출력

// PI 제어 게인 (주행 보정)
static const float K_P            = 0.5f;
static const float K_I            = 0.002f;
static const float INTEGRAL_LIMIT = 500.0f;
static const int   ERROR_DEADBAND = 5;

// 비상 동작 속도
static const int EMERGENCY_SPIN_SPD = 200;
static const uint16_t ESCAPING_MS   = 1000;
unsigned long escaping_until_ms     = 0;

static const unsigned long EMERGENCY_SPIN_MS     = 1200;
static const unsigned long BACK_MS               = 120;
static const unsigned long OSCILLATION_WINDOW_MS = 1200;
static const int   OSCILLATION_COUNT_THRESHOLD   = 4;

int last_turn_direction = 0;         
int turn_change_count   = 0;
unsigned long oscillation_timer_start = 0;

unsigned long emergency_back_until = 0;
unsigned long emergency_spin_until = 0;

volatile long left_encoder_count  = 0;
volatile long right_encoder_count = 0;

void IRAM_ATTR isr_left_encoder()  { left_encoder_count++; }
void IRAM_ATTR isr_right_encoder() { right_encoder_count++; }

static long  start_left_count   = 0;
static long  start_right_count  = 0;
static long  target_turn_pulses = 0;
static long  target_move_pulses = 0;
static float integral_error     = 0.0f;

// --- 제어 주기 ---
static const unsigned long CONTROL_INTERVAL_MS    = 5;    // 5ms 이동 제어
static const unsigned long LED_UPDATE_INTERVAL_MS = 100;  // 100ms LED 갱신

// Puppet 태스크 핸들
TaskHandle_t puppetTaskHandle = NULL;

// ====== P2P 함수들 ==========================================

bool update_Broadcast_recv_JSON_MAP(const String& senderID, const char* jsonBuf, size_t jsonLen) {
  DynamicJsonDocument* doc = new DynamicJsonDocument(JSON_SIZE);
  if (deserializeJson(*doc, jsonBuf, jsonLen)) { delete doc; return false; }

  // 콜백(인터럽트 컨텍스트)에서 오래 블록하지 않도록 즉시 실패 허용
  if (xSemaphoreTake(mapLock, 0) != pdTRUE) { delete doc; return false; }

  auto it = receivedJSON_MAP.find(senderID);
  if (it != receivedJSON_MAP.end()) {
    delete it->second;
    it->second = doc;
  } else {
    receivedJSON_MAP[senderID] = doc;
    currentMemoryUsage_bytes += JSON_SIZE;
  }
  CommRecvTime_MAP[senderID] = millis();
  xSemaphoreGive(mapLock);
  return true;
}

void onEspNowRecv(const esp_now_recv_info_t *recv_info, const uint8_t *incoming, int len) {
  (void)recv_info;
  if (len <= 1) return;

  uint8_t idLen = incoming[0];
  if (len < 1 + idLen) return;

  String senderID = String((const char*)(&incoming[1]), idLen);
  if (senderID == SELF_ID) return;

  int jsonLen = len - (1 + idLen);
  if (jsonLen <= 0) return;
  update_Broadcast_recv_JSON_MAP(senderID, (const char*)(&incoming[1 + idLen]), (size_t)jsonLen);
}

void ensureBroadcastPeer() {
  uint8_t bcast[6] = {0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF};
  if (esp_now_is_peer_exist(bcast)) return;

  esp_now_peer_info_t p = {};
  memcpy(p.peer_addr, bcast, 6);
  p.ifidx   = WIFI_IF_STA;
  p.channel = WiFi.channel();
  p.encrypt = false;

  esp_now_add_peer(&p);
}

void broadcastSelfMessageIfDue() {
  unsigned long now = millis();
  if ((unsigned long)(now - lastBroadcast_ms) < currentBroadcastInterval_ms) return;
  lastBroadcast_ms += currentBroadcastInterval_ms;
  currentBroadcastInterval_ms = random(BROADCAST_MIN_INTERVAL_MS, BROADCAST_MAX_INTERVAL_MS);

  if (selfMessageDoc.isNull()) return;
  ensureBroadcastPeer();

  size_t jsonLen = serializeJson(selfMessageDoc, g_jsonBuf, sizeof(g_jsonBuf));
  if (jsonLen == 0) return;

  const uint8_t idLen = (uint8_t)SELF_ID.length();
  const size_t total  = 1 + (size_t)idLen + jsonLen;
  if ((int)total > ESPNOW_MAX_PAYLOAD) return;

  g_pkt[0] = idLen;
  memcpy(&g_pkt[1], SELF_ID.c_str(), idLen);
  memcpy(&g_pkt[1 + idLen], g_jsonBuf, jsonLen);

  uint8_t bcast[6] = {0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF};
  esp_now_send(bcast, g_pkt, total);
}

void sendTcpMonitoringIfDue() {
  unsigned long now = millis();
  if ((unsigned long)(now - lastTcpSend_ms) < TCP_MONITORING_INTERVAL_MS) return;
  lastTcpSend_ms += TCP_MONITORING_INTERVAL_MS;

  size_t activeRobots = receivedJSON_MAP.size();
  size_t monitorSize  = JSON_SIZE * (activeRobots + 1);
  DynamicJsonDocument monitor(monitorSize);
  monitor["agent_id"] = SELF_ID;
  JsonObject rx = monitor.createNestedObject("received_messages");

  xSemaphoreTake(mapLock, portMAX_DELAY);
  for (auto const& kv : receivedJSON_MAP) {
    if ((unsigned long)(now - CommRecvTime_MAP[kv.first]) <= Peer_LinkDrop_MS)
      rx[kv.first] = kv.second->as<JsonObject>();
  }
  xSemaphoreGive(mapLock);

  String out;
  serializeJson(monitor, out);
  out += "\n";
  for (auto& c : clients)
    if (c && c.connected()) c.print(out);

  size_t tempMem = currentMemoryUsage_bytes + monitorSize;
  if (tempMem > peakMemoryUsage_bytes) peakMemoryUsage_bytes = tempMem;
}

void cleanupStaleEntries() {
  unsigned long now = millis();
  if ((unsigned long)(now - lastMemoryCleanup_ms) < MEMORY_CLEANUP_INTERVAL_MS) return;
  lastMemoryCleanup_ms += MEMORY_CLEANUP_INTERVAL_MS;

  xSemaphoreTake(mapLock, portMAX_DELAY);
  auto it = receivedJSON_MAP.begin();
  int cleaned = 0;
  while (it != receivedJSON_MAP.end()) {
    if ((unsigned long)(now - CommRecvTime_MAP[it->first]) > (Peer_LinkDrop_MS * 2)) {
      delete it->second;
      CommRecvTime_MAP.erase(it->first);
      it = receivedJSON_MAP.erase(it);
      currentMemoryUsage_bytes -= JSON_SIZE;
      cleaned++;
    } else { ++it; }
  }
  xSemaphoreGive(mapLock);

  if (cleaned > 0)
    Serial.printf("[P2P][MEM] Cleaned %d stale entries, current: %d bytes\n",
                  cleaned, currentMemoryUsage_bytes);
}

void printTimingStats() {
  unsigned long now = millis();
  if ((unsigned long)(now - lastStatsPrint_ms) < STATS_PRINT_INTERVAL_MS) return;
  lastStatsPrint_ms += STATS_PRINT_INTERVAL_MS;
  if (p2p_loopCount == 0) return;

  unsigned long avg    = p2p_totalLoopTime_us / p2p_loopCount;
  unsigned long jitter = p2p_maxLoopTime_us - p2p_minLoopTime_us;
  Serial.printf("[P2P][TIMING] Loops:%lu Avg:%lu us Jitter:%lu us ActiveRobots:%d\n",
                p2p_loopCount, avg, jitter, receivedJSON_MAP.size());
  Serial.printf("[P2P][MEM] Current:%d Peak:%d bytes\n",
                currentMemoryUsage_bytes, peakMemoryUsage_bytes);

  p2p_loopCount = p2p_totalLoopTime_us = 0;
  p2p_maxLoopTime_us = 0;
  p2p_minLoopTime_us = 999999;
}

// ============================================================
// ====== Puppet 함수들 =======================================
// ============================================================

static inline void clear_motion_targets() {
  target_turn_pulses = 0;
  target_move_pulses = 0;
  start_left_count   = left_encoder_count;
  start_right_count  = right_encoder_count;
  integral_error     = 0.0f;
}

static inline void enter_escaping(uint16_t ms = ESCAPING_MS) {
  escaping_until_ms = millis() + ms;
  Motors_forward(FWD_SPD);
  state = STATE_ESCAPING;
}

static inline void start_emergency_left_spin() {
  unsigned long now    = millis();
  emergency_back_until = now + BACK_MS;
  emergency_spin_until = emergency_back_until + EMERGENCY_SPIN_MS;
  Motors_backward(FWD_SPD);
  state = STATE_EMERGENCY;
  turn_change_count = 0;
  last_turn_direction = -1;
  oscillation_timer_start = now;
  Serial.println("[Puppet][EMERGENCY] back -> spin_left");
}

static inline void check_oscillation_and_escape(int dir) {
  if (last_turn_direction != 0 && dir != last_turn_direction) {
    unsigned long now = millis();
    if (now - oscillation_timer_start > OSCILLATION_WINDOW_MS) {
      turn_change_count = 1;
      oscillation_timer_start = now;
    } else { turn_change_count++; }
    if (turn_change_count >= OSCILLATION_COUNT_THRESHOLD) {
      start_emergency_left_spin(); return;
    }
  }
  last_turn_direction = dir;
}

void pi_control(long l_now, long r_now, int* left_pwm, int* right_pwm) {
  long err = l_now - r_now;
  if (abs(err) < ERROR_DEADBAND) err = 0;
  integral_error += (float)err;
  if (integral_error >  INTEGRAL_LIMIT) integral_error =  INTEGRAL_LIMIT;
  if (integral_error < -INTEGRAL_LIMIT) integral_error = -INTEGRAL_LIMIT;
  float u = (K_P * (float)err) + (K_I * integral_error);
  *left_pwm  = constrain((int)lroundf(FWD_SPD - u), MIN_MOTOR_PWM, 255);
  *right_pwm = constrain((int)lroundf(FWD_SPD + u), MIN_MOTOR_PWM, 255);
}

void update_status_led() {
  switch (state) {
    case STATE_IDLE:      Set_LED(1, 0, 30,  0); Set_LED(2, 0, 30,  0); break;
    case STATE_TURNING:   Set_LED(1, 0,  0, 50); Set_LED(2, 0,  0, 50); break;
    case STATE_MOVING:    Set_LED(1, 0, 50,  0); Set_LED(2, 0, 50,  0); break;
    case STATE_AVOID:     Set_LED(1,50, 50,  0); Set_LED(2,50, 50,  0); break;
    case STATE_ESCAPING:  Set_LED(1,50, 25,  0); Set_LED(2,50, 25,  0); break;
    case STATE_EMERGENCY: Set_LED(1,50,  0,  0); Set_LED(2,50,  0,  0); break;
  }
}

void start_motion(float angle_deg, float dist_mm) {
  if (state == STATE_AVOID || state == STATE_ESCAPING || state == STATE_EMERGENCY) return;

  start_left_count  = left_encoder_count;
  start_right_count = right_encoder_count;
  integral_error    = 0.0f;

  target_turn_pulses = (long)lroundf(fabsf(angle_deg) * PULSES_PER_DEGREE);
  target_move_pulses = (long)lroundf(fabsf(dist_mm)  * PULSES_PER_MM);

  if (target_turn_pulses > 0 && fabsf(angle_deg) > ROTATION_DEADBAND_DEG) {
    state = STATE_TURNING;
    if (angle_deg > 0) Motors_spin_right(TURN_SPD);
    else                Motors_spin_left(TURN_SPD);
  } else if (target_move_pulses > 0) {
    state = STATE_MOVING;
  } else {
    state = STATE_IDLE;
    Motors_stop();
  }
}

void handle_udp_packet() {
  int packetSize = udp.parsePacket();
  if (!packetSize) return;

  // 가장 최신 패킷만 사용 (버퍼 플러시)
  while (packetSize) {
    int len = udp.read(packetBuffer, 255);
    if (len > 0) packetBuffer[len] = 0;
    packetSize = udp.parsePacket();
  }

  if (strncasecmp(packetBuffer, "STOP", 4) == 0) {
    Motors_stop(); clear_motion_targets(); state = STATE_IDLE; return;
  }

  if (packetBuffer[0] == 'G' || packetBuffer[0] == 'g') {
    float angle = 0, dist = 0;
    if (sscanf(packetBuffer + 1, "%f %f", &angle, &dist) == 2) {
      if (dist < MIN_DIST_MM) return;
      if (state == STATE_MOVING) {
        long l_now = labs(left_encoder_count - start_left_count);
        long r_now = labs(right_encoder_count - start_right_count);
        if (((l_now + r_now) / 2) < UPDATE_THRESHOLD_PULSES) return;
      }
      start_motion(angle, dist);
    }
  }
}

void control_loop(int r1, int r2, int r3, int r4, int r5) {
  bool obstacle = (r1 > TH_OUTER) || (r2 > TH) || (r3 > TH) || (r4 > TH) || (r5 > TH_OUTER);

  if (obstacle) {
    if (state != STATE_AVOID && state != STATE_ESCAPING && state != STATE_EMERGENCY) {
      Motors_stop(); clear_motion_targets(); state = STATE_AVOID;
    }
  }

  if (state == STATE_EMERGENCY) {
    unsigned long now = millis();
    if (now < emergency_back_until) { Motors_backward(FWD_SPD); return; }
    if (now < emergency_spin_until) { Motors_spin_left(EMERGENCY_SPIN_SPD); return; }
    Motors_stop(); state = STATE_IDLE; return;
  }

  long l_now = labs(left_encoder_count - start_left_count);
  long r_now = labs(right_encoder_count - start_right_count);
  long avg   = (l_now + r_now) / 2;

  switch (state) {
    case STATE_TURNING:
      if (avg >= target_turn_pulses) {
        Motors_stop();
        if (target_move_pulses > 0) {
          start_left_count  = left_encoder_count;
          start_right_count = right_encoder_count;
          integral_error    = 0.0f;
          state = STATE_MOVING;
        } else { state = STATE_IDLE; }
      }
      break;

    case STATE_MOVING:
      if (avg >= target_move_pulses) {
        Motors_stop(); state = STATE_IDLE;
      } else {
        int lp, rp;
        pi_control(l_now, r_now, &lp, &rp);
        Left_mot_forward(lp);
        Right_mot_forward(rp);
      }
      break;

    case STATE_AVOID:
      if ((r1<=TH_OUTER)&&(r2<=TH)&&(r3<=TH)&&(r4<=TH)&&(r5<=TH_OUTER)) {
        enter_escaping(ESCAPING_MS); break;
      }
      if (r3 >= TH) {
        if (abs(r2 - r4) <= DELTA || r2 < r4) {
          Motors_spin_left(TURN_SPD);  check_oscillation_and_escape(-1);
        } else {
          Motors_spin_right(TURN_SPD); check_oscillation_and_escape(+1);
        }
      } else if (r1 >= TH_OUTER || r2 >= TH) {
        Motors_spin_right(TURN_SPD); check_oscillation_and_escape(+1);
      } else if (r4 >= TH || r5 >= TH_OUTER) {
        Motors_spin_left(TURN_SPD); check_oscillation_and_escape(-1);
      }
      break;

    case STATE_ESCAPING:
      if (obstacle) { Motors_stop(); state = STATE_AVOID; break; }
      if ((int32_t)(millis() - escaping_until_ms) >= 0) { Motors_stop(); state = STATE_IDLE; }
      break;

    default: break;
  }
}


// ============================================================
// ====== Core 0: Puppet 태스크 ===============================
// ============================================================
void puppetTask(void* parameter) {
  // UDP 시작 (setup()에서 WiFi 연결 완료 후 이 태스크가 시작되므로 안전)
  udp.begin(UDP_PORT);
  Serial.printf("[Puppet][Core0] UDP server started on port %d\n", UDP_PORT);

  unsigned long last_control_time = 0;
  unsigned long last_led_update   = 0;

  while (true) {
    unsigned long now = millis();

    // UDP 명령 처리 (G command / STOP)
    handle_udp_packet();

    // 이동 제어 (5ms 주기)
    if (now - last_control_time >= CONTROL_INTERVAL_MS) {
      last_control_time = now;
      int r1 = Get_IR(1), r2 = Get_IR(2), r3 = Get_IR(3);
      int r4 = Get_IR(4), r5 = Get_IR(5);
      control_loop(r1, r2, r3, r4, r5);
    }

    // LED 갱신 (100ms 주기)
    if (now - last_led_update >= LED_UPDATE_INTERVAL_MS) {
      last_led_update = now;
      update_status_led();
    }

    vTaskDelay(pdMS_TO_TICKS(1));  // 1ms yield → 다른 태스크에 CPU 양보
  }
}

// ============================================================
// ====== 공통 초기화 =========================================
// ============================================================
void setupNetwork() {
  WiFi.mode(WIFI_STA);
  WiFi.setSleep(false);
  esp_wifi_set_ps(WIFI_PS_NONE);
  WiFi.setAutoReconnect(true);
  WiFi.persistent(true);
  WiFi.begin(SSID, PASSWORD);

  Serial.print("[WiFi] Connecting");
  unsigned long t0 = millis();
  while (WiFi.status() != WL_CONNECTED) {
    delay(WIFI_RECONNECT_INTERVAL_MS); Serial.print(".");
    if (millis() - t0 > WIFI_TIMEOUT_MS) {
      Serial.println("\n[WiFi] Timeout, retrying...");
      WiFi.disconnect(true, true);
      delay(WIFI_RETRY_DELAY_MS);
      WiFi.begin(SSID, PASSWORD);
      t0 = millis(); Serial.print("[WiFi] Connecting");
    }
  }
  Serial.printf("\n[WiFi] Connected: %s\n", WiFi.localIP().toString().c_str());
  Serial.printf("[WiFi] SELF_ID: %s\n", SELF_ID.c_str());

  uint8_t primary = 0;
  wifi_second_chan_t second = WIFI_SECOND_CHAN_NONE;
  esp_wifi_get_channel(&primary, &second);
  Serial.printf("[WiFi] Channel: %d\n", primary);

  // TCP 서버 시작 (P2P용)
  tcpServer.begin();
  Serial.printf("[P2P][Core1] TCP server started on port %d\n", TCP_PORT);

  // ESP-NOW 초기화 (P2P용)
  if (esp_now_init() != ESP_OK) {
    Serial.println("[ESPNOW] Init failed -> restart"); ESP.restart();
  }
  esp_now_register_recv_cb(onEspNowRecv);
  ensureBroadcastPeer();
  Serial.printf("[ESPNOW] Ready. Max payload=%d bytes\n", ESPNOW_MAX_PAYLOAD);
}

void setup() {
  Serial.begin(115200);
  delay(SERIAL_STABILIZE_DELAY_MS);

  randomSeed(esp_random());
  mapLock = xSemaphoreCreateMutex();

  // P2P 타이밍/메모리 초기화
  currentMemoryUsage_bytes     = JSON_SIZE;  // selfMessageDoc 크기
  peakMemoryUsage_bytes        = JSON_SIZE;
  unsigned long now            = millis();
  lastBroadcast_ms             = now;
  lastTcpSend_ms               = now;
  lastMemoryCleanup_ms         = now;
  lastStatsPrint_ms            = now;
  currentBroadcastInterval_ms  = random(BROADCAST_MIN_INTERVAL_MS, BROADCAST_MAX_INTERVAL_MS);

  // MONA 하드웨어 초기화 (Puppet용)
  Mona_ESP_init();
  pinMode(PIN_ENCODER_LEFT,  INPUT);
  pinMode(PIN_ENCODER_RIGHT, INPUT);
  attachInterrupt(digitalPinToInterrupt(PIN_ENCODER_LEFT),  isr_left_encoder,  RISING);
  attachInterrupt(digitalPinToInterrupt(PIN_ENCODER_RIGHT), isr_right_encoder, RISING);
  Set_LED(1, 0, 30, 0);
  Set_LED(2, 0, 30, 0);

  // WiFi + TCP + ESP-NOW 초기화
  setupNetwork();

  // ★ Core 0에 Puppet 태스크 생성
  xTaskCreatePinnedToCore(
    puppetTask,        // 태스크 함수
    "PuppetTask",      // 태스크 이름
    8192,              // 스택 크기 (bytes)
    NULL,              // 파라미터
    2,                 // 우선순위 (loop()의 1보다 높게 → 모터 제어 우선)
    &puppetTaskHandle, // 태스크 핸들
    0                  // Core 0 고정
  );

  Serial.println("[SYSTEM] Dual-core ready!");
  Serial.println("[SYSTEM]   Core 0 → Puppet (UDP motion control)");
  Serial.println("[SYSTEM]   Core 1 → P2P   (ESP-NOW + TCP CBBA)");
}


// ============================================================
// ====== Core 1: P2P loop() ==================================
// ============================================================
void loop() {
  unsigned long loopStart_us = micros();

  // WiFi 재연결 체크
  if (WiFi.status() != WL_CONNECTED) {
    for (auto& c : clients) c.stop();
    clients.clear();
    WiFi.reconnect();
    yield(); return;
  }

  // TCP 클라이언트 수락
  WiFiClient newcomer = tcpServer.available();
  if (newcomer) {
    newcomer.setTimeout(10);
    newcomer.setNoDelay(true);
    bool placed = false;
    for (auto& c : clients) {
      if (!c || !c.connected()) { c.stop(); c = newcomer; placed = true; break; }
    }
    if (!placed) clients.push_back(newcomer);
  }

  // TCP 수신: PC → selfMessageDoc (CBBA 데이터)
  for (auto& c : clients) {
    if (c && c.connected() && c.available()) {
      String line = c.readStringUntil('\n');
      (void)deserializeJson(selfMessageDoc, line);
    }
  }

  // 1. ESP-NOW 브로드캐스트 (100ms 주기)
  broadcastSelfMessageIfDue();

  // 2. TCP 모니터링 송신 (50ms 주기)
  sendTcpMonitoringIfDue();

  // 3. 메모리 정리 (5000ms 주기)
  cleanupStaleEntries();

  // 4. 통계 출력 (5000ms 주기)
  printTimingStats();

  // TCP 클라이언트 정리
  for (auto& c : clients)
    if (c && !c.connected()) c.stop();
  clients.erase(
    std::remove_if(clients.begin(), clients.end(),
                   [](WiFiClient& c){ return !c.connected(); }),
    clients.end()
  );

  // 루프 시간 측정
  unsigned long dur = micros() - loopStart_us;
  p2p_loopCount++;
  p2p_totalLoopTime_us += dur;
  if (dur > p2p_maxLoopTime_us) p2p_maxLoopTime_us = dur;
  if (dur < p2p_minLoopTime_us) p2p_minLoopTime_us = dur;

  yield();
}