/*
  Station firmware: a photo of the entrance every 10 s and the temperatures
  every 5 min, all on the microSD card, with the DS3231 time and the board
  asleep between one wake and the next.

  At every wake:
    - reads the DS3231 time;
    - by day (START_HOUR to END_HOUR), takes an 800 x 600 photo and writes it
      to /YYYY-MM-DD/HHMMSS.jpg;
    - at the first wake of each 5 min period, reads the DS18B20 (inside the
      hive) and the AHT20 (outside) and appends a line to /environment.csv;
    - sleeps until the next multiple of 10 s (by day) or of 5 min (at night).

  /events.txt gets a line at every start that is not a wake from sleep
  (power on, brownout, hang and watchdog restart...) and at every camera
  failure, so that a problem shows up when the card is retrieved even if the
  station recovers by itself. The watchdog restarts the board if a wake takes
  more than 30 s.

  CAMERA_ALL_DAY = true also takes photos at night, for a bench test that runs
  overnight. At the hive, false.

  The battery_v column of the CSV stays empty: the solar supply was not built
  and no pin reads the battery voltage.

  Wiring (docs/assembly.md):
    DS18B20  data on 13, with 4.7 kOhm to 3V3
    I2C      SDA on 32, SCL on 33 (AHT20 at 0x38, DS3231 at 0x68)
    card     SPI: SCK 14, MISO 15, MOSI 2, CS 0; module on 5V (VCC)

  Board in the Arduino IDE: "ESP32 Wrover Module", PSRAM "Enabled",
  Upload Speed 115200. Libraries: OneWire and DallasTemperature. To upload,
  remove the wire from pin 2 and put it back afterwards.
*/

#include "esp_camera.h"
#include "esp_sleep.h"
#include "esp_task_wdt.h"
#include <Wire.h>
#include <SPI.h>
#include <SD.h>
#include <OneWire.h>
#include <DallasTemperature.h>

// ------------------------------------------------------------- options

#define CAMERA_ALL_DAY false   // true for an overnight bench test
#define START_HOUR 6           // photos from 06:00...
#define END_HOUR 18            // ...to 18:00
#define PHOTO_STEP_S 10
#define SENSOR_STEP_S 300
#define DISCARDED_FRAMES 3     // the auto exposure settles in the first frames
#define WATCHDOG_S 30

// ------------------------------------------------------------- pins

#define DS18B20_PIN 13
#define SDA_PIN 32
#define SCL_PIN 33
#define SCK_PIN 14
#define MISO_PIN 15
#define MOSI_PIN 2
#define CS_PIN 0

#define AHT20_ADDR 0x38
#define DS3231_ADDR 0x68

// camera with the WROVER-KIT pin map
#define XCLK_GPIO_NUM  21
#define SIOD_GPIO_NUM  26
#define SIOC_GPIO_NUM  27
#define Y9_GPIO_NUM    35
#define Y8_GPIO_NUM    34
#define Y7_GPIO_NUM    39
#define Y6_GPIO_NUM    36
#define Y5_GPIO_NUM    19
#define Y4_GPIO_NUM    18
#define Y3_GPIO_NUM     5
#define Y2_GPIO_NUM     4
#define VSYNC_GPIO_NUM 25
#define HREF_GPIO_NUM  23
#define PCLK_GPIO_NUM  22

OneWire bus(DS18B20_PIN);
DallasTemperature sensors(&bus);
SPIClass cardSpi(HSPI);

// Kept in the memory that survives deep sleep.
RTC_DATA_ATTR int64_t last_photo = -1;     // number of the last 10 s period with a photo
RTC_DATA_ATTR int64_t last_reading = -1;   // number of the last 5 min period read
RTC_DATA_ATTR uint32_t wakes = 0;

struct Time {
  int year, month, day, h, mi, s;
  bool ok;
};

// ------------------------------------------------------------- clock

uint8_t bcd(uint8_t v) { return (v >> 4) * 10 + (v & 0x0F); }
uint8_t to_bcd(uint8_t v) { return ((v / 10) << 4) | (v % 10); }

bool responds(uint8_t address) {
  Wire.beginTransmission(address);
  return Wire.endTransmission() == 0;
}

uint8_t read_register(uint8_t r) {
  Wire.beginTransmission(DS3231_ADDR);
  Wire.write(r);
  Wire.endTransmission();
  Wire.requestFrom(DS3231_ADDR, 1);
  return Wire.read();
}

