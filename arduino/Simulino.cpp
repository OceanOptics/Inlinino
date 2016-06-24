/*
 * SIMULINO is a library to simulate scientific instruments
 * 
 * Instruments available:
 *  ECO-BB3 sn:349, 499
 *  ECO-BB9 sn:279
 *  
 *  Note: values of sensors are constant
 *    time returned by instrument is constant
 * 
 * author: Nils Haentjens < nils.haentjens+inlinino@maine.edu
 * created: June 23, 2016
 * updated: June 23, 2016
 * version: 0.1.3
 *    
 */

/* ------------------------------------------------
 *  Select instrument to simulate
 *  Please comment/uncomment the appropriate line
 *  ----------------------------------------------- */
//#define BB3_349
//#define BB3_499
#define BB9_279

/* ------------------------------------------------
 *  Select set of value
 *    dark: no scattering (min)
 *    drop5: 5 drops of scattering solution (some)
 *    drop40: instrument sensor is saturated (max)
 *    increment: instrument counts are incremented
 *  Please comment/uncomment the appropriate line
 *  ----------------------------------------------- */
//#define DARK
//#define DROP5
//#define DROP40
#define INCREMENT

/* ------------------------------------------------
 *  From here you should not modify the code
 *  unless you know what you are doing
 *  ----------------------------------------------- */

int i = 0;

void setup() {
  // Initialize serial communication (same for all instruments)
  //    baudrate: 19200
  //    bytesize: 8
  //    parity: N
  //    stop bits: 1
  Serial.begin(19200, SERIAL_8N1);
  
  // Wait for serial port to connect (Needed for native USB port only)
  while (!Serial) {
    delay(10);
  }
  
  // Display instrument header information
#ifdef BB9_279
  Serial.println("Persistor CF1 SN:51959   BIOS:4.2   PicoDOS:4.2");
  Serial.println("");
  Serial.println("BB9 S/N 279 v1.03 Compiled on Mar 15 2006 at 17:42:58");
  Serial.println("");
#endif
}

// the loop routine runs over and over again forever:
void loop() {
#if defined(BB3_349)
  #ifdef DARK
    Serial.println("05/10/16\t18:06:23\t470\t55\t532\t57\t660\t57\t537");
  #elif defined(DROP5)
    Serial.println("05/10/16\t18:42:27\t470\t683\t532\t970\t660\t912\t542");
  #elif defined(DROP40)
    Serial.println("05/10/16\t19:00:32\t470\t4071\t532\t4123\t660\t4118\t542");
  #elif defined(INCREMENT)
    Serial.print("05/10/16\t19:00:32\t470\t");
    Serial.print(i);
    Serial.print("\t532\t");
    Serial.print(i + 10 % 4096);
    Serial.print("\t660\t");
    Serial.print(i + 20 % 4096);
    Serial.println("\t542");
    i = (i + 1) % 4096;
  #endif
#elif defined(BB3_499)
  #ifdef DARK
    Serial.println("01/01/00\t00:00:08\t470\t50\t532\t49\t595\t42\t550");
  #elif defined(DROP5)
    Serial.println("01/01/00\t00:00:20\t470\t584\t532\t784\t595\t1365\t547");
  #elif defined(DROP40)
    Serial.println("01/01/00\t00:00:22\t470\t3857\t532\t4097\t595\t4124\t547");
  #elif defined(INCREMENT)
    Serial.print("01/01/00\t00:00:22\t470\t");
    Serial.print(i);
    Serial.print("\t532\t");
    Serial.print(i + 10 % 4096);
    Serial.print("\t595\t");
    Serial.print(i + 20 % 4096);
    Serial.println("\t547");
    i = (i + 1) % 4096;
  #endif
#elif defined(BB9_279)
  #ifdef DARK
    // Dark
    Serial.println("WETA_BB90279\t21\t1\t10\t412\t63\t440\t58\t488\t55\t510\t44\t532\t57\t595\t58\t660\t75\t676\t54\t715\t53\t0e1a");
  #elif defined(DROP5)
    if ( i == 0 ) {
      // Red 5
      Serial.println("WETA_BB90279\t21\t1\t1\t412\t360\t440\t725\t488\t506\t510\t661\t532\t616\t595\t797\t660\t1022\t676\t900\t715\t940\t0fda");
    } else if ( i == 1 ) {
      // Green 5
      Serial.println("WETA_BB90279\t21\t1\t5\t412\t250\t440\t657\t488\t513\t510\t680\t532\t617\t595\t817\t660\t1338\t676\t934\t715\t933\t0fec");
    } else if ( i == 2 ) { 
      // Blue 5
      Serial.println("WETA_BB90279\t21\t1\t9\t412\t252\t440\t594\t488\t519\t510\t664\t532\t621\t595\t773\t660\t1034\t676\t895\t715\t1001\t1018");
    }
    i = (i + 1) % 3;
  #elif defined(DROP40)
    if ( i == 0 ) {
      // Red 40
      Serial.println("WETA_BB90279\t21\t1\t14\t412\t1502\t440\t3598\t488\t3302\t510\t4120\t532\t4120\t595\t4120\t660\t4120\t676\t4120\t715\t4120\t1173");
    } else if ( i == 1 ) {
      // Green 40
      Serial.println("WETA_BB90279\t21\t1\t18\t412\t1482\t440\t3659\t488\t3292\t510\t4120\t532\t4120\t595\t4120\t660\t4120\t676\t4120\t715\t4120\t1184");
    } else if ( i == 2 ) { 
      // Blue 40
      Serial.println("WETA_BB90279\t21\t1\t12\t412\t1565\t440\t3834\t488\t3442\t510\t4120\t532\t4120\t595\t4120\t660\t4120\t676\t4120\t715\t4120\t1178");
    }
    i = (i + 1) % 3;
  #elif defined(INCREMENT)
    Serial.print("WETA_BB90279\t21\t1\t14\t412\t");
    Serial.print(i);
    Serial.print("\t440\t");
    Serial.print(i + 10 % 4096);
    Serial.print("\t488\t");
    Serial.print(i + 20 % 4096);
    Serial.print("\t510\t");
    Serial.print(i + 30 % 4096);
    Serial.print("\t532\t");
    Serial.print(i + 40 % 4096);
    Serial.print("\t595\t");
    Serial.print(i + 50 % 4096);
    Serial.print("\t660\t");
    Serial.print(i + 60 % 4096);
    Serial.print("\t676\t");
    Serial.print(i + 70 % 4096);
    Serial.print("\t715\t");
    Serial.print(i + 80 % 4096);
    Serial.println("\t1173");
    i = (i + 1) % 4096;
  #endif
#endif
  // All instruments run at 1 Hz
  delay(1000);
}
