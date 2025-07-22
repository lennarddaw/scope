#include "esp_camera.h"
#include <WiFi.h>
#include <WebServer.h>
#include <PubSubClient.h>
#include <ESPmDNS.h>

// Bekannte WLANs
const char* ssidList[] = {"devolo-108", "Schule"};
const char* passwordList[] = {"BKAJYQKRJAEVHEFO", "WlanAccess"};
const int networkCount = sizeof(ssidList) / sizeof(ssidList[0]);

// MQTT-Konfiguration
const char* mqtt_server = "192.168.2.194";
const int   mqtt_port   = 1883;
const char* mqtt_topic  = "home/esp/cam/#";

// Webserver auf Port 80
WebServer server(80);

// MQTT-Client
WiFiClient espClient;
PubSubClient mqttClient(espClient);

// Globale Flags
volatile bool streamActive = false;
volatile bool brightLedState = false;

// LED-Pins: LED_PIN (z. B. rote LED) und LED_PIN_BRIGHT (z. B. helle LED)
#define LED_PIN 33         
#define LED_PIN_BRIGHT 4   

unsigned long lastStatusPrint = 0;
unsigned long lastBlinkTime = 0;
bool ledState = false;

// Kamera-Konfiguration (funktionierende Konfiguration)
camera_config_t config = {
  .pin_pwdn     = 32,
  .pin_reset    = -1,
  .pin_xclk     = 0,
  .pin_sscb_sda = 26,
  .pin_sscb_scl = 27,
  .pin_d7       = 35,
  .pin_d6       = 34,
  .pin_d5       = 39,
  .pin_d4       = 36,
  .pin_d3       = 21,
  .pin_d2       = 19,
  .pin_d1       = 18,
  .pin_d0       = 5,
  .pin_vsync    = 25,
  .pin_href     = 23,
  .pin_pclk     = 22,
  .xclk_freq_hz = 20000000,
  .ledc_timer   = LEDC_TIMER_0,
  .ledc_channel = LEDC_CHANNEL_0,
  .pixel_format = PIXFORMAT_JPEG,
  .frame_size   = FRAMESIZE_SVGA,
  .jpeg_quality = 10,
  .fb_count     = 2,
};

// Verbindung zu einem der bekannten WLANs herstellen
void connectToWiFi() {
  bool connected = false;
  for (int i = 0; i < networkCount && !connected; i++) {
    Serial.print("Versuche, mich mit ");
    Serial.println(ssidList[i]);
    WiFi.begin(ssidList[i], passwordList[i]);
    unsigned long startAttemptTime = millis();
    while (WiFi.status() != WL_CONNECTED && millis() - startAttemptTime < 10000) {
      delay(500);
      Serial.print(".");
    }
    if (WiFi.status() == WL_CONNECTED) {
      connected = true;
      Serial.println();
      Serial.print("Verbunden mit: ");
      Serial.println(ssidList[i]);
      Serial.print("IP-Adresse: ");
      Serial.println(WiFi.localIP());
      break;
    } else {
      Serial.println();
      Serial.print("Verbindung zu ");
      Serial.println(ssidList[i]);
      Serial.println(" fehlgeschlagen.");
    }
  }
  if (!connected) {
    Serial.println("Keine bekannte Verbindung verfügbar.");
  }
}

// mDNS einrichten, damit der ESP unter "esp32cam.local" erreichbar ist
void setupMDNS() {
  if (!MDNS.begin("esp32cam")) {
    Serial.println("Fehler beim Starten von mDNS");
  } else {
    Serial.println("mDNS gestartet, erreichbar unter: esp32cam.local");
  }
}

// MQTT-Callback: Befehle verarbeiten
void mqttCallback(char* topic, byte* payload, unsigned int length) {
  String message;
  for (unsigned int i = 0; i < length; i++) {
    message += (char)payload[i];
  }
  Serial.print("MQTT-Befehl empfangen: ");
  Serial.println(message);
  
  if (message == "activate_esp_cam") {
    streamActive = true;
    Serial.println("Stream aktiviert.");
  }
  else if (message == "deactivate_esp_cam") {
    streamActive = false;
    Serial.println("Stream deaktiviert.");
  }
  else if (message == "activate_esp_bright_led") {
    brightLedState = true;
    Serial.println("Bright LED on.");
  }
  else if (message == "deactivate_esp_bright_led") {
    brightLedState = false;
    Serial.println("Bright LED off.");
  }
  else {
    Serial.print("Unbekannter Befehl: ");
    Serial.println(message);
  }
  Serial.print("Aktueller streamActive Status: ");
  Serial.println(streamActive ? "true" : "false");
}

