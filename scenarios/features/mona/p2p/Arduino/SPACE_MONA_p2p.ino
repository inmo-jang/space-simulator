#include <Arduino.h>
#include <WiFi.h>
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

// ====== USER CONFIG ======
const char* SSID       = "InMOLab";
const char* PASSWORD   = "dlsahfoq104!";
const String SELF_ID   = "Your SELF_ID";
const uint16_t SERVER_PORT = 8080;

// JSON 버퍼는 넉넉하게(단, 실제 ESPNOW payload는 1470 제한)
const size_t JSON_SIZE = 2048;
const int TOTAL_ROBOTS = 12;

// ====== TIMING CONSTANTS (누적 오차 방지 방식) ======
const uint32_t BROADCAST_MIN_INTERVAL_MS = 100;
const uint32_t BROADCAST_MAX_INTERVAL_MS = 100;
const uint32_t TCP_MONITORING_INTERVAL_MS = 100;
const uint32_t MEMORY_CLEANUP_INTERVAL_MS = 5000;
const uint32_t STATS_PRINT_INTERVAL_MS = 5000;

const uint32_t Peer_LinkDrop_MS = 900;
const uint32_t WIFI_RECONNECT_INTERVAL_MS = 300;
const uint32_t WIFI_TIMEOUT_MS = 10000;
const uint32_t WIFI_RETRY_DELAY_MS = 200;
const uint32_t SERIAL_STABILIZE_DELAY_MS = 1000;

// ESPNOW v2 payload 최대
static const int ESPNOW_MAX_PAYLOAD = 1470;

WiFiServer server(SERVER_PORT);
std::vector<WiFiClient> clients;

DynamicJsonDocument selfMessageDoc(JSON_SIZE);
std::map<String, DynamicJsonDocument*> receivedJSON_MAP;
std::map<String, unsigned long> CommRecvTime_MAP;

SemaphoreHandle_t mapLock;

// ====== 누적 오차 방지를 위한 타이밍 변수 ======
unsigned long lastBroadcast_ms = 0;
unsigned long lastTcpSend_ms = 0;
unsigned long lastMemoryCleanup_ms = 0;
unsigned long lastStatsPrint_ms = 0;
uint32_t currentBroadcastInterval_ms = BROADCAST_MIN_INTERVAL_MS;

// ====== TIMING MONITORING ======
unsigned long loopCount = 0;
unsigned long maxLoopTime_us = 0;
unsigned long minLoopTime_us = 999999;
unsigned long totalLoopTime_us = 0;

// ====== MEMORY MONITORING ======
size_t currentMemoryUsage_bytes = 0;
size_t peakMemoryUsage_bytes = 0;

static char g_jsonBuf[JSON_SIZE];
static uint8_t g_pkt[ESPNOW_MAX_PAYLOAD];

// -------------------------
// Memory cleanup
// -------------------------
void cleanupStaleEntries() {
  unsigned long now = millis();
  
  // 누적 오차 방지: 정확히 5초마다 실행
  if ((unsigned long)(now - lastMemoryCleanup_ms) < MEMORY_CLEANUP_INTERVAL_MS) {
    return;
  }
  
  lastMemoryCleanup_ms += MEMORY_CLEANUP_INTERVAL_MS;
  
  xSemaphoreTake(mapLock, portMAX_DELAY);
  
  auto it = receivedJSON_MAP.begin();
  int cleanedCount = 0;
  
  while (it != receivedJSON_MAP.end()) {
    if ((unsigned long)(now - CommRecvTime_MAP[it->first]) > (Peer_LinkDrop_MS * 2)) {
      delete it->second;
      CommRecvTime_MAP.erase(it->first);
      it = receivedJSON_MAP.erase(it);
      
      currentMemoryUsage_bytes -= JSON_SIZE;
      cleanedCount++;
    } else {
      ++it;
    }
  }
  
  xSemaphoreGive(mapLock);
  
  if (cleanedCount > 0) {
    Serial.printf("[MEMORY] Cleaned %d stale entries, current: %d bytes\n", 
                  cleanedCount, currentMemoryUsage_bytes);
  }
}

// -------------------------
// Update map
// -------------------------
bool update_Broadcast_recv_JSON_MAP(const String& senderID, const char* jsonBuf, size_t jsonLen) {
  DynamicJsonDocument* doc = new DynamicJsonDocument(JSON_SIZE);
  DeserializationError err = deserializeJson(*doc, jsonBuf, jsonLen);
  if (err) {
    delete doc;
    return false;
  }

  if (xSemaphoreTake(mapLock, 0) != pdTRUE) {
    delete doc;
    return false;
  }

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

  update_Broadcast_recv_JSON_MAP(senderID,
                                (const char*)(&incoming[1 + idLen]),
                                (size_t)jsonLen);
}