void write_register(uint8_t r, uint8_t v) {
  Wire.beginTransmission(DS3231_ADDR);
  Wire.write(r);
  Wire.write(v);
  Wire.endTransmission();
}

Time read_time() {
  Time t = {};
  if (!responds(DS3231_ADDR)) return t;
  Wire.beginTransmission(DS3231_ADDR);
  Wire.write(0x00);
  Wire.endTransmission();
  if (Wire.requestFrom(DS3231_ADDR, 7) != 7) return t;
  uint8_t r[7];
  for (int i = 0; i < 7; i++) r[i] = Wire.read();
  t.s = bcd(r[0] & 0x7F);
  t.mi = bcd(r[1] & 0x7F);
  t.h = bcd(r[2] & 0x3F);
  t.day = bcd(r[4] & 0x3F);
  t.month = bcd(r[5] & 0x1F);
  t.year = 2000 + bcd(r[6]);
  t.ok = t.year >= 2026 && t.month >= 1 && t.month <= 12 && t.day >= 1;
  return t;
}

// Days since 01/01/1970 (Howard Hinnant's algorithm), to count seconds
// across the turn of the day or the month.
int64_t days_since_1970(int y, int m, int d) {
  y -= m <= 2;
  int era = y / 400;
  int year_of_era = y - era * 400;
  int day_of_year = (153 * (m + (m > 2 ? -3 : 9)) + 2) / 5 + d - 1;
  int day_of_era = year_of_era * 365 + year_of_era / 4 - year_of_era / 100 + day_of_year;
  return (int64_t)era * 146097 + day_of_era - 719468;
}

int64_t seconds(const Time &t) {
  return days_since_1970(t.year, t.month, t.day) * 86400 + t.h * 3600 + t.mi * 60 + t.s;
}

Time compile_time() {
  const char *months = "JanFebMarAprMayJunJulAugSepOctNovDec";
  char m[4] = {__DATE__[0], __DATE__[1], __DATE__[2], 0};
  Time t = {};
  t.month = (strstr(months, m) - months) / 3 + 1;
  t.day = atoi(__DATE__ + 4);
  t.year = atoi(__DATE__ + 7);
  t.h = atoi(__TIME__);
  t.mi = atoi(__TIME__ + 3);
  t.s = atoi(__TIME__ + 6);
  t.ok = true;
  return t;
}

// Sets the clock to the compile time when the oscillator stopped (battery) or
// when the clock reads earlier than the compile time, which cannot be right.
bool check_clock() {
  if (!responds(DS3231_ADDR)) return false;
  Time c = compile_time();
  Time t = read_time();
  bool stopped = read_register(0x0F) & 0x80;
  if (!stopped && t.ok && seconds(t) >= seconds(c)) return false;
  Wire.beginTransmission(DS3231_ADDR);
  Wire.write(0x00);
  Wire.write(to_bcd(c.s));
  Wire.write(to_bcd(c.mi));
  Wire.write(to_bcd(c.h));
  Wire.write(1);
  Wire.write(to_bcd(c.day));
  Wire.write(to_bcd(c.month));
  Wire.write(to_bcd(c.year - 2000));
  Wire.endTransmission();
  write_register(0x0F, read_register(0x0F) & ~0x80);
  return true;
}

// ------------------------------------------------------------- sensors

float read_ds18b20() {
  sensors.begin();
  if (sensors.getDeviceCount() == 0) return NAN;
  sensors.setResolution(12);
  sensors.requestTemperatures();
  float t = sensors.getTempCByIndex(0);
  return t == DEVICE_DISCONNECTED_C ? NAN : t;
}

// AHT20: command 0xAC 0x33 0x00, 6-byte answer after 80 ms
bool read_aht20(float &temp, float &hum) {
  if (!responds(AHT20_ADDR)) return false;
  Wire.requestFrom(AHT20_ADDR, 1);
  if ((Wire.read() & 0x08) == 0) {
    Wire.beginTransmission(AHT20_ADDR);
    Wire.write(0xBE); Wire.write(0x08); Wire.write(0x00);
    Wire.endTransmission();
    delay(10);
  }
  Wire.beginTransmission(AHT20_ADDR);
  Wire.write(0xAC); Wire.write(0x33); Wire.write(0x00);
  Wire.endTransmission();
  delay(80);
  uint8_t d[6];
  if (Wire.requestFrom(AHT20_ADDR, 6) != 6) return false;
  for (int i = 0; i < 6; i++) d[i] = Wire.read();
  if (d[0] & 0x80) return false;
  uint32_t u = ((uint32_t)d[1] << 12) | ((uint32_t)d[2] << 4) | (d[3] >> 4);
  uint32_t t = ((uint32_t)(d[3] & 0x0F) << 16) | ((uint32_t)d[4] << 8) | d[5];
  temp = t * 200.0 / 1048576 - 50;
  hum = u * 100.0 / 1048576;
  return true;
}

