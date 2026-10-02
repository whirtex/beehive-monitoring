/*
  DHT11 and DS1302 clock on the Arduino Uno.
  It prints on the serial port the CSV that the station will write to the card.

  Wiring:
    DHT11 VCC   -> 5V
    DHT11 DATA  -> pin 2
    DHT11 GND   -> GND
    10 kOhm resistor between VCC and DATA

    DS1302 VCC -> 5V
    DS1302 GND -> GND
    DS1302 CLK -> pin 5
    DS1302 DAT -> pin 4
    DS1302 RST -> pin 3

  The DS1302 is not I2C: it uses three wires and the Rtc by Makuna library.
  Without the CR2032 battery in the holder, the clock resets every time the
  power drops and goes back to the time of the last upload.
*/

#include "DHT.h"
#include <ThreeWire.h>
#include <RtcDS1302.h>

#define DHT_PIN 2
#define DHT_TYPE DHT11

DHT dht(DHT_PIN, DHT_TYPE);

// pin order: DAT, CLK, RST
ThreeWire wires(4, 5, 3);
RtcDS1302<ThreeWire> rtc(wires);

void setup() {
  Serial.begin(9600);
  dht.begin();
  rtc.Begin();

  RtcDateTime compiled = RtcDateTime(__DATE__, __TIME__);

  if (rtc.GetIsWriteProtected()) {
    rtc.SetIsWriteProtected(false);
  }
  if (!rtc.GetIsRunning()) {
    rtc.SetIsRunning(true);
  }
  if (!rtc.IsDateTimeValid() || rtc.GetDateTime() < compiled) {
    rtc.SetDateTime(compiled);
  }

  Serial.println("datetime,temperature_c,humidity_pct");
}

void loop() {
  delay(3000);

  RtcDateTime now = rtc.GetDateTime();
  float humidity = dht.readHumidity();
  float temperature = dht.readTemperature();

  if (isnan(humidity) || isnan(temperature)) {
    Serial.println("sensor read error");
    return;
  }

  char datetime[20];
  snprintf(datetime, sizeof(datetime), "%04u-%02u-%02u %02u:%02u:%02u",
           now.Year(), now.Month(), now.Day(),
           now.Hour(), now.Minute(), now.Second());

  Serial.print(datetime);
  Serial.print(",");
  Serial.print(temperature, 1);
  Serial.print(",");
  Serial.println(humidity, 1);
}
