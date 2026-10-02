/*
  Teste da estacao na ESP32-WROVER-DEV: camera OV2640 e DS18B20.

  Ainda sem cartao, sem DS3231 e sem AHT20. A placa cria uma rede Wi-Fi
  propria, e o computador busca as fotos por ela:

    rede:  colmeia-g4
    senha: a de credenciais.h
    fotos: http://192.168.4.1/        pagina que atualiza sozinha
           http://192.168.4.1/foto    uma foto JPEG de 1280 x 720
           http://192.168.4.1/temp    temperatura do DS18B20, em texto

  A porta serial, a 115200, mostra o CSV com o tempo desde a partida e a
  temperatura interna, a cada 3 s.

  Ligacao do DS18B20 (face plana virada para voce, terminais para baixo):
    esquerda -> GND
    meio     -> GPIO 13, com 4,7 kOhm para o 3V3
    direita  -> 3V3

  Placa na Arduino IDE: "ESP32 Wrover Module", com PSRAM "Enabled".
  Bibliotecas: OneWire e DallasTemperature.
  A camera usa o mapeamento do WROVER-KIT, e nao o da AI-Thinker.
*/

#include "esp_camera.h"
#include <WiFi.h>
#include <WebServer.h>
#include <OneWire.h>
#include <DallasTemperature.h>

// A senha da rede fica em credenciais.h, que nao vai para o repositorio.
// Copie credenciais.h.exemplo como credenciais.h e escolha a senha antes
// de gravar.
#include "credenciais.h"

const char *REDE = "colmeia-g4";

#define PINO_DS18B20 13
#define INTERVALO_CSV_MS 3000

// mapeamento da camera no WROVER-KIT
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

OneWire barramento(PINO_DS18B20);
DallasTemperature sensores(&barramento);
WebServer servidor(80);

float temperatura = NAN;
unsigned long ultimo_csv = 0;
bool conversao_pedida = false;

bool iniciar_camera() {
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
  c.frame_size = FRAMESIZE_HD;  // 1280 x 720, como na estacao
  c.jpeg_quality = 12;          // 0 a 63; menor e melhor
  c.fb_count = 2;
  c.fb_location = CAMERA_FB_IN_PSRAM;
  c.grab_mode = CAMERA_GRAB_LATEST;  // sempre o quadro mais novo

  if (!psramFound()) {
    Serial.println("# ERRO: PSRAM desligada. Ferramentas > PSRAM > Enabled");
    return false;
  }
  esp_err_t erro = esp_camera_init(&c);
  if (erro != ESP_OK) {
    Serial.printf("# ERRO: camera nao iniciou (0x%x). Confira o cabo flat\n", erro);
    return false;
  }
  return true;
}

void enviar_foto() {
  camera_fb_t *fb = esp_camera_fb_get();
  if (!fb) {
    servidor.send(503, "text/plain", "camera sem quadro");
    return;
  }
  servidor.sendHeader("Cache-Control", "no-store");
  servidor.setContentLength(fb->len);
  servidor.send(200, "image/jpeg", "");
  servidor.client().write(fb->buf, fb->len);
  esp_camera_fb_return(fb);
}

void enviar_temperatura() {
  servidor.send(200, "text/plain", isnan(temperatura) ? "sem leitura" : String(temperatura, 2));
}

void enviar_pagina() {
  servidor.send(200, "text/html",
    "<!doctype html><meta name=viewport content='width=device-width'>"
    "<title>colmeia-g4</title><body style='margin:0;background:#111;color:#eee;font-family:sans-serif'>"
    "<p style='margin:8px'>Temperatura interna: <b id=t>...</b> &deg;C</p>"
    "<img id=f style='width:100%'>"
    "<script>"
    "function foto(){var i=new Image();i.onload=function(){f.src=i.src;setTimeout(foto,200)};"
    "i.onerror=function(){setTimeout(foto,1000)};i.src='/foto?'+Date.now()}"
    "function temp(){fetch('/temp').then(r=>r.text()).then(x=>t.textContent=x)}"
    "foto();temp();setInterval(temp,3000)"
    "</script>");
}

void setup() {
  Serial.begin(115200);
  delay(500);

  sensores.begin();
  sensores.setResolution(12);
  sensores.setWaitForConversion(false);  // nao trava o servidor durante os 750 ms da conversao
  if (sensores.getDeviceCount() == 0) {
    Serial.println("# AVISO: nenhum DS18B20 no GPIO 13. Confira o resistor de 4,7 kOhm");
  }

  bool camera_ok = iniciar_camera();

  WiFi.softAP(REDE, SENHA_AP);
  Serial.print("# rede ");
  Serial.print(REDE);
  Serial.print(", endereco http://");
  Serial.println(WiFi.softAPIP());

  servidor.on("/", enviar_pagina);
  servidor.on("/temp", enviar_temperatura);
  if (camera_ok) {
    servidor.on("/foto", enviar_foto);
  }
  servidor.begin();

  Serial.println("tempo_s,temperatura_interna_c");
}

void loop() {
  servidor.handleClient();

  unsigned long agora = millis();
  if (!conversao_pedida && agora - ultimo_csv >= INTERVALO_CSV_MS - 800) {
    sensores.requestTemperatures();
    conversao_pedida = true;
  }
  if (conversao_pedida && agora - ultimo_csv >= INTERVALO_CSV_MS) {
    float t = sensores.getTempCByIndex(0);
    // -127 e o valor que a biblioteca devolve quando o sensor nao responde
    temperatura = (t == DEVICE_DISCONNECTED_C) ? NAN : t;
    conversao_pedida = false;
    ultimo_csv = agora;

    Serial.print(agora / 1000.0, 1);
    Serial.print(",");
    if (isnan(temperatura)) {
      Serial.println("");
    } else {
      Serial.println(temperatura, 2);
    }
  }
}
