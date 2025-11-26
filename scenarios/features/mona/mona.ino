// MONA_ESPNow_Bridge.ino  (ESP32 / Arduino Core 3.3.2, IDF 5.x)
// - TCP(한 줄 JSON) ←→ selfMessageDoc
// - ESP-NOW 브로드캐스트: [sender_id_len][sender_id][json_bytes]
// - ESP-NOW 수신: 위 포맷 파싱 → receivedJSON_MAP 업데이트
// - TCP 모니터 출력: {file_name, self_message, received_messages}\n (다중 클라이언트 허용)
// - Serial Monitor 보기 좋은 출력(요청 포맷)
//
// 필요 라이브러리: ArduinoJson, esp_now (ESP32 SDK), WiFi

#include <Arduino.h>
#include <WiFi.h>
#include <WiFiClient.h>
#include <WiFiServer.h>
#include <esp_now.h>
#include <esp_wifi.h>
#include <ArduinoJson.h>
#include <vector>
#include <map>

// ====== USER CONFIG ======
const char* SSID       = "SSID";
const char* PASSWORD   = "PW";
const String SELF_ID   = "A";         // 보드 고유 ID (예: "A","B"...)
const uint16_t SERVER_PORT = 8080;    // 보드 TCP 서버 포트

const size_t JSON_SIZE = 2048;
const uint32_t Broadcast_TX_MS = 20; // 송신 0.02초
const uint32_t Peer_LinkDrop_MS = 400;  // 이웃 연결 끊김 시간 판단 0.4초
// =========================

WiFiServer server(SERVER_PORT);
std::vector<WiFiClient> clients;                 // 다중 클라이언트 허용

// [이중 메모리 구조]
DynamicJsonDocument selfMessageDoc(JSON_SIZE);           // JSON 메모리 : PC(시뮬레이터) → set_message()로 들어온 JSON 저장
std::map<String, DynamicJsonDocument*> receivedJSON_MAP; // 이웃 보드별 최신 JSON (포인터로 보관) - Stable Buffer
std::map<String, unsigned long> CommRecvTime_MAP;        // ESP-NOW Broadcast 수신시각

unsigned long lastBroadcast = 0;

// Serial 출력 트리거 플래그(새 데이터가 들어왔을 때만 깔끔하게 출력)
bool dirtySelf = false;
bool dirtyNeighbors = false;

// ---------- Broadcast 메세지 최신 상태 유지 ----------
// 1. ESP-NOW 수신 메세지 JSON 변환 (데이터 깨지면, err 반환 및 메모리 삭제)
// 2. receivedJSON_MAP 관리 -> 기존 ID면 옛날 데이터 지우고, 받은 데이터로 덮어쓰기 / 아니면 목록 새로 추가
// 3. CommRecvTime_MAP 관리 -> 수신한 시각 확인 -> sendMonitorToClients 함수 확인하여 통신 연결 판단 로직

bool update_Broadcast_recv_JSON_MAP(const String& senderID, const char* jsonBuf, size_t jsonLen) {
  DynamicJsonDocument* doc = new DynamicJsonDocument(JSON_SIZE);
  DeserializationError err = deserializeJson(*doc, jsonBuf, jsonLen);
  if (err) {
    delete doc;
    return false;
  }
  
  // 1. 데이터 갱신 (덮어쓰기)
  auto it = receivedJSON_MAP.find(senderID);
  if (it != receivedJSON_MAP.end()) {
    delete it->second;
    it->second = doc;
  } else {
    receivedJSON_MAP[senderID] = doc;
  }
  
  // 2. 수신 시각 갱신
  CommRecvTime_MAP[senderID] = millis();
  
  return true;
}