void ensureBroadcastPeer() {
  uint8_t bcast[6] = {0xFF,0xFF,0xFF,0xFF,0xFF,0xFF};
  if (esp_now_is_peer_exist(bcast)) return;

  esp_now_peer_info_t p = {};
  memcpy(p.peer_addr, bcast, 6);
  p.ifidx = WIFI_IF_STA;
  p.channel = WiFi.channel();
  p.encrypt = false;

  esp_err_t rc = esp_now_add_peer(&p);
  if (rc != ESP_OK && rc != ESP_ERR_ESPNOW_EXIST) {
  }
}

void broadcastSelfMessageIfDue() {
  unsigned long now = millis();
  
  // 누적 오차 방지: (now - lastBroadcast_ms) 사용
  if ((unsigned long)(now - lastBroadcast_ms) < currentBroadcastInterval_ms) {
    return;
  }

  // 누적 오차 방지: lastBroadcast_ms += interval
  lastBroadcast_ms += currentBroadcastInterval_ms;
  
  // 다음 간격 설정 (충돌 회피를 위한 랜덤화)
  currentBroadcastInterval_ms = random(BROADCAST_MIN_INTERVAL_MS, BROADCAST_MAX_INTERVAL_MS);

  if (selfMessageDoc.isNull()) return;

  ensureBroadcastPeer();

  size_t jsonLen = serializeJson(selfMessageDoc, g_jsonBuf, sizeof(g_jsonBuf));
  if (jsonLen == 0) return;

  const uint8_t idLen = (uint8_t)SELF_ID.length();
  const size_t total = 1 + (size_t)idLen + jsonLen;

  if ((int)total > ESPNOW_MAX_PAYLOAD) {
    return;
  }

  g_pkt[0] = idLen;
  memcpy(&g_pkt[1], SELF_ID.c_str(), idLen);
  memcpy(&g_pkt[1 + idLen], g_jsonBuf, jsonLen);

  uint8_t bcast[6] = {0xFF,0xFF,0xFF,0xFF,0xFF,0xFF};
  esp_err_t rc = esp_now_send(bcast, g_pkt, total);
  if (rc != ESP_OK) {
    //Serial.printf("[ESP-NOW TX] send failed: %d\n", (int)rc);
  }
}

// -------------------------
// TCP Monitoring (누적 오차 방지)
// -------------------------
void sendTcpMonitoringIfDue() {
  unsigned long now = millis();
  
  // 누적 오차 방지
  if ((unsigned long)(now - lastTcpSend_ms) < TCP_MONITORING_INTERVAL_MS) {
    return;
  }
  
  lastTcpSend_ms += TCP_MONITORING_INTERVAL_MS;
  
  // 동적 메모리 할당 (실제 필요한 크기만)
  size_t activeRobots = receivedJSON_MAP.size();
  size_t monitorSize = JSON_SIZE * (activeRobots + 1);
  
  DynamicJsonDocument monitor(monitorSize);
  monitor["agent_id"] = SELF_ID;
  JsonObject rx = monitor.createNestedObject("received_messages");

  xSemaphoreTake(mapLock, portMAX_DELAY);
  for (auto const &kv : receivedJSON_MAP) {
    if ((unsigned long)(now - CommRecvTime_MAP[kv.first]) <= Peer_LinkDrop_MS) {
      rx[kv.first] = kv.second->as<JsonObject>();
    }
  }
  xSemaphoreGive(mapLock);

  String out;
  serializeJson(monitor, out);
  out += "\n";

  for (auto &c : clients) {
    if (c && c.connected()) {
      c.print(out);
    }
  }
  
  // 피크 메모리 추적
  size_t tempMemory = currentMemoryUsage_bytes + monitorSize;
  if (tempMemory > peakMemoryUsage_bytes) {
    peakMemoryUsage_bytes = tempMemory;
  }
}

// -------------------------
// Statistics printing
// -------------------------
void printTimingStats() {
  unsigned long now = millis();
  
  // 누적 오차 방지
  if ((unsigned long)(now - lastStatsPrint_ms) < STATS_PRINT_INTERVAL_MS) {
    return;
  }
  
  lastStatsPrint_ms += STATS_PRINT_INTERVAL_MS;
  
  if (loopCount == 0) return;
  
  unsigned long avgLoopTime_us = totalLoopTime_us / loopCount;
  unsigned long jitter_us = maxLoopTime_us - minLoopTime_us;
  
  Serial.printf("[TIMING] Loops: %lu, Avg: %lu us, Min: %lu us, Max: %lu us\n",
                loopCount, avgLoopTime_us, minLoopTime_us, maxLoopTime_us);
  Serial.printf("[TIMING] Jitter: %lu us\n", jitter_us);
  Serial.printf("[MEMORY] Current: %d bytes, Peak: %d bytes, Active robots: %d\n",
                currentMemoryUsage_bytes, peakMemoryUsage_bytes, receivedJSON_MAP.size());
  
  // 통계 리셋
  loopCount = 0;
  totalLoopTime_us = 0;
  maxLoopTime_us = 0;
  minLoopTime_us = 999999;
}

