/***********************************************************
 *  Human Matrix version 4
 *  - Target board : Arduino Nano 33 BLE Sense
 *  - data : sound, acc, rssi
 *  updated on Dec. 21. 2021
***********************************************************/
#include <ArduinoBLE.h>
#include <Arduino_LSM9DS1.h>  // accelerometer, gyroscope, magnetometer
#include <PDM.h>  // microphone 
#include <avr/dtostrf.h>

// create service and characteristics
BLEService sensorService("a33b0000-6238-11ec-90d6-0242ac120003");
BLECharacteristic SendStrData("a33b0100-6238-11ec-90d6-0242ac120003", BLERead | BLENotify,100);
//BLEIntCharacteristic rssiLevel("a33b0200-6238-11ec-90d6-0242ac120003", BLERead | BLENotify);
//BLEFloatCharacteristic acc("a33b0300-6238-11ec-90d6-0242ac120003", BLERead | BLENotify);


// sound data
short Buffer[256]; // sound buffer
volatile int Read; // read data

// rssi strength
int rssiStrength = 0;

// last acc. data
float oldX = 0., oldY = 0., oldZ = 0., absDiffSum = 0.;


void setup(){
  Serial.begin(9600);
  PDM.onReceive(onPDMdata); // sound read function
  pinMode(LED_BUILTIN, OUTPUT);

  while(!Serial);  // 시리얼이 연결될 때까지 대기
  
  if(!IMU.begin()){  // LSM9DS1 센서 시작
    Serial.println("Failed to initialize IMU!");
    while(1);
  }
  
  if(!PDM.begin(1, 16000)){  // mono, 16kHz sampling
    Serial.println("Failed to initialize Mic!");
    while(1);
  }
  
  if(!BLE.begin()){
    Serial.println("starting BLE failed!");
    while(1);
  }

  //-----------------------------------
  BLE.setLocalName("HM Badge No.01"); // <<<<<<<<<<<<<<<<<<<<<
  //-----------------------------------
  BLE.setAdvertisedService(sensorService);
  sensorService.addCharacteristic(SendStrData);
//  sensorService.addCharacteristic(rssiLevel);
//  sensorService.addCharacteristic(acc);
  BLE.addService(sensorService);
  
  BLE.advertise();
  Serial.println("Bluetooth device active, waiting for connections...");
}
unsigned int Count=0;
void loop(){
  
  BLEDevice central = BLE.central();
  
  if(central){
    Serial.print("Connected to central: ");
    Serial.println(central.address());
    digitalWrite(LED_BUILTIN, HIGH);
    
    while(central.connected()){
      int SndData = updateSoundData();
      int RSSIData = updateRSSI(central);
      float ACCData = updateAccelerometer();  
      char StrCount[100];
      char temp[20];
      dtostrf(ACCData, 5, 3, temp);
      sprintf(StrCount,"%d,%d,%s",SndData,RSSIData,temp);
      SendStrData.writeValue(StrCount,strlen(StrCount));
      Count++;
      delay(100);  // 데이터 업데이트 간격
      
    }
  
    digitalWrite(LED_BUILTIN, LOW);
    Serial.print("Disconnected from central: ");
    Serial.println(central.address());
  }
}

int updateSoundData(){
  int power = 0;
  if(Read){
  
    for(int i=0; i<Read; i++){
      power += Buffer[i]*Buffer[i];  
    }
    power /= sizeof(Buffer);  // 버퍼에 쌓인 사운드 데이터의 파워

    Serial.print("Average : ");
    Serial.println(power);
    return power;  
  }
}

void onPDMdata(){
  int bytesAvailable = PDM.available();
  PDM.read(Buffer, bytesAvailable);
  Read = bytesAvailable/2;   // =======>>>>>>> ???
}

float updateAccelerometer(){
  float x, y, z, absDX = 0., absDY = 0., absDZ = 0.;
  
  if(IMU.accelerationAvailable()){
    IMU.readAcceleration(x, y, z);
    
    if(x != oldX){
      absDX = abs(x - oldX);
      oldX = x;
    }
    
    if(y != oldY){
      absDY = abs(y - oldY);
      oldY = y;
    }
    
    if(z != oldZ){
      absDZ = abs(z - oldZ);
      oldZ = z;
    }
    
    absDiffSum = absDX + absDY + absDZ;
//    acc.writeValue(absDiffSum);
//    Serial.print(x);
//    Serial.print('\t');
//    Serial.print(y);
//    Serial.print('\t');
//    Serial.print(z);
//    Serial.print('\t');
    Serial.println(absDiffSum);
    return absDiffSum;
  }
}

int updateRSSI(BLEDevice _central){
  rssiStrength = _central.rssi();
//  rssiLevel.writeValue(-rssiStrength); // convert to positive number
  Serial.print("RSSI Strength : ");
  Serial.println(rssiStrength);
  return rssiStrength;
}