// ---------- arduino serial monitor log ----------
void printMonitorToSerial() {
  Serial.println();
  Serial.printf("---- %s (연결한 보드) 수신 메세지 ----\n\n", SELF_ID.c_str());

  if (!selfMessageDoc.isNull()) {
    serializeJsonPretty(selfMessageDoc, Serial);  // self_message 전체 출력
    Serial.println();
  } else {
    Serial.println("(수신된 self_message 없음)");
  }

  Serial.println();
  Serial.println("---- Broadcast 수신 메세지 ---- ");

  if (receivedJSON_MAP.empty()) {
    Serial.println("(수신된 이웃 메시지 없음)");
  } else {
    for (auto const& kv : receivedJSON_MAP) {
      const String& neighborID = kv.first;
      DynamicJsonDocument* doc = kv.second;

      Serial.println(neighborID);   // 예: B, C, D ...
      Serial.println("~~~");        // 시작 구분선

      if (doc) {
        serializeJsonPretty(*doc, Serial);
        Serial.println();
      } else {
        Serial.println("(NULL)");
      }

      Serial.println("~~~~");       // 끝 구분선
      Serial.println();
    }
  }
}

// ---------- ESP-NOW 수신 콜백 ----------
void onEspNowRecv(const esp_now_recv_info* info, const uint8_t* incoming, int len) {
  // info->src_addr 로 송신자 MAC을 얻을 수 있음 (필요시 사용)
  // const uint8_t* srcMac = info->src_addr;

  if (len <= 1) return;
  uint8_t idLen = incoming[0];
  if (len < 1 + idLen) return;

  // sender ID (payload 내 길이 기반 파싱)
  String senderID = String((const char*)(&incoming[1]), idLen);

  // 본인 ID면 무시
  if (senderID == SELF_ID) return;

  int jsonLen = len - (1 + idLen);
  if (jsonLen <= 0) return;

  // JSON payload (NUL 종결 가정 없음, 길이 기반 파싱)
  const char* jsonPtr = (const char*)(&incoming[1 + idLen]);

  if (update_Broadcast_recv_JSON_MAP(senderID, jsonPtr, jsonLen)) {
    // Serial.printf("[ESP-NOW RX] from %s, %d bytes\n", senderID.c_str(), jsonLen);
    dirtyNeighbors = true;
  } else {
    Serial.println("[ESP-NOW RX] JSON parse failed");
  }
}

// ---------- ESP-NOW 브로드캐스트 ----------
void broadcastSelfMessageIfDue() {
  if (millis() - lastBroadcast < Broadcast_TX_MS) return;
  lastBroadcast = millis();

  if (selfMessageDoc.isNull()) return; // self_message 없으면 스킵

  // 브로드캐스트 Peer 모든 곳 통신 보장
  uint8_t bcast[6] = {0xFF,0xFF,0xFF,0xFF,0xFF,0xFF};
  if (!esp_now_is_peer_exist(bcast)) {
    esp_now_peer_info_t p = {};
    memcpy(p.peer_addr, bcast, 6);
    p.channel = 0;
    p.encrypt = false;
    esp_now_add_peer(&p);
  }

  // self_message 직렬화 (NUL 미포함)
  char jsonBuf[JSON_SIZE];
  size_t jsonLen = serializeJson(selfMessageDoc, jsonBuf, sizeof(jsonBuf));

  uint8_t idLen = SELF_ID.length();
  size_t total = 1 + idLen + jsonLen;
  uint8_t* pkt = new uint8_t[total];

  pkt[0] = idLen;
  memcpy(&pkt[1], SELF_ID.c_str(), idLen);
  memcpy(&pkt[1 + idLen], jsonBuf, jsonLen);

  esp_err_t rc = esp_now_send(bcast, pkt, total);
  if (rc == ESP_OK) {
    // Serial.printf("[ESP-NOW TX] %u bytes\n", (unsigned)total);
  } else {
    Serial.printf("[ESP-NOW TX] send failed: %d\n", (int)rc);
  }

  delete[] pkt;
}

// ---------- TCP: 신규 클라이언트 수락 ----------
void acceptClients() {
  WiFiClient newcomer = server.available();
  if (!newcomer) return;

  // 타임아웃/지연 설정
  newcomer.setTimeout(10);
  newcomer.setNoDelay(true);

  // 끊긴 소켓 자리에 꽂기
  bool placed = false;
  for (auto &c : clients) {
    if (!c || !c.connected()) { c.stop(); c = newcomer; placed = true; break; }
  }
  if (!placed) clients.push_back(newcomer);

  Serial.printf("[TCP] client connected, total=%u\n", (unsigned)clients.size());
}

