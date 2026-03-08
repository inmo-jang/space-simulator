#include <WiFi.h>
#include <WiFiUdp.h>
#include "Mona_ESP_lib.h"
#include <math.h>
#include <strings.h> // strncasecmp를 위한 헤더 추가 (Core 3.x 대응)

// ===================== WiFi / UDP =====================
const char* ssid     = "InMOLab";
const char* password = "dlsahfoq104!";
WiFiUDP udp;
const int localPort = 8080;
char packetBuffer[255];

// ===================== 상태 정의 =====================
enum RobotState {
  STATE_IDLE,
  STATE_TURNING,
  STATE_MOVING,
  STATE_AVOID,
  STATE_ESCAPING,
  STATE_EMERGENCY
};
volatile RobotState state = STATE_IDLE;

// 펄스/제어 상수
static const float PULSES_PER_MM     = 18.0f;
static const float PULSES_PER_DEGREE = 12.8f;
static const int   FWD_SPD  = 100;
static const int   TURN_SPD = 100;

// 900펄스마다 새로운 명령을 받음
static const long  UPDATE_THRESHOLD_PULSES = 900;   
static const float MIN_DIST_MM               = 40.0f; 

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

// ===================== PI 제어 게인 =====================
static const float K_P = 0.5f;
static const float K_I = 0.002f;

// 적분 제한
static const float INTEGRAL_LIMIT = 500.0f;

// 오차 데드밴드
static const int ERROR_DEADBAND = 5;

// 비상 동작 속도
static const int EMERGENCY_SPIN_SPD = 200;

static const uint16_t ESCAPING_MS = 1000;
unsigned long escaping_until_ms = 0;

static const unsigned long EMERGENCY_SPIN_MS = 1200;
static const unsigned long BACK_MS           = 120;
static const unsigned long OSCILLATION_WINDOW_MS = 1200;
static const int   OSCILLATION_COUNT_THRESHOLD = 4;

int last_turn_direction = 0;         
int turn_change_count   = 0;
unsigned long oscillation_timer_start = 0;

unsigned long emergency_back_until = 0;
unsigned long emergency_spin_until = 0;

volatile long left_encoder_count  = 0;
volatile long right_encoder_count = 0;

void IRAM_ATTR isr_left_encoder()  { left_encoder_count++; }
void IRAM_ATTR isr_right_encoder() { right_encoder_count++; }

static long  start_left_count  = 0;
static long  start_right_count = 0;
static long  target_turn_pulses = 0;
static long  target_move_pulses = 0;
static float integral_error = 0.0f;

// ===================== 제어 주기 관리 =====================
static const unsigned long CONTROL_INTERVAL_MS = 5;  // 5ms 제어 주기
unsigned long last_control_time = 0;

// ===================== LED 상태 표시 =====================
static const unsigned long LED_UPDATE_INTERVAL_MS = 100;
unsigned long last_led_update = 0;

// ===================== 유틸리티 =====================
static inline void clear_motion_targets() {
  target_turn_pulses = 0;
  target_move_pulses = 0;
  start_left_count  = left_encoder_count;
  start_right_count = right_encoder_count;
  integral_error = 0.0f;
}

static inline void enter_escaping(uint16_t ms = ESCAPING_MS) {
  escaping_until_ms = millis() + ms;
  Motors_forward(FWD_SPD);
  state = STATE_ESCAPING;
}

static inline void start_emergency_left_spin() {
  unsigned long now = millis();
  emergency_back_until = now + BACK_MS;
  emergency_spin_until = emergency_back_until + EMERGENCY_SPIN_MS;

  Motors_backward(FWD_SPD);
  state = STATE_EMERGENCY;

  turn_change_count = 0;
  last_turn_direction = -1;
  oscillation_timer_start = now;

  Serial.println("[EMERGENCY] back -> spin_left");
}

static inline void check_oscillation_and_escape(int current_direction) {
  if (last_turn_direction != 0 && current_direction != last_turn_direction) {
    unsigned long now = millis();
    if (now - oscillation_timer_start > OSCILLATION_WINDOW_MS) {
      turn_change_count = 1;
      oscillation_timer_start = now;
    } else {
      turn_change_count++;
    }

    if (turn_change_count >= OSCILLATION_COUNT_THRESHOLD) {
      start_emergency_left_spin();
      return;
    }
  }
  last_turn_direction = current_direction;
}

// ===================== 개선된 PI 제어 =====================
void pi_control(long l_now, long r_now, int* left_pwm, int* right_pwm) {
  long err = l_now - r_now;
  if (abs(err) < ERROR_DEADBAND) {
    err = 0;
  }
  integral_error += (float)err;
  if (integral_error > INTEGRAL_LIMIT) integral_error = INTEGRAL_LIMIT;
  if (integral_error < -INTEGRAL_LIMIT) integral_error = -INTEGRAL_LIMIT;
  float u = (K_P * (float)err) + (K_I * integral_error);
  *left_pwm  = constrain((int)lroundf(FWD_SPD - u), MIN_MOTOR_PWM, 255);
  *right_pwm = constrain((int)lroundf(FWD_SPD + u), MIN_MOTOR_PWM, 255);
}

