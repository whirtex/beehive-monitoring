/*
  Test of the ESP32 internal clock, without the DS3231.

  The board sleeps 10 s, wakes, writes the time of the internal clock to the
  serial port and sleeps again, as the station does. During deep sleep, the
  time keeps being counted by an internal oscillator of the ESP32, less
  accurate than the DS3231 crystal. analysis/clock_test.py writes the computer
  time, set over the internet, next to each line: the difference between the
  two shows how much the internal clock drifts per hour.

  Every cold start (cable plugged, EN button, power loss) resets the internal
  clock, and the station has no network to set it again.

  Board in the Arduino IDE: "ESP32 Wrover Module". Uses no library.
*/

#include <sys/time.h>
#include "esp_sleep.h"

#define SLEEP_S 10

RTC_DATA_ATTR unsigned long wakes = 0;  // survives deep sleep

void setup() {
  Serial.begin(115200);

  if (esp_sleep_get_wakeup_cause() != ESP_SLEEP_WAKEUP_TIMER) {
    struct timeval zero = {0, 0};
    settimeofday(&zero, NULL);
    wakes = 0;
    Serial.println("# cold start: internal clock reset");
  }

  struct timeval now;
  gettimeofday(&now, NULL);
  wakes++;
  Serial.printf("clock_s=%.3f wakes=%lu\n", now.tv_sec + now.tv_usec / 1e6, wakes);
  Serial.flush();

  esp_deep_sleep(SLEEP_S * 1000000ULL);
}

void loop() {}