// ------------------------------------------------------------- card

bool card_ok = false;

void write_line(const char *file, const char *header, const char *line) {
  if (!card_ok) return;
  bool is_new = !SD.exists(file);
  File f = SD.open(file, FILE_APPEND);
  if (!f) return;
  if (is_new && header) f.println(header);
  f.println(line);
  f.close();
}

void event(const Time &t, const char *text) {
  char line[160];
  if (t.ok) {
    snprintf(line, sizeof line, "%04d-%02d-%02d %02d:%02d:%02d,%s",
             t.year, t.month, t.day, t.h, t.mi, t.s, text);
  } else {
    snprintf(line, sizeof line, "no time,%s", text);
  }
  Serial.printf("# event: %s\n", line);
  write_line("/events.txt", "date_time,event", line);
}

// ------------------------------------------------------------- camera

bool start_camera() {
  if (!psramFound()) return false;
  camera_config_t c = {};
  c.ledc_channel = LEDC_CHANNEL_0;
  c.ledc_timer = LEDC_TIMER_0;
  c.pin_d0 = Y2_GPIO_NUM;
  c.pin_d1 = Y3_GPIO_NUM;
  c.pin_d2 = Y4_GPIO_NUM;
  c.pin_d3 = Y5_GPIO_NUM;
  c.pin_d4 = Y6_GPIO_NUM;
  c.pin_d5 = Y7_GPIO_NUM;
  c.pin_d6 = Y8_GPIO_NUM;
  c.pin_d7 = Y9_GPIO_NUM;
  c.pin_xclk = XCLK_GPIO_NUM;
  c.pin_pclk = PCLK_GPIO_NUM;
  c.pin_vsync = VSYNC_GPIO_NUM;
  c.pin_href = HREF_GPIO_NUM;
  c.pin_sccb_sda = SIOD_GPIO_NUM;
  c.pin_sccb_scl = SIOC_GPIO_NUM;
  c.sccb_i2c_port = 1;  // the camera is on I2C 1; the sensors, on 0
  c.pin_pwdn = -1;
  c.pin_reset = -1;
  c.xclk_freq_hz = 20000000;
  c.pixel_format = PIXFORMAT_JPEG;
  c.frame_size = FRAMESIZE_SVGA;
  c.jpeg_quality = 12;
  c.fb_count = 1;
  c.fb_location = CAMERA_FB_IN_PSRAM;
  c.grab_mode = CAMERA_GRAB_LATEST;
  return esp_camera_init(&c) == ESP_OK;
}

const char *reason_name(esp_reset_reason_t m) {
  switch (m) {
    case ESP_RST_POWERON: return "power on";
    case ESP_RST_EXT: return "external reset";
    case ESP_RST_SW: return "software restart";
    case ESP_RST_PANIC: return "hang (panic)";
    case ESP_RST_INT_WDT: return "interrupt watchdog";
    case ESP_RST_TASK_WDT: return "watchdog: a wake took more than 30 s";
    case ESP_RST_WDT: return "watchdog";
    case ESP_RST_DEEPSLEEP: return "wake from sleep";
    case ESP_RST_BROWNOUT: return "brownout";
    case ESP_RST_SDIO: return "SDIO";
    default: return "unknown reason";
  }
}

// ------------------------------------------------------------- main

void go_to_sleep(int64_t now_s, unsigned long start_ms, bool day) {
  int step = day ? PHOTO_STEP_S : SENSOR_STEP_S;
  int64_t target = (now_s / step + 1) * step;
  // aims half a second after the turn, so the clock already reads the new period
  int64_t wait_ms = (target - now_s) * 1000 + 500 - (int64_t)(millis() - start_ms);
  if (wait_ms < 1000) wait_ms += step * 1000;
  Serial.printf("# awake %lu ms; sleeps %lld ms\n", millis() - start_ms, wait_ms);
  Serial.flush();
  if (card_ok) SD.end();
  esp_sleep_enable_timer_wakeup((uint64_t)wait_ms * 1000);
  esp_deep_sleep_start();
}

