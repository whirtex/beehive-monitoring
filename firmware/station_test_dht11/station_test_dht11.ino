/*
  Station test on the ESP32-WROVER-DEV: OV2640 camera and DHT11.
  Variant for the demonstration, with the DHT11 in place of the DS18B20.

  Still without the card, the DS3231 and the AHT20. The board creates its own
  Wi-Fi network, and the computer fetches the photos through it:

    network:  beehive-g4
    password: the one in credentials.h
    photos:   http://192.168.4.1/        page that refreshes by itself
              http://192.168.4.1/photo   one 1280 x 720 JPEG photo
              http://192.168.4.1/temp    DHT11 temperature, as text
              http://192.168.4.1/humid   DHT11 humidity, as text

  The serial port, at 115200, shows the CSV with the time since start-up, the
  temperature and the humidity, every 3 s.

  Wiring of the 4-pin DHT11 (grille toward you, pins pointing down):
    1 (left)  -> 3V3
    2         -> GPIO 13, with 10 kOhm to 3V3
    3         -> not connected
    4 (right) -> GND

  Board in the Arduino IDE: "ESP32 Wrover Module", with PSRAM "Enabled".
  Library: DHT sensor library (Adafruit).
  The camera uses the WROVER-KIT pin map, not the AI-Thinker one.
*/

#include "esp_camera.h"
#include <WiFi.h>
#include <WebServer.h>
#include "DHT.h"

// The network password lives in credentials.h, which is not in the
// repository. Copy credentials.h.example as credentials.h and choose the
// password before uploading.
#include "credentials.h"

const char *NETWORK = "beehive-g4";

#define DHT_PIN 13
#define CSV_INTERVAL_MS 3000

// camera pin map on the WROVER-KIT
#define PWDN_GPIO_NUM  -1
#define RESET_GPIO_NUM -1
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

DHT dht(DHT_PIN, DHT11);
WebServer server(80);

float temperature = NAN;
float humidity = NAN;
unsigned long last_csv = 0;

bool start_camera() {
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
  c.pin_pwdn = PWDN_GPIO_NUM;
  c.pin_reset = RESET_GPIO_NUM;
  c.xclk_freq_hz = 20000000;
  c.pixel_format = PIXFORMAT_JPEG;
  c.frame_size = FRAMESIZE_HD;  // 1280 x 720, as in the station
  c.jpeg_quality = 12;          // 0 to 63; lower is better
  c.fb_count = 2;
  c.fb_location = CAMERA_FB_IN_PSRAM;
  c.grab_mode = CAMERA_GRAB_LATEST;  // always the newest frame

  if (!psramFound()) {
    Serial.println("# ERROR: PSRAM is off. Tools > PSRAM > Enabled");
    return false;
  }
  esp_err_t err = esp_camera_init(&c);
  if (err != ESP_OK) {
    Serial.printf("# ERROR: camera did not start (0x%x). Check the flat cable\n", err);
    return false;
  }
  return true;
}

void send_photo() {
  camera_fb_t *fb = esp_camera_fb_get();
  if (!fb) {
    server.send(503, "text/plain", "camera has no frame");
    return;
  }
  server.sendHeader("Cache-Control", "no-store");
  server.setContentLength(fb->len);
  server.send(200, "image/jpeg", "");
  server.client().write(fb->buf, fb->len);
  esp_camera_fb_return(fb);
}

void send_temperature() {
  server.send(200, "text/plain", isnan(temperature) ? "no reading" : String(temperature, 2));
}

void send_humidity() {
  server.send(200, "text/plain", isnan(humidity) ? "no reading" : String(humidity, 0));
}

void send_page() {
  server.send(200, "text/html",
    "<!doctype html><meta name=viewport content='width=device-width'>"
    "<title>beehive-g4</title><body style='margin:0;background:#111;color:#eee;font-family:sans-serif'>"
    "<p style='margin:8px'>Temperature: <b id=t>...</b> &deg;C &middot; humidity: <b id=u>...</b> %</p>"
    "<img id=f style='width:100%'>"
    "<script>"
    "function photo(){var i=new Image();i.onload=function(){f.src=i.src;setTimeout(photo,200)};"
    "i.onerror=function(){setTimeout(photo,1000)};i.src='/photo?'+Date.now()}"
    "function temp(){fetch('/temp').then(r=>r.text()).then(x=>t.textContent=x);"
    "fetch('/humid').then(r=>r.text()).then(x=>u.textContent=x)}"
    "photo();temp();setInterval(temp,3000)"
    "</script>");
}

void setup() {
  Serial.begin(115200);
  delay(500);

  dht.begin();

  bool camera_ok = start_camera();

  WiFi.softAP(NETWORK, AP_PASSWORD);
  Serial.print("# network ");
  Serial.print(NETWORK);
  Serial.print(", address http://");
  Serial.println(WiFi.softAPIP());

  server.on("/", send_page);
  server.on("/temp", send_temperature);
  server.on("/humid", send_humidity);
  if (camera_ok) {
    server.on("/photo", send_photo);
  }
  server.begin();

  Serial.println("time_s,temperature_c,humidity_pct");
}

void loop() {
  server.handleClient();

  unsigned long now = millis();
  if (now - last_csv >= CSV_INTERVAL_MS) {
    last_csv = now;
    // reading the DHT11 blocks for about 25 ms, which does not disturb the server
    temperature = dht.readTemperature();
    humidity = dht.readHumidity();
    if (isnan(temperature) || isnan(humidity)) {
      Serial.println("# WARNING: no DHT11 reading. Check the 10 kOhm resistor and pin 2 of the sensor");
    }

    Serial.print(now / 1000.0, 1);
    Serial.print(",");
    if (!isnan(temperature)) Serial.print(temperature, 1);
    Serial.print(",");
    if (!isnan(humidity)) Serial.print(humidity, 0);
    Serial.println();
  }
}