// ---------- TCP: 끊긴 클라이언트 정리 ----------
void pruneClients() {
  for (auto it = clients.begin(); it != clients.end(); ) {
    if (!(*it) || !(*it).connected()) {
      it = clients.erase(it);
    } else ++it;
  }
}

// ---------- TCP: 각 클라이언트에서 한 줄(JSON) 수신 → selfMessageDoc 갱신 ----------
void readFromClients() {
  for (auto &c : clients) {
    if (!c || !c.connected()) continue;
    while (c.available()) {
      String line = c.readStringUntil('\n');  // NDJSON
      line.trim();
      if (line.length() == 0) continue;

      DeserializationError err = deserializeJson(selfMessageDoc, line);
      if (!err) {
        // Serial.printf("[TCP RX] self_message updated (%u bytes)\n", (unsigned)line.length());
        dirtySelf = true;
      } else {
        Serial.println("[TCP RX] JSON parse failed");
      }
    }
  }
}

// ---------- TCP: 모니터 JSON(self + neighbors) 송신 ----------
void sendMonitorToClients() {
  DynamicJsonDocument monitor(JSON_SIZE*4); // 전체 패킷용 큰 버퍼
  unsigned long now = millis();

  if (!selfMessageDoc.isNull()) {
    String ag = selfMessageDoc["agent_id"] | String("UNKNOWN");
    monitor["file_name"] = "JSON_" + ag + "_send";
    monitor["self_message"] = selfMessageDoc.as<JsonObject>();
  } else {
    monitor["file_name"] = "JSON_UNKNOWN_send";
    JsonObject obj = monitor.createNestedObject("self_message");
    obj["agent_id"] = String("UNKNOWN");
  }

  JsonObject rx = monitor.createNestedObject("received_messages");
  for (auto const &kv : receivedJSON_MAP) {
    String nid = kv.first;
    unsigned long lastSeen = CommRecvTime_MAP[nid];

    // CommRecvTime_MAP 이내에 수신된 데이터만 포함
    if (now - lastSeen <= Peer_LinkDrop_MS) {
      if (kv.second) {
        rx[nid] = kv.second->as<JsonObject>();
      }
    }
    // CommRecvTime_MAP 지난 데이터는 rx에 넣지 않음 -> PC는 "끊김"으로 인식
  }

  String out;
  serializeJson(monitor, out);
  out += "\n"; // 개행 필수(PC 쪽에서 라인 경계로 파싱)

  for (auto &c : clients) {
    if (!c || !c.connected()) continue;
    c.print(out);
  }
}

// ---------- 네트워크 초기화 ----------
void setupNetwork() {
  WiFi.mode(WIFI_STA);
  WiFi.begin(SSID, PASSWORD);
  esp_wifi_set_ps(WIFI_PS_NONE);

  Serial.print("[WiFi] connecting");
  while (WiFi.status() != WL_CONNECTED) { delay(300); Serial.print("."); }
  Serial.println();
  Serial.printf("[WiFi] connected: %s\n", WiFi.localIP().toString().c_str());

  server.begin();
  Serial.printf("[TCP] server started on %u\n", SERVER_PORT);

  if (esp_now_init() != ESP_OK) {
    Serial.println("[ESP-NOW] init failed, rebooting...");
    delay(1000);
    ESP.restart();
  }
  // 콜백 등록
  esp_now_register_recv_cb(onEspNowRecv);
}

// ---------- Arduino 표준 진입 ----------
void setup() {
  Serial.begin(115200);
  delay(300);
  Serial.println();
  Serial.println("=== MONA ESP-NOW Bridge ===");
  Serial.printf("SELF_ID=%s, PORT=%u\n", SELF_ID.c_str(), SERVER_PORT);

  setupNetwork();
}

void loop() {
  acceptClients();
  pruneClients();
  readFromClients();            // PC→보드: self_message 갱신
  broadcastSelfMessageIfDue();  // 보드→이웃: ESP-NOW 브로드캐스트
  sendMonitorToClients();       // 보드→PC: 모니터 JSON 스트리밍 (여기서 워치독 체크 수행)

  // 새 데이터가 들어왔을 때만 출력하도록함
  if (dirtySelf || dirtyNeighbors) {
    printMonitorToSerial();
    dirtySelf = false;
    dirtyNeighbors = false;
  }

  delay(10); // 루프 지연 최소화
}