void setup() {
  unsigned long start = millis();
  Serial.begin(115200);

  esp_task_wdt_config_t wdt = {};
  wdt.timeout_ms = WATCHDOG_S * 1000;
  wdt.idle_core_mask = 0;
  wdt.trigger_panic = true;
  if (esp_task_wdt_reconfigure(&wdt) != ESP_OK) esp_task_wdt_init(&wdt);
  esp_task_wdt_add(NULL);

  wakes++;
  esp_reset_reason_t reason = esp_reset_reason();

  Wire.begin(SDA_PIN, SCL_PIN);
  bool clock_set = check_clock();
  Time t = read_time();

  cardSpi.begin(SCK_PIN, MISO_PIN, MOSI_PIN, CS_PIN);
  card_ok = SD.begin(CS_PIN, cardSpi, 4000000);

  if (reason != ESP_RST_DEEPSLEEP) {
    last_photo = last_reading = -1;
    char text[96];
    snprintf(text, sizeof text, "start: %s", reason_name(reason));
    event(t, text);
    if (clock_set) event(t, "clock set to the compile time");
    if (!t.ok) event(t, "clock did not respond");
  }
  if (!card_ok) Serial.println("# card not found");

  if (!t.ok) {
    // Without the time the photo cannot be named: tries again in 10 s.
    Serial.println("# no time from the DS3231");
    esp_sleep_enable_timer_wakeup(PHOTO_STEP_S * 1000000ULL);
    esp_deep_sleep_start();
  }

  int64_t now = seconds(t);
  bool day = CAMERA_ALL_DAY || (t.h >= START_HOUR && t.h < END_HOUR);
  Serial.printf("# %04d-%02d-%02d %02d:%02d:%02d, wake %lu\n",
                t.year, t.month, t.day, t.h, t.mi, t.s, (unsigned long)wakes);

  // Photo
  int64_t photo_period = now / PHOTO_STEP_S;
  if (day && photo_period != last_photo) {
    last_photo = photo_period;
    if (!start_camera()) {
      event(t, "camera did not start");
    } else {
      for (int i = 0; i < DISCARDED_FRAMES; i++) esp_camera_fb_return(esp_camera_fb_get());
      camera_fb_t *fb = esp_camera_fb_get();
      if (!fb) {
        event(t, "camera gave no photo");
      } else if (card_ok) {
        char folder[16], name[32];
        snprintf(folder, sizeof folder, "/%04d-%02d-%02d", t.year, t.month, t.day);
        snprintf(name, sizeof name, "%s/%02d%02d%02d.jpg", folder, t.h, t.mi, t.s);
        if (!SD.exists(folder)) SD.mkdir(folder);
        File f = SD.open(name, FILE_WRITE);
        size_t written = f ? f.write(fb->buf, fb->len) : 0;
        if (f) f.close();
        Serial.printf("# photo %s, %u bytes%s\n", name, (unsigned)fb->len,
                      written == fb->len ? "" : " (WRITE FAILED)");
      }
      if (fb) esp_camera_fb_return(fb);
    }
  }

  // Sensors, once per 5 min period
  int64_t sensor_period = now / SENSOR_STEP_S;
  if (sensor_period != last_reading) {
    last_reading = sensor_period;
    float inside = read_ds18b20();
    float outside = NAN, humidity = NAN;
    read_aht20(outside, humidity);
    char line[96], ti[12] = "", to[12] = "", ho[12] = "";
    if (!isnan(inside)) snprintf(ti, sizeof ti, "%.2f", inside);
    if (!isnan(outside)) snprintf(to, sizeof to, "%.1f", outside);
    if (!isnan(humidity)) snprintf(ho, sizeof ho, "%.0f", humidity);
    snprintf(line, sizeof line, "%04d-%02d-%02d,%02d:%02d:%02d,%s,%s,%s,",
             t.year, t.month, t.day, t.h, t.mi, t.s, ti, to, ho);
    Serial.printf("# environment: %s\n", line);
    write_line("/environment.csv",
               "date,time,t_inside_c,t_outside_c,humidity_outside_pct,battery_v", line);
  }

  go_to_sleep(now, start, day);
}

void loop() {}
