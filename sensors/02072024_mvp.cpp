#include <WiFi.h>
#include <HTTPClient.h>
#include <EEPROM.h>
#include <Wire.h>
#include <ArduinoJson.h>
#include <DHT.h>
#include <WebServer.h>
#include <NTPClient.h>  // Include NTPClient library
#include <WiFiUdp.h>    // Include WiFiUdp library for NTP

#define DHTPIN 4
#define DHTTYPE DHT22
DHT dht(DHTPIN, DHTTYPE);

#define LED_PIN 2 // Built-in LED for visual feedback
#define RESET_BUTTON_PIN 5
#define EEPROM_SIZE 512

const char* ssid = "EVOS";
const char* password = "evos02122020";

const char* apiEndpoint = "https://windevs.uz/sensors/api/sensor-data/";
const char* tokenEndpoint = "https://windevs.uz/sensors/api/token/";
const char* refreshEndpoint = "https://windevs.uz/sensors/api/token/refresh/";
const char* basicAuthUsername = "bekhzad";
const char* basicAuthPassword = "admin";

String jwtToken;
String refreshTokenString;
unsigned long tokenExpiryTime = 0;

WebServer server(80);

unsigned long startTime;

WiFiUDP ntpUDP;
NTPClient timeClient(ntpUDP, "pool.ntp.org");

void setup() {
  Serial.begin(115200);
  pinMode(LED_PIN, OUTPUT);
  pinMode(RESET_BUTTON_PIN, INPUT_PULLUP);
  EEPROM.begin(EEPROM_SIZE);
  dht.begin();
  
  connectToWiFi();
  startWebServer();
  
  // Initialize NTP client
  timeClient.begin();
  
  // Obtain initial tokens
  if (!obtainTokens()) {
    Serial.println("Failed to obtain initial tokens");
    return;
  }
  
  printSystemInfo(); // Print system information at startup
}

void loop() {
  timeClient.update(); // Update NTP client to fetch time
  delay(2000);
  
  float h = dht.readHumidity();
  float t = dht.readTemperature();
  float f = dht.readTemperature(true);

  if (isnan(h) || isnan(t) || isnan(f)) {
    Serial.println(F("Failed to read from DHT sensor!"));
    return;
  }

  float hif = dht.computeHeatIndex(f, h);
  float hic = dht.computeHeatIndex(t, h, false);

  unsigned long currentTime = millis();
  unsigned long uptime = (currentTime - startTime) / 1000; // Uptime in seconds
  String formattedUptime = formatUptime(uptime);
  String timestamp = getTimestamp();

  Serial.println("Sensor Readings:");
  Serial.print("Humidity: ");
  Serial.print(h);
  Serial.println("%");
  Serial.print("Temperature (C): ");
  Serial.print(t);
  Serial.println("°C");
  Serial.print("Temperature (F): ");
  Serial.print(f);
  Serial.println("°F");
  Serial.print("Heat Index (C): ");
  Serial.print(hic);
  Serial.println("°C");
  Serial.print("Heat Index (F): ");
  Serial.print(hif);
  Serial.println("°F");

  sendDataToAPI(h, t, f, hic, hif, uptime, timestamp); // Pass uptime as unsigned long
  parseSerialCommand();
  provideVisualFeedback();
  checkResetButton();
  // Rotate tokens if expired
  if (millis() > tokenExpiryTime) {
    if (!refreshToken()) {
      Serial.println("Failed to refresh token");
      return;
    }
  }

  server.handleClient();
}

void connectToWiFi() {
  Serial.print("Connecting to WiFi ");
  Serial.println(ssid);
  
  WiFi.begin(ssid, password);
  
  while (WiFi.status() != WL_CONNECTED) {
    delay(1000);
    Serial.print(".");
  }
  
  Serial.println("");
  Serial.println("WiFi connected.");
  Serial.println("IP address: ");
  Serial.println(WiFi.localIP());
}

