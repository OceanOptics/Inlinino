/*
   SIMULINO is a library to simulate scientific instruments

   Instruments available:
    ECO-BB3 sn:349, 499
    ECO-BB9 sn:279
    ECO-3X1M sn:005
    ECO-BBFL2 sn:200
    SBE ThermoSalinoGraph

    Note: values of sensors are constant
      time returned by instrument is constant

   author: Nils Haentjens < nils.haentjens+inlinino@maine.edu
   created: June 23, 2016
   updated: April 3, 2017
   version: 0.2.1

*/

/* ------------------------------------------------
    Select instrument to simulate
    Please comment/uncomment the appropriate line
    ----------------------------------------------- */
//#define BB3_349
//#define BB3_499
//#define BB9_279
//#define _3X1M_005
//#define BBFL2_200
//#define BB3_XXX
//#define BB3_TARA
//#define TSG
//#define UBAT_0010
#define BBRT_142R

/* ------------------------------------------------
    Select set of value
      dark: no scattering (min)
      drop5: 5 drops of scattering solution (some)
      drop40: instrument sensor is saturated (max)
      increment: instrument counts are incremented
    Available only for BB3_349, BB3_499, BB9_279
    Please comment/uncomment the appropriate line
    ----------------------------------------------- */
//#define DARK
//#define DROP5
//#define DROP40
//#define INCREMENT

/* ------------------------------------------------
    From here you should not modify the code
    unless you know what you are doing
    ----------------------------------------------- */

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
#elif defined(_3X1M_005)
  if ( i == 0 ) {
    Serial.println("06/24/16\t19:33:04\t440\t1111\t470\t1362\t532\t223\t538");
  } else if ( i == 1 ) {
    Serial.println("06/24/16\t19:33:06\t440\t1104\t470\t1368\t532\t223\t538");
  } else if ( i == 2 ) {
    Serial.println("06/24/16\t19:33:08\t440\t1112\t470\t1385\t532\t227\t538");
  }
  i = (i + 1) % 3;
#elif defined(BBFL2_200)
  if ( i == 0 ) {
    Serial.println("06/24/16\t19:28:07\t660\t247\t695\t735\t460\t91\t8961");
  } else if ( i == 1 ) {
    Serial.println("06/24/16\t19:28:09\t660\t244\t695\t734\t460\t90\t8961");
  } else if ( i == 2 ) {
    Serial.println("06/24/16\t19:28:10\t660\t251\t695\t735\t460\t92\t8961");
  }
  i = (i + 1) % 3;
#elif defined(BB3_XXX)
  Serial.println("06/24/16\t19:28:07\t440\t1247\t550\t935\t660\t791\t8961");
#elif defined(BB3_TARA)
  Serial.println("11/08/16\t20:33:49\t470\t4130\t532\t53\t650\t83\t524");
#elif defined(TSG)
  Serial.println("21.483, 52.433, 33.456");
#elif defined(UBAT_0010)
  if ( i == 0 ) {
    Serial.println("UBAT0010,00118,1.48E7,1.664E+09,1198,11.901,653,0.632,43,1.15,13,19,20,20,19,25,44,42,35,31,31,34,32,27,22,25,33,35,30,59,163,242,243,238,245,259,257,279,380,639,817,819,745,660,588,537,507,465,424,433,410,349,314,282,250,231,218,208,193,178,167,156,141,126,120,118,113,102,83,43");
  } else if ( i == 1 ) {
    Serial.println("UBAT0010,00119,1.48E7,3.290E+09,1205,11.896,650,0.631,43,1.10,15,7,3,4,2,2,3,1,2,9,25,38,42,45,48,48,45,48,50,49,45,40,40,51,62,64,57,56,56,52,52,57,75,89,158,419,684,766,728,627,511,48,40,52,68,116,166,160,127,92,83,89,85,69,53,39,24,14,9,11,24,33,27,20,17,20,26,27,34,54,101,140,159,158,153,148,137,129");
  } else if ( i == 2 ) {
    Serial.println("UBAT0010,00128,1.48E7,1.836E+09,1201,11.892,644,0.631,43,1.11,132,131,120,106,99,100,94,82,72,63,57,58,66,66,55,41,39,45,47,41,34,35,44,64,116,168,192,198,189,176,169,163,157,153,163,188,210,205,191,180,191,193,186,169,149,128,100,61,36,28,21,15,10,7,5,4,5,4,5,6");
  } else if ( i == 3 ) {
    Serial.println("UBAT0010,00129,1.48E7,1.407E+09,1199,11.902,659,0.631,43,1.13,6,8,4,1,3,6,6,5,4,2,2,3,5,3,1,5,5,7,9,11,7,4,3,6,9,8,7,25,111,413,1048,1418,1435,1323,1130,715,301,81,21,11,27,53,57,53,66,80,76,73,80,76,68,70,96,142,172,171,168,175,185,220");
  }
//  } else if ( i == 4 ) {
//    Serial.println("UBAT0010,00130,1.48E7,2.593E+09,1200,11.894,661,0.631,43,1.19,241,284,396,356,278,237,192,177,164,157,147,130,118,113,136,180,200,187,162,136,117,104,98,100,104,100,94,89,89,88,88,89,90,98,111,118,115,111,103,93,84,77,70,65,58,53,49,46,41,39,37,33,28,28,26,21,17,18,16,15");
//  } else if ( i == 5 ) {
//    Serial.println("UBAT0010,00131,1.48E7,1.624E+09,1206,11.892,652,0.631,43,1.07,15,14,13,12,12,9,11,8,6,10,9,8,9,7,5,6,11,13,9,6,5,7,8,12,34,113,221,227,195,149,109,85,70,70,91,94,83,101,144,163,148,113,88,74,65,74,88,80,65,57,59,66,76,77,73,58,42,29,20,16");
//  } else if ( i == 6 ) {
//    Serial.println("UBAT0010,00132,1.48E7,8.731E+08,1203,11.893,652,0.630,43,1.11,13,10,10,10,26,164,48,25,19,22,22,20,14,17,81,123,79,45,26,19,17,17,15,13,20,45,67,75,95,105,90,70,56,49,40,54,78,86,93,93,78,65,57,58,91,75,53,44,32,23,21,21,21,24,30,59,92,93,84,80");
//  } else if ( i == 7 ) {
//    Serial.println("UBAT0010,00132,1.48E7,8.731E+08,1203,11.893,652,0.630,43,1.11,13,10,10,10,26,164,48,25,19,22,22,20,14,17,81,123,79,45,26,19,17,17,15,13,20,45,67,75,95,105,90,70,56,49,40,54,78,86,93,93,78,65,57,58,91,75,53,44,32,23,21,21,21,24,30,59,92,93,84,80");
//  }
  i = (i + 1) % 4;
#elif defined(BBRT_142R)
  if ( i == 0 ) {
    Serial.println("99/99/99\t99:99:99\t667\t95\t541");
  } else if ( i == 1 ) {
    Serial.println("99/99/99\t99:99:99\t667\t95\t540");
  } else if ( i == 2 ) {
    Serial.println("99/99/99\t99:99:99\t667\t96\t540");
  } else if ( i == 3 ) {
    Serial.println("99/99/99\t99:99:99\t668\t3489\t541");
  } else if ( i == 4 ) {
    Serial.println("99/99/99\t99:99:99\t668\t1892\t540");
  } else if ( i == 5 ) {
    Serial.println("99/99/99\t99:99:99\t668\t4119\t541");
  }
  i = (i + 1) % 6;
#endif
  // All instruments run at 1 Hz
  delay(1000);
}
