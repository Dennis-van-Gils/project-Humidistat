/*******************************************************************************
  Humidistat v1

  Hardware & pin out
  ------------------

  Adafruit Feather M4 Express
    Sensors:
    - BME280 #1, I2C address 0x76
    - BME280 #2, I2C address 0x77
    Actuators:
    - solenoid valve #1    , via solid-state relay on pin D12
    - solenoid valve #2    , via solid-state relay on pin D5
    - external 220 VAC pump, via solid-state relay on pin D13

  The RGB LED of the Feather M4 will indicate its status:
    - Blue : We're setting up
    - Green: All okay and idling
  Every read out, the LED will flash brightly turquoise.

  https://github.com/Dennis-van-Gils/project-Humidistat
  Dennis van Gils
  22-01-2022
*******************************************************************************/

#include <Arduino.h>
#include <SPI.h>
#include <Wire.h>

#include "Adafruit_BME280.h"
#include "Adafruit_NeoPixel.h"
#include "Adafruit_Sensor.h"
#include "DvG_SerialCommand.h"

// Pin assignments for actuators
#define PIN_VALVE_1 12
#define PIN_VALVE_2 5
#define PIN_PUMP 13

// BME280: Temperature, humidity and pressure sensors
#define DAQ_PERIOD 1000 // [ms] Data-acquisition period, 1 sec at minimum
Adafruit_BME280 bme_1;
Adafruit_BME280 bme_2;

// On-board NeoPixel RGB LED
#define NEO_DIM 3    // Brightness level for dim intensity [0 -255]
#define NEO_BRIGHT 6 // Brightness level for bright intensity [0 - 255]
#define NEO_FLASH_DURATION 100 // [ms]
bool neo_flash = false;
uint32_t t_neo_flash = 0;
Adafruit_NeoPixel neo(1, PIN_NEOPIXEL, NEO_GRB + NEO_KHZ800);

// Serial command listener
DvG_SerialCommand sc(Serial);

// -----------------------------------------------------------------------------
//  State control
// -----------------------------------------------------------------------------

struct State {
  /* Holds actual actuator states and sensor readings
   */
  bool valve_1 = false;
  bool valve_2 = false;
  bool pump = false;
  float temp_1 = NAN; // ['C]
  float temp_2 = NAN; // ['C]
  float humi_1 = NAN; // [% RH]
  float humi_2 = NAN; // [% RH]
  float pres_1 = NAN; // [Pa]
  float pres_2 = NAN; // [Pa]
};
State state;

struct Request {
  /* Holds requested actuator states
   */
  bool valve_1 = false;
  bool valve_2 = false;
  bool pump = false;
};
Request request;

void update_actuators() {
  /* Grants the requested actuator states
   */
  if (request.valve_1 != state.valve_1) {
    state.valve_1 = request.valve_1;
    digitalWrite(PIN_VALVE_1, state.valve_1);
  }
  if (request.valve_2 != state.valve_2) {
    state.valve_2 = request.valve_2;
    digitalWrite(PIN_VALVE_2, state.valve_2);
  }
  if (request.pump != state.pump) {
    state.pump = request.pump;
    digitalWrite(PIN_PUMP, state.pump);
  }
}

void connect_BME280_sensors() {
  uint8_t idx_try;
  bool success;

  for (idx_try = 0; idx_try < 3; idx_try++) {
    success = bme_1.begin(0x76);
    if (success) { break; }
    delay(1000);
  }
  if (!success) { Serial.println("Could not find BME280 sensor #1"); }

  for (idx_try = 0; idx_try < 3; idx_try++) {
    success = bme_2.begin(0x77);
    if (success) { break; }
    delay(1000);
  }
  if (!success) { Serial.println("Could not find BME280 sensor #2"); }
}

void read_BME280_sensors() {
  /* Update the sensor readings and save in `state`
   */
  state.temp_1 = bme_1.readTemperature();
  state.humi_1 = bme_1.readHumidity();
  state.pres_1 = bme_1.readPressure();

  state.temp_2 = bme_2.readTemperature();
  state.humi_2 = bme_2.readHumidity();
  state.pres_2 = bme_2.readPressure();
}

void perform_measurement_and_report(uint32_t now, uint32_t t_0) {
  /* Perform a single measurement and report over serial
   */

  // Set RGB LED to bright turquoise: Performing new measurement
  neo_flash = true;
  t_neo_flash = now;
  neo.setPixelColor(0, neo.Color(0, NEO_BRIGHT, NEO_BRIGHT));
  neo.show();

  read_BME280_sensors();

  Serial.print(now - t_0);
  Serial.write('\t');
  Serial.print(state.valve_1);
  Serial.write('\t');
  Serial.print(state.valve_2);
  Serial.write('\t');
  Serial.print(state.pump);
  Serial.write('\t');
  Serial.print(state.humi_1, 2);
  Serial.write('\t');
  Serial.print(state.humi_2, 2);
  Serial.write('\t');
  Serial.print(state.temp_1, 2);
  Serial.write('\t');
  Serial.print(state.temp_2, 2);
  Serial.write('\t');
  Serial.print(state.pres_1, 0);
  Serial.write('\t');
  Serial.print(state.pres_2, 0);
  Serial.write('\n');
}

