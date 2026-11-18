/*
  Station simulation for presentations: the ESP32 receives over USB the frames
  of a hive video, in place of the camera, and writes each one to the card as
  the station would (/YYYY-MM-DD/HHMMSS.jpg, with the DS3231 time). With each
  photo come a SIMULATED temperature and humidity, which go to a line of
  /environment.csv with the same time as the photo. events.txt marks the start
  as "simulation", and analysis/results.py uses that.

  The frames are sent by analysis/simulate.py, on the computer. Serial protocol,
  at 460800: the computer sends "PHOTO <bytes> <t_inside> <t_outside> <humidity>\n"
  and then the photo in 8 kB chunks; the board answers "+" after each chunk and
  "OK <file>" at the end. "END\n" writes the end of the simulation to events.txt.

  Same wiring as the station (docs/assembly.md). Board in the Arduino IDE:
  "ESP32 Wrover Module", PSRAM "Enabled". To upload, remove the wire from pin 2.
*/

#include <Wire.h>
#include <SPI.h>
#include <SD.h>
#include <OneWire.h>
#include <DallasTemperature.h>

#define SPEED 460800
#define CHUNK 8192

#define DS18B20_PIN 13
#define SDA_PIN 32
#define SCL_PIN 33
#define SCK_PIN 14
#define MISO_PIN 15
#define MOSI_PIN 2
#define CS_PIN 0

#define AHT20_ADDR 0x38
#define DS3231_ADDR 0x68

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

// ------------------------------------------------------------- main

// Environment line with the simulated values that came with the photo.
void write_environment(const Time &t, float inside, float outside, float humidity) {
  char line[96];
  snprintf(line, sizeof line, "%04d-%02d-%02d,%02d:%02d:%02d,%.2f,%.1f,%.0f,",
           t.year, t.month, t.day, t.h, t.mi, t.s, inside, outside, humidity);
  write_line("/environment.csv",
             "date,time,t_inside_c,t_outside_c,humidity_outside_pct,battery_v", line);
}

// Receives a photo of n bytes in chunks, with "+" after each one.
void receive_photo(size_t n, float inside, float outside, float humidity) {
  uint8_t *buf = (uint8_t *)ps_malloc(n);
  if (!buf) {
    Serial.println("ERROR no memory");
    return;
  }
  Serial.println("READY");
  size_t received = 0;
  unsigned long last = millis();
  while (received < n && millis() - last < 5000) {
    size_t chunk_end = min(n, (received / CHUNK + 1) * CHUNK);
    while (received < chunk_end && millis() - last < 5000) {
      int k = Serial.read(buf + received, chunk_end - received);
      if (k > 0) {
        received += k;
        last = millis();
      }
    }
    if (received == chunk_end) Serial.write('+');
  }
  if (received < n) {
    Serial.printf("ERROR received %u of %u bytes\n", (unsigned)received, (unsigned)n);
    free(buf);
    return;
  }
  Time t = read_time();
  char folder[16], name[32];
  snprintf(folder, sizeof folder, "/%04d-%02d-%02d", t.year, t.month, t.day);
  snprintf(name, sizeof name, "%s/%02d%02d%02d.jpg", folder, t.h, t.mi, t.s);
  if (!SD.exists(folder)) SD.mkdir(folder);
  File f = SD.open(name, FILE_WRITE);
  size_t written = f ? f.write(buf, n) : 0;
  if (f) f.close();
  free(buf);
  if (written == n) Serial.printf("OK %s\n", name);
  else Serial.printf("ERROR wrote %u of %u bytes to %s\n", (unsigned)written, (unsigned)n, name);
  write_environment(t, inside, outside, humidity);
}

void setup() {
  Serial.setRxBufferSize(CHUNK * 2);
  Serial.begin(SPEED);
  Wire.begin(SDA_PIN, SCL_PIN);
  check_clock();
  cardSpi.begin(SCK_PIN, MISO_PIN, MOSI_PIN, CS_PIN);
  card_ok = SD.begin(CS_PIN, cardSpi, 4000000);
  Time t = read_time();
  event(t, "start: simulation, photos of a video received over USB");
  Serial.println(card_ok ? "SIMULATION READY" : "ERROR card not found");
}

void loop() {
  if (!Serial.available()) {
    delay(5);
    return;
  }
  String line = Serial.readStringUntil('\n');
  line.trim();
  if (line.startsWith("PHOTO ")) {
    float ti = 0, to = 0, ho = 0;
    unsigned long n = 0;
    sscanf(line.c_str() + 6, "%lu %f %f %f", &n, &ti, &to, &ho);
    receive_photo(n, ti, to, ho);
  } else if (line == "END") {
    event(read_time(), "end of the simulation");
    Serial.println("OK end");
  } else if (line == "PING") {
    Serial.println(card_ok ? "SIMULATION READY" : "ERROR card not found");
  }
}