// MQTT-Verbindung herstellen und Reconnect-Logik
void setupMQTT() {
  mqttClient.setServer(mqtt_server, mqtt_port);
  mqttClient.setCallback(mqttCallback);
  
  // Versuche einmalig eine Verbindung herzustellen
  Serial.print("Verbinde mit MQTT...");
  if (mqttClient.connect("ESP32CamClient")) {
    Serial.println("verbunden");
    mqttClient.subscribe(mqtt_topic);
  } else {
    Serial.print("Fehler, rc=");
    Serial.println(mqttClient.state());
    // Hier könntest du entscheiden, ob du weitermachst oder später in loop() neu versuchst.
  }
}

// Webserver-Routen definieren
void startCameraServer() {
  // Root: Zeige entweder den Stream oder eine Standby-Seite
  server.on("/", HTTP_GET, [](){
    if (streamActive) {
      server.send(200, "text/html",
        "<html>\
           <head><title>ESP32-CAM Stream</title></head>\
           <body>\
             <h1>ESP32-CAM Live Stream</h1>\
             <img src=\"/stream\" style=\"width:100%;\"/>\
           </body>\
         </html>");
    } else {
      server.send(200, "text/html",
        "<html>\
           <head><title>Standby</title></head>\
           <body>\
             <h1>Kamera im Standby-Modus</h1>\
             <p>Aktivieren Sie den Stream per MQTT-Befehl.</p>\
           </body>\
         </html>");
    }
  });

  // Stream-Endpunkt: Liefert den MJPEG-Stream, wenn aktiviert
  server.on("/stream", HTTP_GET, [](){
    if (!streamActive) {
      server.send(403, "text/plain", "Stream nicht aktiv");
      return;
    }
    WiFiClient client = server.client();
    String response = "HTTP/1.1 200 OK\r\n";
    response += "Content-Type: multipart/x-mixed-replace; boundary=frame\r\n\r\n";
    server.sendContent(response);

    while (streamActive && client.connected()) {
      camera_fb_t * fb = esp_camera_fb_get();
      if (!fb) {
        Serial.println("Kameracapture fehlgeschlagen");
        break;
      }
      response = "--frame\r\n";
      response += "Content-Type: image/jpeg\r\n\r\n";
      server.sendContent(response);
      client.write(fb->buf, fb->len);
      server.sendContent("\r\n");
      esp_camera_fb_return(fb);
      delay(30);
    }
  });
  
  server.begin();
  Serial.println("Webserver gestartet.");
}

//
// Setup-Funktion
//
void setup() {
  Serial.begin(115200);
  Serial.setDebugOutput(true);
  Serial.println();

  // LED-Pins konfigurieren
  pinMode(LED_PIN, OUTPUT);
  pinMode(LED_PIN_BRIGHT, OUTPUT);

  // Kamera initialisieren
  Serial.println("Initialisiere Kamera...");
  esp_err_t err = esp_camera_init(&config);
  if (err != ESP_OK) {
    Serial.printf("Kamera-Init fehlgeschlagen mit Fehler 0x%x\n", err);
    // Hier kannst du z.B. einen Neustart einleiten oder in einen Fehler-Standby wechseln.
  }

  // WLAN-Verbindung herstellen über Liste
  connectToWiFi();

  // mDNS initialisieren
  setupMDNS();

  // MQTT einrichten (einmaliger Versuch)
  setupMQTT();

  // Starte den Webserver – dieser wird jetzt unabhängig von der MQTT-Verbindung gestartet
  startCameraServer();
}

//
// Hauptschleife
//
void loop() {
  // Versuche in der Loop-Funktion, die MQTT-Verbindung aufrechtzuerhalten:
  if (!mqttClient.connected()) {
    Serial.println("MQTT-Verbindung verloren, versuche erneut zu verbinden...");
    // Versuche, die Verbindung herzustellen (dies ist nicht blockierend)
    if (mqttClient.connect("ESP32CamClient")) {
      Serial.println("MQTT-Verbindung wiederhergestellt.");
      mqttClient.subscribe(mqtt_topic);
    }
  }
  mqttClient.loop();
  server.handleClient();

  // LED-Steuerung:
  if (streamActive) {
    digitalWrite(LED_PIN, HIGH);
  } else {
    unsigned long currentTime = millis();
    if (currentTime - lastBlinkTime > 500) {
      ledState = !ledState;
      digitalWrite(LED_PIN, ledState ? HIGH : LOW);
      lastBlinkTime = currentTime;
    }
  }
  digitalWrite(LED_PIN_BRIGHT, brightLedState ? HIGH : LOW);

  // Heartbeat-Ausgabe alle 10 Sekunden
  if (millis() - lastStatusPrint > 10000) {
    Serial.print("Heartbeat: streamActive = ");
    Serial.println(streamActive ? "true" : "false");
    lastStatusPrint = millis();
  }
}