void setupNetwork() {
  WiFi.mode(WIFI_STA);
  WiFi.setSleep(false);
  esp_wifi_set_ps(WIFI_PS_NONE);
  WiFi.setAutoReconnect(true);
  WiFi.persistent(true);

  WiFi.begin(SSID, PASSWORD);

  Serial.print("[WiFi] Connecting to AP");
  unsigned long t0 = millis();
  while (WiFi.status() != WL_CONNECTED) {
    delay(WIFI_RECONNECT_INTERVAL_MS);
    Serial.print(".");
    if (millis() - t0 > WIFI_TIMEOUT_MS) {
      Serial.println("\n[WiFi] connect timeout -> retry");
      WiFi.disconnect(true, true);
      delay(WIFI_RETRY_DELAY_MS);
      WiFi.begin(SSID, PASSWORD);
      t0 = millis();
      Serial.print("[WiFi] Connecting to AP");
    }
  }

  Serial.println("\n[WiFi] Connected!");
  Serial.printf("[WiFi] IP Address: %s\n", WiFi.localIP().toString().c_str());
  Serial.printf("[WiFi] Board ID (SELF_ID): %s\n", SELF_ID.c_str());

  uint8_t primary = 0;
  wifi_second_chan_t second = WIFI_SECOND_CHAN_NONE;
  esp_wifi_get_channel(&primary, &second);
  Serial.printf("[WiFi] Channel: %d\n", primary);

  server.begin();

  if (esp_now_init() != ESP_OK) {
    Serial.println("[ESPNOW] init failed -> restart");
    ESP.restart();
  }

  esp_now_register_recv_cb(onEspNowRecv);
  ensureBroadcastPeer();

  // Serial.printf("[ESPNOW] Ready. Max payload=%d bytes\n", ESPNOW_MAX_PAYLOAD);
  // Serial.printf("[CONFIG] JSON_SIZE=%d bytes, Broadcast interval=%d~%dms\n",
  //               JSON_SIZE, BROADCAST_MIN_INTERVAL_MS, BROADCAST_MAX_INTERVAL_MS);
}

void setup() {
  Serial.begin(115200);
  delay(SERIAL_STABILIZE_DELAY_MS);

  randomSeed(esp_random());
  mapLock = xSemaphoreCreateMutex();

  // 초기 메모리 설정
  currentMemoryUsage_bytes = JSON_SIZE;  // selfMessageDoc
  peakMemoryUsage_bytes = JSON_SIZE;
  
  // 타이밍 초기화 (millis()로 현재 시간 설정)
  unsigned long now = millis();
  lastBroadcast_ms = now;
  lastTcpSend_ms = now;
  lastMemoryCleanup_ms = now;
  lastStatsPrint_ms = now;
  
  // 첫 브로드캐스트 간격 랜덤화
  currentBroadcastInterval_ms = random(BROADCAST_MIN_INTERVAL_MS, BROADCAST_MAX_INTERVAL_MS);

  setupNetwork();
  
  Serial.println("[SYSTEM] Using drift-free timing (누적 오차 방지)");
}

void loop() {
  unsigned long loopStart_us = micros();

  // ========== WiFi 재연결 체크 ==========
  if (WiFi.status() != WL_CONNECTED) {
    for (auto &c : clients) c.stop();
    clients.clear();
    WiFi.reconnect();
    yield();
    return;
  }

  // ========== TCP 클라이언트 수락 ==========
  WiFiClient newcomer = server.available();
  if (newcomer) {
    newcomer.setTimeout(10);
    newcomer.setNoDelay(true);

    bool placed = false;
    for (auto &c : clients) {
      if (!c || !c.connected()) {
        c.stop();
        c = newcomer;
        placed = true;
        break;
      }
    }
    if (!placed) clients.push_back(newcomer);
  }

  // ========== TCP 데이터 수신 (PC -> ESP32) ==========
  for (auto &c : clients) {
    if (c && c.connected() && c.available()) {
      String line = c.readStringUntil('\n');
      (void)deserializeJson(selfMessageDoc, line);
    }
  }

  // ========== 핵심 작업 (누적 오차 방지 방식) ==========
  
  // 1. ESP-NOW 브로드캐스트 (가장 중요!)
  broadcastSelfMessageIfDue();
  
  // 2. TCP 모니터링 송신
  sendTcpMonitoringIfDue();
  
  // 3. 메모리 정리 (주기적)
  cleanupStaleEntries();
  
  // 4. 통계 출력 (주기적)
  printTimingStats();

  // ========== TCP 클라이언트 정리 ==========
  for (auto &c : clients) {
    if (c && !c.connected()) c.stop();
  }
  clients.erase(std::remove_if(clients.begin(), clients.end(),
    [](WiFiClient& c){ return !c.connected(); }), clients.end());

  // ========== 루프 시간 측정 ==========
  unsigned long loopEnd_us = micros();
  unsigned long loopDuration_us = loopEnd_us - loopStart_us;
  
  loopCount++;
  totalLoopTime_us += loopDuration_us;
  
  if (loopDuration_us > maxLoopTime_us) maxLoopTime_us = loopDuration_us;
  if (loopDuration_us < minLoopTime_us) minLoopTime_us = loopDuration_us;

  // ========== CPU 양보 (다른 태스크에게 시간 할애) ==========
  yield();
}