void startWebServer() {
  server.on("/", HTTP_GET, []() {
    if (!server.authenticate(basicAuthUsername, basicAuthPassword)) {
      return server.requestAuthentication();
    }
    
    String message = "<html><body>";
    message += "<h1>Sensor Data</h1>";
    message += "<p>Humidity: " + String(dht.readHumidity()) + "%</p>";
    message += "<p>Temperature (C): " + String(dht.readTemperature()) + "°C</p>";
    message += "<p>Temperature (F): " + String(dht.readTemperature(true)) + "°F</p>";
    message += "<p>Heat Index (C): " + String(dht.computeHeatIndex(dht.readTemperature(), dht.readHumidity(), false)) + "°C</p>";
    message += "<p>Heat Index (F): " + String(dht.computeHeatIndex(dht.readTemperature(true), dht.readHumidity())) + "°F</p>";
    message += "<p>Uptime: " + formatUptime((millis() - startTime) / 1000) + "</p>";
    message += "</body></html>";
    
    server.send(200, "text/html", message);
  });

  server.on("/config", HTTP_GET, []() {
    if (!server.authenticate(basicAuthUsername, basicAuthPassword)) {
      return server.requestAuthentication();
    }
    
    String message = "<html><body>";
    message += "<h1>Configure WiFi</h1>";
    message += "<form action='/config' method='post'>";
    message += "SSID: <input type='text' name='ssid'><br>";
    message += "Password: <input type='password' name='password'><br>";
    message += "<input type='submit' value='Save'>";
    message += "</form></body></html>";
    
    server.send(200, "text/html", message);
  });

  server.on("/config", HTTP_POST, []() {
    if (!server.authenticate(basicAuthUsername, basicAuthPassword)) {
      return server.requestAuthentication();
    }
    
    if (server.hasArg("ssid") && server.hasArg("password")) {
      String newSSID = server.arg("ssid");
      String newPassword = server.arg("password");
      storeWiFiConfig(newSSID.c_str(), newPassword.c_str());
      server.send(200, "text/html", "<html><body><h1>Configuration Saved!</h1></body></html>");
      delay(1000);
      ESP.restart();
    } else {
      server.send(400, "text/html", "<html><body><h1>Missing SSID or Password!</h1></body></html>");
    }
  });

  server.begin();
}

void sendDataToAPI(float humidity, float tempC, float tempF, float heatIndexC, float heatIndexF, unsigned long uptime, String timestamp) {
  if (WiFi.status() == WL_CONNECTED) {
    HTTPClient http;
    http.begin(apiEndpoint);
    http.addHeader("Content-Type", "application/json");
    http.addHeader("Authorization", "Bearer " + jwtToken);

    DynamicJsonDocument doc(256);
    doc["sensor_id"] = generateSensorID();
    doc["humidity"] = humidity;
    doc["temperature"] = tempC; // Ensure correct field names
    doc["heat_index"] = heatIndexC; // Ensure correct field names
    doc["uptime"] = uptime;
    doc["datetime"] = timestamp;

    String payload;
    serializeJson(doc, payload);

    Serial.println("Sending data to API:");
    Serial.println(payload);

    int httpResponseCode = http.POST(payload);

    if (httpResponseCode == 401) { // Unauthorized
      if (refreshToken()) {
        http.addHeader("Authorization", "Bearer " + jwtToken);
        httpResponseCode = http.POST(payload);
      }
    }

    if (httpResponseCode > 0) {
      String response = http.getString();
      Serial.println("HTTP Response Code:");
      Serial.println(httpResponseCode);
      Serial.println("Response:");
      Serial.println(response);
    } else {
      Serial.print("Error on sending POST: ");
      Serial.println(httpResponseCode);
    }

    http.end();
  }
}

String generateSensorID() {
  return WiFi.macAddress();
}


void provideVisualFeedback() {
  digitalWrite(LED_PIN, HIGH);
  delay(500);
  digitalWrite(LED_PIN, LOW);
  delay(100);
}

void checkResetButton() {
  static unsigned long buttonPressStartTime = 0;
  static bool buttonPressDetected = false;
  const unsigned long resetButtonPressDuration = 3000; // 3 seconds

  if (digitalRead(RESET_BUTTON_PIN) == LOW) { // Button pressed (assuming active low)
    if (!buttonPressDetected) { // First detection of button press
      buttonPressStartTime = millis();
      buttonPressDetected = true;
    }

    if (millis() - buttonPressStartTime >= resetButtonPressDuration) {
      Serial.println("Reset button pressed for 3 seconds. Resetting WiFi configurations...");
      clearWiFiConfig();
      delay(1000);
      ESP.restart(); // Restart ESP8266
    }
  } else { // Button not pressed
    buttonPressDetected = false; // Reset button press detection
  }
}

void clearWiFiConfig() {
  // Clear stored WiFi credentials in EEPROM
  writeStringToEEPROM(0, "");
  writeStringToEEPROM(50, "");
}
void writeStringToEEPROM(int addr, String data) {
  EEPROM.begin(EEPROM_SIZE);
  for (unsigned int i = 0; i < data.length(); i++) {
    EEPROM.write(addr + i, data[i]);
  }
  EEPROM.commit();
  EEPROM.end();
}

void storeWiFiConfig(const char* ssid, const char* password) {
  writeStringToEEPROM(0, String(ssid));
  writeStringToEEPROM(50, String(password));
}

void readWiFiConfig(char* ssid, char* password) {
  String storedSSID = readStringFromEEPROM(0);
  String storedPassword = readStringFromEEPROM(50);
  storedSSID.toCharArray(ssid, storedSSID.length() + 1);
  storedPassword.toCharArray(password, storedPassword.length() + 1);
}

String readStringFromEEPROM(int addr) {
  EEPROM.begin(EEPROM_SIZE);
  String data;
  char character;
  for (unsigned int i = 0; i < 50; i++) {
    character = EEPROM.read(addr + i);
    if (character == 0) {
      break;
    }
    data.concat(character);
  }
  EEPROM.end();
  return data;
}