// ===================== LED 상태 표시 =====================
void update_status_led() {
  switch (state) {
    case STATE_IDLE:
      Set_LED(1, 0, 30, 0);   // 녹색: 대기
      Set_LED(2, 0, 30, 0);
      break;
    case STATE_TURNING:
      Set_LED(1, 0, 0, 50);   // 파란색: 회전
      Set_LED(2, 0, 0, 50);
      break;
    case STATE_MOVING:
      Set_LED(1, 0, 50, 0);   // 밝은 녹색: 이동
      Set_LED(2, 0, 50, 0);
      break;
    case STATE_AVOID:
      Set_LED(1, 50, 50, 0);  // 노란색: 회피
      Set_LED(2, 50, 50, 0);
      break;
    case STATE_ESCAPING:
      Set_LED(1, 50, 25, 0);  // 주황색: 탈출
      Set_LED(2, 50, 25, 0);
      break;
    case STATE_EMERGENCY:
      Set_LED(1, 50, 0, 0);   // 빨간색: 비상
      Set_LED(2, 50, 0, 0);
      break;
  }
}

// ===================== 함수 선언 =====================
void start_motion(float angle_deg, float dist_mm);
void handle_udp_packet();
void control_loop(int r1, int r2, int r3, int r4, int r5);

void setup() {
  Serial.begin(115200);
  Mona_ESP_init();

  pinMode(PIN_ENCODER_LEFT, INPUT);
  pinMode(PIN_ENCODER_RIGHT, INPUT);
  attachInterrupt(digitalPinToInterrupt(PIN_ENCODER_LEFT), isr_left_encoder,  RISING);
  attachInterrupt(digitalPinToInterrupt(PIN_ENCODER_RIGHT), isr_right_encoder, RISING);

  // WiFi 연결
  WiFi.mode(WIFI_STA);
  WiFi.begin(ssid, password);
  while (WiFi.status() != WL_CONNECTED) {
    delay(500); Serial.print(".");
  }
  Serial.println("\nWiFi connected");
  Serial.println(WiFi.localIP());

  udp.begin(localPort);
  // 초기 LED 상태
  Set_LED(1, 0, 30, 0);
  Set_LED(2, 0, 30, 0);
  
  Serial.println("MONA ready puppet!");
}

void loop() {
  unsigned long now = millis();
  // UDP 패킷 처리
  handle_udp_packet();

  // 제어 주기 확인 (5ms 간격)
  if (now - last_control_time >= CONTROL_INTERVAL_MS) {
    last_control_time = now;

    // 싱글코어: IR 센서를 loop()에서 직접 읽음
    int r1 = Get_IR(1);
    int r2 = Get_IR(2);
    int r3 = Get_IR(3);
    int r4 = Get_IR(4);
    int r5 = Get_IR(5);

    control_loop(r1, r2, r3, r4, r5);
  }
  // LED 업데이트 (100ms 간격)
  if (now - last_led_update >= LED_UPDATE_INTERVAL_MS) {
    last_led_update = now;
    update_status_led();
  }
}

void start_motion(float angle_deg, float dist_mm) {
  if (state == STATE_AVOID || state == STATE_ESCAPING || state == STATE_EMERGENCY) {
    return;
  }

  start_left_count  = left_encoder_count;
  start_right_count = right_encoder_count;
  integral_error = 0.0f;

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

  // 버퍼 플러시
  while (packetSize) {
     int len = udp.read(packetBuffer, 255);
     if (len > 0) packetBuffer[len] = 0;
     packetSize = udp.parsePacket();
  }

  if (strncasecmp(packetBuffer, "STOP", 4) == 0) {
    Motors_stop();
    clear_motion_targets();
    state = STATE_IDLE;
    return;
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
      Motors_stop();
      clear_motion_targets();
      state = STATE_AVOID;
    }
  }

  if (state == STATE_EMERGENCY) {
    unsigned long now = millis();
    if (now < emergency_back_until) {
      Motors_backward(FWD_SPD);
      return;
    }
    if (now < emergency_spin_until) {
      Motors_spin_left(EMERGENCY_SPIN_SPD);
      return;
    }
    Motors_stop();
    state = STATE_IDLE;
    return;
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
          integral_error = 0.0f;
          state = STATE_MOVING;
        } else {
          state = STATE_IDLE;
        }
      }
      break;

    case STATE_MOVING:
      if (avg >= target_move_pulses) {
        Motors_stop();
        state = STATE_IDLE;
      } else {
        int left_pwm, right_pwm;
        pi_control(l_now, r_now, &left_pwm, &right_pwm);
        Left_mot_forward(left_pwm);
        Right_mot_forward(right_pwm);
      }
      break;

    case STATE_AVOID:
      if ((r1 <= TH_OUTER) && (r2 <= TH) && (r3 <= TH) && (r4 <= TH) && (r5 <= TH_OUTER)) {
        enter_escaping(ESCAPING_MS);
        break;
      }
      if (r3 >= TH) {
        if (abs(r2 - r4) <= DELTA || r2 < r4) {
          Motors_spin_left(TURN_SPD);
          check_oscillation_and_escape(-1);
        } else {
          Motors_spin_right(TURN_SPD);
          check_oscillation_and_escape(+1);
        }
      } else if (r1 >= TH_OUTER || r2 >= TH) {
        Motors_spin_right(TURN_SPD);
        check_oscillation_and_escape(+1);
      } else if (r4 >= TH || r5 >= TH_OUTER) {
        Motors_spin_left(TURN_SPD);
        check_oscillation_and_escape(-1);
      }
      break;

    case STATE_ESCAPING:
      if (obstacle) {
        Motors_stop();
        state = STATE_AVOID;
        break;
      }
      if ((int32_t)(millis() - escaping_until_ms) >= 0) {
        Motors_stop();
        state = STATE_IDLE;
      }
      break;

    default: break;
  }
}
