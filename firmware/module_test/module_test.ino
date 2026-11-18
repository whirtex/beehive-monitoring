/*
  Test of the station modules, one at a time, for the step-by-step guide of
  docs/assembly.md.

  Every 5 s the board looks for everything that may be connected and writes to
  the serial port, at 115200, what it found: DS18B20, AHT20, DS3231, card and
  camera. What is not connected yet shows as "not found", with a hint. So a
  module can be connected and checked on the serial monitor without uploading
  the program again at each step.

  With the camera and the card connected, each round takes an 800 x 600 photo
  and writes it to /test.jpg, reading it back to check.

  Wiring (docs/assembly.md):
    DS18B20  data on 13, with 4.7 kOhm to 3V3
    I2C      SDA on 32, SCL on 33 (AHT20 at 0x38, DS3231 at 0x68)
    card     SPI: SCK 14, MISO 15, MOSI 2, CS 0; module on 5V (VCC)

  The first time, and whenever the DS3231 battery fails, the clock is set to the
  time this program was compiled, and also when it reads earlier than the
  compile time, which cannot be right.

  Board in the Arduino IDE: "ESP32 Wrover Module", PSRAM "Enabled", Upload
  Speed 115200. Libraries: OneWire and DallasTemperature. The AHT20 and the
  DS3231 are read straight from their registers, with no library.
*/

#include "esp_camera.h"
#include <Wire.h>
#include <SPI.h>
#include <SD.h>
#include <OneWire.h>
#include <DallasTemperature.h>

#define DS18B20_PIN 13
#define SDA_PIN 32
#define SCL_PIN 33
#define SCK_PIN 14
#define MISO_PIN 15
#define MOSI_PIN 2
#define CS_PIN 0

#define AHT20_ADDR 0x38
#define DS3231_ADDR 0x68
#define INTERVAL_MS 5000

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

// ------------------------------------------------------------- test

bool camera_ok = false;
unsigned long round_n = 0;

void list_i2c() {
  Serial.print("I2C:     ");
  int found = 0;
  for (uint8_t e = 1; e < 127; e++) {
    if (responds(e)) {
      Serial.printf("0x%02X ", e);
      found++;
    }
  }
  if (found == 0) Serial.print("nothing (check SDA on 32, SCL on 33 and 3V3)");
  Serial.println();
}

void test_ds18b20() {
  Serial.print("DS18B20: ");
  float t = read_ds18b20();
  if (isnan(t)) Serial.println("not found (check the 4.7 kOhm resistor on column 4 and the wire colours)");
  else Serial.printf("1 sensor, %.2f C\n", t);
}

void test_aht20() {
  Serial.print("AHT20:   ");
  float t, h;
  if (!responds(AHT20_ADDR)) Serial.println("not found (0x38)");
  else if (!read_aht20(t, h)) Serial.println("busy; tries again next round");
  else Serial.printf("%.1f C, %.0f %% humidity\n", t, h);
}

void test_ds3231() {
  Serial.print("DS3231:  ");
  if (!responds(DS3231_ADDR)) {
    Serial.println("not found (0x68)");
    return;
  }
  bool set = check_clock();
  Time t = read_time();
  Serial.printf("%04d-%02d-%02d %02d:%02d:%02d%s\n", t.year, t.month, t.day, t.h, t.mi, t.s,
                set ? "  (set now to the compile time)" : "");
}

void test_card_and_camera() {
  if (!card_ok) {
    SD.end();
    card_ok = SD.begin(CS_PIN, cardSpi, 4000000);
  }
  camera_fb_t *fb = NULL;
  if (camera_ok) {
    esp_camera_fb_return(esp_camera_fb_get());  // discards an old frame
    fb = esp_camera_fb_get();
  }
  Serial.print("Camera:  ");
  if (!camera_ok) Serial.println("did not start (check the flat cable)");
  else if (!fb) Serial.println("started, but gave no photo");
  else Serial.printf("photo of %ux%u, %u bytes\n", fb->width, fb->height, fb->len);

  Serial.print("Card:    ");
  if (!card_ok) {
    Serial.println("not found (check the module on 5V, the four wires and the card in FAT32)");
  } else {
    const char *name = fb ? "/test.jpg" : "/test.txt";
    File f = SD.open(name, FILE_WRITE);
    size_t written = 0, expected = 0;
    if (f) {
      if (fb) {
        expected = fb->len;
        written = f.write(fb->buf, fb->len);
      } else {
        char text[32];
        expected = snprintf(text, sizeof text, "round %lu\n", round_n);
        written = f.write((const uint8_t *)text, expected);
      }
      f.close();
    }
    File g = SD.open(name);
    size_t read_back = g ? g.size() : 0;
    if (g) g.close();
    if (written == expected && read_back == expected && expected > 0) {
      Serial.printf("%.1f GB, %s written and read back (%u bytes)\n", SD.cardSize() / 1e9, name + 1,
                    (unsigned)read_back);
    } else {
      Serial.printf("mounted, but the write failed (%u of %u bytes)\n", (unsigned)written, (unsigned)expected);
      card_ok = false;  // mounts again next round
    }
  }
  if (fb) esp_camera_fb_return(fb);
}

void setup() {
  Serial.begin(115200);
  delay(500);
  if (esp_reset_reason() == ESP_RST_BROWNOUT) {
    Serial.println("# The board restarted on a brownout: check the capacitor on 5V");
  }
  camera_ok = start_camera();
  Wire.begin(SDA_PIN, SCL_PIN);
  cardSpi.begin(SCK_PIN, MISO_PIN, MOSI_PIN, CS_PIN);
  sensors.setResolution(12);
  Serial.println("# module test: a report every 5 s");
}

void loop() {
  round_n++;
  Serial.printf("\n--- round %lu ---\n", round_n);
  test_ds18b20();
  list_i2c();
  test_aht20();
  test_ds3231();
  test_card_and_camera();
  delay(INTERVAL_MS);
}