void printSystemInfo() {
  Serial.println("System Information:");
  Serial.print("SSID: ");
  Serial.println(ssid);
  Serial.print("IP Address: ");
  Serial.println(WiFi.localIP());
  Serial.print("MAC Address: ");
  Serial.println(WiFi.macAddress());
  Serial.print("Token Expiry Time (ms): ");
  Serial.println(tokenExpiryTime);
}

bool obtainTokens() {
  if (WiFi.status() == WL_CONNECTED) {
    HTTPClient http;
    http.begin(tokenEndpoint);
    http.addHeader("Content-Type", "application/json");

    DynamicJsonDocument doc(256);
    doc["username"] = basicAuthUsername;  // Replace with your actual username
    doc["password"] = basicAuthUsername;  // Replace with your actual password

    String payload;
    serializeJson(doc, payload);

    int httpResponseCode = http.POST(payload);

    if (httpResponseCode == 200) {
      String response = http.getString();
      DynamicJsonDocument responseDoc(512);
      deserializeJson(responseDoc, response);
      jwtToken = responseDoc["access"].as<String>();
      refreshTokenString = responseDoc["refresh"].as<String>();
      tokenExpiryTime = millis() + 300000; // Set token expiry time to 5 minutes from now
      http.end();
      return true;
    } else {
      Serial.print("Error on obtaining tokens: ");
      Serial.println(httpResponseCode);
    }

    http.end();
  }
  return false;
}

bool refreshToken() {
  if (WiFi.status() == WL_CONNECTED) {
    HTTPClient http;
    http.begin(refreshEndpoint);
    http.addHeader("Content-Type", "application/json");

    DynamicJsonDocument doc(256);
    doc["refresh"] = refreshTokenString;

    String payload;
    serializeJson(doc, payload);

    int httpResponseCode = http.POST(payload);

    if (httpResponseCode == 200) {
      String response = http.getString();
      DynamicJsonDocument responseDoc(512);
      deserializeJson(responseDoc, response);
      jwtToken = responseDoc["access"].as<String>();
      refreshTokenString = responseDoc["refresh"].as<String>();
      tokenExpiryTime = millis() + 300000; // Set token expiry time to 5 minutes from now
      http.end();
      return true;
    } else {
      Serial.print("Error on refreshing token: ");
      Serial.println(httpResponseCode);
    }

    http.end();
  }
  return false;
}

String formatUptime(unsigned long uptimeSeconds) {
  unsigned long days = uptimeSeconds / 86400;
  unsigned long hours = (uptimeSeconds % 86400) / 3600;
  unsigned long minutes = (uptimeSeconds % 3600) / 60;
  unsigned long seconds = uptimeSeconds % 60;

  String formattedUptime = String(days) + "d " + String(hours) + "h " + String(minutes) + "m " + String(seconds) + "s";
  return formattedUptime;
}

String getTimestamp() {
  time_t now = timeClient.getEpochTime();
  struct tm* tmstruct = localtime(&now);

  char timestamp[20];
  sprintf(timestamp, "%04d-%02d-%02d %02d:%02d:%02d",
          tmstruct->tm_year + 1900,
          tmstruct->tm_mon + 1,
          tmstruct->tm_mday,
          tmstruct->tm_hour,
          tmstruct->tm_min,
          tmstruct->tm_sec);
  return String(timestamp);
}


void parseSerialCommand() {
  if (Serial.available() > 0) {
    String command = Serial.readStringUntil('\n');
    command.trim();
    command.toLowerCase();  // Make command case-insensitive

    if (command.startsWith("ssid ")) {
      int spaceIndex = command.indexOf(' ');
      if (spaceIndex != -1 && command.length() > spaceIndex + 1) {
        String ssid = command.substring(spaceIndex + 1);
        storeWiFiConfig(ssid.c_str(), EEPROM.readString(32).c_str());
        Serial.println("SSID updated. Restarting...");
        ESP.restart();
      } else {
        Serial.println("Error: SSID cannot be empty.");
      }
    } else if (command.startsWith("password ")) {
      int spaceIndex = command.indexOf(' ');
      if (spaceIndex != -1 && command.length() > spaceIndex + 1) {
        String password = command.substring(spaceIndex + 1);
        storeWiFiConfig(EEPROM.readString(0).c_str(), password.c_str());
        Serial.println("Password updated. Restarting...");
        ESP.restart();
      } else {
        Serial.println("Error: Password cannot be empty.");
      }
    } else if (command.equals("help")) {
      Serial.println("Available commands:");
      Serial.println("  ssid <your_ssid>      - Set the WiFi SSID");
      Serial.println("  password <your_password> - Set the WiFi password");
      Serial.println("  help                  - Show this help message");
    } else {
      Serial.println("Unknown command. Type 'help' for a list of commands.");
    }
  }
}