bool parseBoolInString(char *strIn, uint8_t iPos) {
  if (strlen(strIn) > iPos) {
    return (bool)atoi(&strIn[iPos]);
  } else {
    return false;
  }
}

// -----------------------------------------------------------------------------
//  setup
// -----------------------------------------------------------------------------

void setup() {
  // Initialize actuators
  pinMode(PIN_VALVE_1, OUTPUT);
  pinMode(PIN_VALVE_2, OUTPUT);
  pinMode(PIN_PUMP, OUTPUT);
  digitalWrite(PIN_VALVE_1, state.valve_1);
  digitalWrite(PIN_VALVE_2, state.valve_2);
  digitalWrite(PIN_PUMP, state.pump);

  // Set RGB LED to blue: We're setting up
  neo.begin();
  neo.setPixelColor(0, neo.Color(0, 0, NEO_BRIGHT));
  neo.show();

  Serial.begin(9600);

  connect_BME280_sensors();
  read_BME280_sensors(); // Ditch the first reading. Tends to be off.

  // Set RGB LED to dim green: We're all ready to go and idle
  neo.setPixelColor(0, neo.Color(0, NEO_DIM, 0));
  neo.show();
}

// -----------------------------------------------------------------------------
//  loop
// -----------------------------------------------------------------------------

void loop() {
  char *str_cmd; // Incoming serial command string
  static bool reporting_continuously = false;
  uint32_t now = millis();
  static uint32_t t_0 = now;
  static uint32_t tick = now;

  // Short burst control
  const uint32_t T_burst_1 = 500;  // [ms]
  const uint32_t T_burst_2 = 1000; // [ms]
  static bool burst_valve_1 = false;
  static bool burst_valve_2 = false;
  static uint32_t t_burst_valve_1 = 0;
  static uint32_t t_burst_valve_2 = 0;

  // Process incoming serial commands
  if (sc.available()) {
    str_cmd = sc.getCmd();

    if (strcmp(str_cmd, "id?") == 0) {
      Serial.println("Arduino, Humidistat v1");

    } else if (strcmp(str_cmd, "b1") == 0) {
      // Turn valve 1 & pump on for a short fixed duration, aka 'burst'
      burst_valve_1 = true;
      t_burst_valve_1 = now;
      request.valve_1 = true;
      request.pump = true;
      update_actuators();

    } else if (strcmp(str_cmd, "b2") == 0) {
      // Turn valve 2 & pump on for a short fixed duration, aka 'burst'
      burst_valve_2 = true;
      t_burst_valve_2 = now;
      request.valve_2 = true;
      request.pump = true;
      update_actuators();

    } else if (strncmp(str_cmd, "v1", 2) == 0) {
      // Turn valve 1 on/off
      request.valve_1 = parseBoolInString(str_cmd, 2);
      update_actuators();

    } else if (strncmp(str_cmd, "v2", 2) == 0) {
      // Turn valve 2 on/off
      request.valve_2 = parseBoolInString(str_cmd, 2);
      update_actuators();

    } else if (strncmp(str_cmd, "p", 1) == 0) {
      // Turn pump on/off
      request.pump = parseBoolInString(str_cmd, 1);
      update_actuators();

    } else if (strcmp(str_cmd, "r") == 0) {
      // Try to reconnect to BME280's
      connect_BME280_sensors();

    } else if (strcmp(str_cmd, "c") == 0) {
      // Continuously perform measurements and report over serial
      reporting_continuously = !reporting_continuously;

    } else if (strcmp(str_cmd, "?") == 0) {
      // Perform a single measurement and report over serial
      reporting_continuously = false;
      perform_measurement_and_report(now, t_0);
    }
  }

  // Burst control
  if (burst_valve_1 && (now - t_burst_valve_1 > T_burst_1)) {
    burst_valve_1 = false;
    request.valve_1 = false;
    request.pump = false;
    update_actuators();
  }

  if (burst_valve_2 && (now - t_burst_valve_2 > T_burst_2)) {
    burst_valve_2 = false;
    request.valve_2 = false;
    request.pump = false;
    update_actuators();
  }

  // DAQ
  if (now - tick >= DAQ_PERIOD) {
    tick += DAQ_PERIOD; // Strict-interval time keeping
    if (reporting_continuously) { perform_measurement_and_report(now, t_0); }
  }

  // Set RGB LED back to dim green: Measurement is done
  if (neo_flash && (now - t_neo_flash >= NEO_FLASH_DURATION)) {
    neo_flash = false;
    neo.setPixelColor(0, neo.Color(0, NEO_DIM, 0));
    neo.show();
  }
}
