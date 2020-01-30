/*
 * PASC is a firmware to read data from analog to digital converter ADC
 *    and print it in the serial monitor.
 * It supports the ADC pins from: 
 *    Arduino Uno (10 bit)
 *    ADS1115 Differential (16-bit)
 *    ADS1115 Single ended (16-bit)
 *    ADS1015 Differential (12-bit)
 *    ADS1015 Single ended (12-bit)
 *    
 * The libraries Wire and Adafruit_ADS1015.h are required
 * 
 * author: Nils Haentjens < nils.haentjens+inlinino@maine.edu
 * created: June 21, 2016
 * updated: June 23, 2016
 * version: 0.1.6
 *    
 */

/* ------------------------------------------------
 *  Select your electronic board setup
 *  Please comment/uncomment the appropriate line
 *  ----------------------------------------------- */
//#define ARDUINO_UNO
//#define ADS1115_DIFFERENTIAL
//#define ADS1115_SINGLE_ENDED
#define ADS1015_DIFFERENTIAL
//#define ADS1015_SINGLE_ENDED

/* ------------------------------------------------
 *  Select your pins and set number selected
 *    SIN: Single ended
 *    DIF: Differential
 *  Please comment/uncomment the appropriate line
 *  Note: PIN_A4 and PIN_A5 of the Arduino Uno cannot
 *    be used at the same time that the ADS1X15
 *  ----------------------------------------------- */
//#define SIN_A0
//#define SIN_A1
//#define SIN_A2
//#define SIN_A3
//#define SIN_A4
//#define SIN_A5
#define DIF_A01
//#define DIF_A23

/* ------------------------------------------------
 *  Specify the number of pin selected above
 *  Please set the appropriate number between 1 and 6
 *  ----------------------------------------------- */
const int NUMBER_OF_PIN = 1;

/* ------------------------------------------------
 *  From here you should not modify the code
 *  unless you know what you are doing
 *  ----------------------------------------------- */

// Load libraries
#if defined(ADS1115_DIFFERENTIAL) || defined(ADS1115_SINGLE_ENDED) || defined(ADS1015_DIFFERENTIAL) || defined(ADS1015_SINGLE_ENDED)
  #include <Wire.h>
  #include <Adafruit_ADS1015.h>
#endif

// Load appropriate ADS1x15 driver if required
#if defined(ADS1115_DIFFERENTIAL) || defined(ADS1115_SINGLE_ENDED)
  Adafruit_ADS1115 ads;  /* Use this for the 16-bit version */
#elif defined(ADS1015_DIFFERENTIAL) || defined(ADS1015_SINGLE_ENDED)
  Adafruit_ADS1015 ads;     /* Use thi for the 12-bit version */
#endif

// Set default configuration
int cfg_delay = 1000;

void setup(void) {
  // Establish Serial connection
  Serial.begin(9600);
  // Wait for serial port to connect (Needed for native USB port only)
  while (!Serial) {
    delay(10);
  }
  // Display software information
    Serial.print("Inlinino v0.1.6 - ");
#ifdef ARDUINO_UNO
  Serial.println("Arduino Uno");
#elif defined(ADS1115_DIFFERENTIAL) || defined(ADS1115_SINGLE_ENDED)
  Serial.println("ADS1115 - ADC 16 bit");
#elif defined(ADS1015_DIFFERENTIAL) || defined(ADS1015_SINGLE_ENDED)
  Serial.println("ADS1015 - ADC 12 bit");
#endif
//  Serial.println("Units: counts");
//#if defined(ARDUINO_UNO)
//  Serial.println("Mode: Single Ended");
////  Serial.println("A0 A1 A2 A3 A4 A5");
//#elif defined(ADS1015_SINGLE_ENDED) || defined(ADS1115_SINGLE_ENDED)
//  Serial.println("Mode: Single Ended");
////  Serial.println("A0 A1 A2 A3");
//#elif defined(ADS1015_DIFFERENTIAL) || defined(ADS1115_DIFFERENTIAL)
//  Serial.println("Mode: Differential");
////  Serial.println("D01 D23");
//#endif
  // Wait for data from host
  Serial.println("Waiting for host configuration...");
#ifdef ARDUINO_UNO
  Serial.println("sample_rate<int>");
#elif defined(ADS1115_DIFFERENTIAL) || defined(ADS1115_SINGLE_ENDED) || defined(ADS1015_DIFFERENTIAL) || defined(ADS1015_SINGLE_ENDED)
  Serial.println("sample_rate<int>\tgain<int>");
#endif
  while (Serial.available() <= 0) {
    delay(10);
  }
  int sample_rate = Serial.parseInt();
#if defined(ADS1115_DIFFERENTIAL) || defined(ADS1115_SINGLE_ENDED) || defined(ADS1015_DIFFERENTIAL) || defined(ADS1015_SINGLE_ENDED)
  int gain = Serial.parseInt();
#endif

  // Set sample rate
#ifdef ARDUINO_UNO
  // Arduino Uno: threoric maximum of 9600 Hz
  Serial.println(1000 / (20 * NUMBER_OF_PIN));
  if (1 <= sample_rate &&  sample_rate <= 1000 / (20 * NUMBER_OF_PIN) ) {
    // remove conversion delay (2*10 ms) of Arduino Uno from cfg_delay
    cfg_delay = 1000 / sample_rate - 20 * NUMBER_OF_PIN;
#elif defined(ADS1115_DIFFERENTIAL) || defined(ADS1115_SINGLE_ENDED)
  // ADS1115: 8 to 860 Hz
  if (1 <= sample_rate &&  sample_rate <= 1000 / (8 * NUMBER_OF_PIN)) {
    // remove conversion delay (1x8 ms) of ADS1115 from cfg_delay
    cfg_delay = 1000 / sample_rate - 8 * NUMBER_OF_PIN;
#elif defined(ADS1015_DIFFERENTIAL) || defined(ADS1015_SINGLE_ENDED)
  // ADS1015: 128 to 3300 Hz
  if (1 <= sample_rate &&  sample_rate <= 1000 / (1 * NUMBER_OF_PIN)) {
    // remove conversion delay (1x1 ms) of ADS1015 from cfg_delay
    cfg_delay = 1000 / sample_rate - 1 * NUMBER_OF_PIN;
#endif
  } else {
    cfg_delay = 1000;
    Serial.println("ERROR: Sample rate out of bound");
  }

#if defined(ADS1115_DIFFERENTIAL) || defined(ADS1115_SINGLE_ENDED) || defined(ADS1015_DIFFERENTIAL) || defined(ADS1015_SINGLE_ENDED)
  // Set Gain of ADS-1X15
  // The ADC input range (or gain) can be changed via the following
  // functions, but be careful never to exceed VDD +0.3V max, or to
  // exceed the upper and lower limits if you adjust the input range!
  // Setting these values incorrectly may destroy your ADC!
  //                                                                ADS1015  ADS1115
  //                                                                -------  -------
  switch (gain) {
    case 23:
      ads.setGain(GAIN_TWOTHIRDS);  // 2/3x gain +/- 6.144V  1 bit = 3mV      0.1875mV (default)
      break;
    case 1:
      ads.setGain(GAIN_ONE);        // 1x gain   +/- 4.096V  1 bit = 2mV      0.125mV
      break;
    case 2:
      ads.setGain(GAIN_TWO);        // 2x gain   +/- 2.048V  1 bit = 1mV      0.0625mV
      break;
    case 4:
      ads.setGain(GAIN_FOUR);       // 4x gain   +/- 1.024V  1 bit = 0.5mV    0.03125mV
      break;
    case 8:
      ads.setGain(GAIN_EIGHT);      // 8x gain   +/- 0.512V  1 bit = 0.25mV   0.015625mV
      break;
    case 16:
      ads.setGain(GAIN_SIXTEEN);    // 16x gain  +/- 0.256V  1 bit = 0.125mV  0.0078125mV
      break;
    default:
      Serial.println("ERROR: Unknow gain setting");
      Serial.println("  leaving default gain (2/3x gain +/- 6.144V)");
    break;
  }
#endif

  // Display configuration
//  Serial.print("Delay: "); Serial.print(cfg_delay); Serial.println(" ms");
//#if defined(ADS1115_DIFFERENTIAL) || defined(ADS1115_SINGLE_ENDED) || defined(ADS1015_DIFFERENTIAL) || defined(ADS1015_SINGLE_ENDED)
//  if (gain == 23) {
//    Serial.println("Gain: 2/3");
//  } else {
//    Serial.print("Gain: "); Serial.println(gain);
//  }
//#endif

#if defined(ADS1115_DIFFERENTIAL) || defined(ADS1115_SINGLE_ENDED) || defined(ADS1015_DIFFERENTIAL) || defined(ADS1015_SINGLE_ENDED)
  // Start ads
  ads.begin();
#endif
}

void loop(void) {
#if defined(ARDUINO_UNO)
  // Arduino Uno Single Ended Pins
  // Read data from analog pin twice with small delay after each read
  // because ADC multiplexer needs time to switch and voltage need time to stabilize
  #ifdef SIN_A0
    int adc0 = analogRead(A0); delay(10); adc0 = analogRead(A0); delay(10);
  #endif
  #ifdef SIN_A1
    int adc1 = analogRead(A1); delay(10); adc1 = analogRead(A1); delay(10);
  #endif
  #ifdef SIN_A2
    int adc2 = analogRead(A2); delay(10); adc2 = analogRead(A2); delay(10);
  #endif
  #ifdef SIN_A3
    int adc3 = analogRead(A3); delay(10); adc3 = analogRead(A3); delay(10);
  #endif
  #ifdef SIN_A4
    int adc4 = analogRead(A4); delay(10); adc4 = analogRead(A4); delay(10);
  #endif
  #ifdef SIN_A5
    int adc5 = analogRead(A5); delay(10); adc5 = analogRead(A5); delay(10);
  #endif
  
  #if defined(SIN_A0) && (defined(SIN_A1) || defined(SIN_A2) || defined(SIN_A3) || defined(SIN_A4) || defined(SIN_A5)) 
    Serial.print(adc0); Serial.print("\t");
  #elif defined(SIN_A0) && not (defined(SIN_A1) && defined(SIN_A2) && defined(SIN_A3) && defined(SIN_A4) && defined(SIN_A5)) 
    Serial.println(adc0);
  #endif
  #if defined(SIN_A1) && (defined(SIN_A2) || defined(SIN_A3) || defined(SIN_A4) || defined(SIN_A5)) 
    Serial.print(adc1); Serial.print("\t");
  #elif defined(SIN_A1) && not (defined(SIN_A2) && defined(SIN_A3) && defined(SIN_A4) && defined(SIN_A5)) 
    Serial.println(adc1);
  #endif
  #if defined(SIN_A2) && (defined(SIN_A3) || defined(SIN_A4) || defined(SIN_A5)) 
    Serial.print(adc2); Serial.print("\t");
  #elif defined(SIN_A2) && not (defined(SIN_A3) && defined(SIN_A4) && defined(SIN_A5)) 
    Serial.println(adc2);
  #endif
  #if defined(SIN_A3) && (defined(SIN_A4) || defined(SIN_A5)) 
    Serial.print(adc3); Serial.print("\t");
  #elif defined(SIN_A3) && not (defined(SIN_A4) && defined(SIN_A5)) 
    Serial.println(adc3);
  #endif
  #if defined(SIN_A4) && defined(SIN_A5)
    Serial.print(adc4); Serial.print("\t");
  #elif defined(SIN_A4) && not defined(SIN_A5)
    Serial.println(adc4);
  #endif
  #ifdef SIN_A5
    Serial.println(adc5);
  #endif
#elif defined(ADS1015_SINGLE_ENDED) || defined(ADS1115_SINGLE_ENDED)
  // Single Ended reading (conversion delay included in Adafruit_ADS1015 library)
  #ifdef SIN_A0
    int16_t adc0 = ads.readADC_SingleEnded(0);
  #endif
  #ifdef SIN_A1
    int16_t adc1 = ads.readADC_SingleEnded(1);
  #endif
  #ifdef SIN_A2
    int16_t adc2 = ads.readADC_SingleEnded(2);
  #endif
  #ifdef SIN_A3
    int16_t adc3 = ads.readADC_SingleEnded(3);
  #endif
  #if defined(SIN_A0) && (defined(SIN_A1) || defined(SIN_A2) || defined(SIN_A3)) 
    Serial.print(adc0); Serial.print("\t");
  #elif defined(SIN_A0) && not (defined(SIN_A1) && defined(SIN_A2) && defined(SIN_A3)) 
    Serial.println(adc0);
  #endif
  #if defined(SIN_A1) && (defined(SIN_A2) || defined(SIN_A3)) 
    Serial.print(adc1); Serial.print("\t");
  #elif defined(SIN_A1) && not (defined(SIN_A2) && defined(SIN_A3)) 
    Serial.println(adc1);
  #endif
  #if defined(SIN_A2) && defined(SIN_A3)
    Serial.print(adc2); Serial.print("\t");
  #elif defined(SIN_A2) && not defined(SIN_A3)
    Serial.println(adc2);
  #endif
  #ifdef SIN_A3
    Serial.println(adc3);
  #endif
#elif defined(ADS1015_DIFFERENTIAL) || defined(ADS1115_DIFFERENTIAL)
  // Differential reading (conversion delay included in Adafruit_ADS1015 library)
  #ifdef DIF_A01
    int16_t adc01 = ads.readADC_Differential_0_1();
  #endif
  #ifdef DIF_A23
    int16_t adc23 = ads.readADC_Differential_2_3();
  #endif
  #if defined(DIF_A01) && defined(DIF_A23)
    Serial.print(adc01); Serial.print("\t");
  #elif defined(DIF_A01) && not defined(DIF_A23)
    Serial.println(adc01);
  #endif
  #if defined(DIF_A23)
    Serial.println(adc23);
  #endif
#endif

  delay(cfg_delay); // milliseconds
}
