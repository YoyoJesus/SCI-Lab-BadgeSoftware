import asyncio
import datetime
import csv
import os
# import pymysql
from bleak import BleakClient, BleakScanner
import struct
from threading import Thread
import threading
# import aiomysql

# UUID 정의
SERVICE_UUID = "0000012f-0000-1000-8000-00805f9b34fb"  # Actual service from Badge04
DATA_CHAR_UUID = "0000345f-0000-1000-8000-00805f9b34fb"  # Actual characteristic from Badge04

# Legacy UUIDs (not used by Badge04 but kept for reference)
LEGACY_SERVICE_UUID = "a33b0000-6238-11ec-90d6-0242ac120003"  # service
SND_CHAR_UUID = "a33b0100-6238-11ec-90d6-0242ac120003"  # characteristic (sound)
RSSI_CHAR_UUID = "a33b0200-6238-11ec-90d6-0242ac120003"  # characteristic (rssi)
ACC_CHAR_UUID = "a33b0300-6238-11ec-90d6-0242ac120003"  # characteristic (acc)

BADGE_ADDRESS = {
    "D9:6D:90:A1:2B:3A": "Badge06",
    "99:0F:9A:A1:83:96": "Badge01",
    "F9:5C:35:CF:D8:53": "Badge09",
    "E9:7D:DA:71:28:2C": "Badge05",
    "F9:54:91:BD:45:86": "Badge10",
    "AA:F4:C8:5D:45:ED": "Badge04",
    "71:F2:53:B7:47:FA": "Badge08",
}


device_counter=0
detected_badge_addresses=[]
Total_detected_device=0
# TABLENAME=''
DBName=''

# Global variable to store received data
received_data = []
stop_collection = False
csv_filename = None

# Global mapping to store client address to badge name mapping
client_badge_mapping = {}
# Initialize unified CSV file for all badge data
def init_unified_csv_file(db_name):
    """Initialize unified CSV file with headers for all badges"""
    global csv_filename
    timestamp = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
    
    # Create a folder for CSV files if it doesn't exist
    csv_folder = "badge_data"
    os.makedirs(csv_folder, exist_ok=True)
    
    csv_filename = os.path.join(csv_folder, f"AllBadges_data_{timestamp}.csv")
    # Create CSV file with headers
    with open(csv_filename, 'w', newline='', encoding='utf-8') as csvfile:
        writer = csv.writer(csvfile)
        writer.writerow(['Timestamp', 'Badge_Name', 'Sound_Level', 'RSSI', 'Acceleration', 'Raw_Data'])
    
    print(f"📝 Created unified CSV file: {csv_filename}")
    return csv_filename

# Check if unified CSV file already exists, if not create it
def ensure_unified_csv_exists(db_name):
    """Ensure the unified CSV file exists, create if it doesn't"""
    global csv_filename
    if csv_filename is None or not os.path.exists(csv_filename):
        init_unified_csv_file(db_name)
    return csv_filename

# Function to save data to CSV
def save_to_csv(timestamp, badge_name, sound, rssi, acceleration, raw_data):
    """Save a single data point to unified CSV file"""
    global csv_filename
    if csv_filename:
        try:
            # Use a simple file append (Python handles concurrent access reasonably well for simple appends)
            with open(csv_filename, 'a', newline='', encoding='utf-8') as csvfile:
                writer = csv.writer(csvfile)
                writer.writerow([timestamp, badge_name, sound, rssi, acceleration, raw_data])
        except Exception as e:
            print(f"❌ Error saving to unified CSV: {e}")
    else:
        print("❌ No CSV file initialized!")

# Notification callback function
def create_notification_handler(badge_name):
    """
    Create a notification handler for a specific badge.
    
    Args:
        badge_name: The name of the badge this handler is for
    
    Returns:
        A notification handler function specific to this badge
    """
    def notification_handler(sender, data):
        """Handle notifications from a specific badge and save to CSV"""
        global stop_collection
        if stop_collection:
            return
            
        try:
            # Decode the data
            decoded_data = data.decode('utf-8')
            timestamp = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]  # Include milliseconds
            
            # Parse the data (format appears to be: "value1,value2,value3")
            values = decoded_data.split(',')
            if len(values) == 3:
                sound_value = values[0].strip()
                rssi_value = values[1].strip()
                acc_value = values[2].strip()
                
                data_entry = {
                    'timestamp': timestamp,
                    'badge_name': badge_name,  # Use the specific badge name
                    'raw_data': decoded_data,
                    'sound': sound_value,
                    'rssi': rssi_value,
                    'acceleration': acc_value
                }
                
                received_data.append(data_entry)
                
                # Save to CSV immediately
                save_to_csv(timestamp, badge_name, sound_value, rssi_value, acc_value, decoded_data)
                
                # Print every 10th reading to avoid spam (but save all to CSV)
                if len(received_data) % 10 == 0:
                    print(f"[{timestamp}] #{len(received_data)} - {badge_name}: Sound={sound_value}, RSSI={rssi_value}, Acc={acc_value}")
            else:
                print(f"[{timestamp}] {badge_name} Raw Data: {decoded_data}")
                # Save raw data too
                save_to_csv(timestamp, badge_name, "N/A", "N/A", "N/A", decoded_data)
                
        except Exception as e:
            print(f"Error processing notification from {badge_name}: {e}")
            print(f"Raw data: {data}")
    
    return notification_handler

# Function to handle user input in a separate thread
def input_handler():
    """Handle user input to stop data collection"""
    global stop_collection
    try:
        input("🛑 Press ENTER to stop data collection...\n")
        stop_collection = True
        print("\n⏹️  Stopping data collection...")
    except:
        stop_collection = True

# 현재 가용한 BLE 장치를 스캔하여 리스트를 출력한다.
# 콜백함수를 이용하여 장치가 발견되었을 때마다 장치 정보를 출력한다.
# 장치를 발견하였을 때 실행되는 콜백함수
async def detection_callback(device, advertisement_data):

    if device.address in BADGE_ADDRESS.keys():
        # print(f'[Target device] {device.address}, RSSI = {device.rssi}')
        print(f'.', end='')
    else:
        # Print all devices to help identify Badge04
        rssi = advertisement_data.rssi if hasattr(advertisement_data, 'rssi') else 'N/A'
        print(f'Found device: {device.address}, Name: {device.name}, RSSI: {rssi}')

async def Scan_Devices():
    global detected_badge_addresses

    # Bleak 스캐너
    scanner = BleakScanner()
    # 콜백함수 등록
    # scanner.register_detection_callback(detection_callback)

    await scanner.start()     # 검색 시작
    print(f'\nScanning devices ', end='')
    await asyncio.sleep(5.0)  # 5초동안 대기. 만약 이 때 검출된 장치가 있다면 콜백함수가 호출된다. (45회 콜백되었음)
    await scanner.stop()      # 검색 중지

    # devices = await scanner.get_discovered_devices()  # 검색된 장치 리스트 반환
    devices = scanner.discovered_devices  # 검색된 장치 리스트 반환
    detected_badge_addresses = [d.address for d in devices if d.address in BADGE_ADDRESS]  # 검색된 장치 중 뱃지만 저장
    # detected_badge_localnames = [BADGE_ADDRESS[bdg] for bdg in detected_badge_addresses]  # 뱃지의 로컬이름 저장

    print(f'\nDetected Badge Addresses  : {detected_badge_addresses}\n')

async def connection_run(address):
    if not address in detected_badge_addresses:
        # print('not detected address')
        return f"Address {address} not detected"
    
    lock = asyncio.Lock()
    global device_counter,Total_detected_device,DBName,client_badge_mapping
    BadgeName = BADGE_ADDRESS[address]
    
    max_retries = 3
    retry_count = 0
    
    client = BleakClient(address)
    
    # Try to connect with retries
    while retry_count < max_retries:
        try:
            print(f"Attempting to connect to {BadgeName} (attempt {retry_count + 1}/{max_retries})")
            await client.connect(timeout=10)
            if client.is_connected:
                print(f'Successfully connected to {BadgeName}')
                # Store the client-badge mapping for notification handling
                client_badge_mapping[address] = BadgeName
                break
            else:
                print(f"Failed to connect to {BadgeName}")
                retry_count += 1
                if retry_count < max_retries:
                    await asyncio.sleep(2)
        except Exception as e:
            print(f"Connection error for {BadgeName}: {e}")
            retry_count += 1
            if retry_count < max_retries:
                await asyncio.sleep(2)
    
    # Update counter regardless of connection success
    async with lock:
        device_counter += 1

    if not client.is_connected:
        print(f"Cannot Connect to: {BadgeName} after {max_retries} attempts")
        return f"Failed to connect to {BadgeName}"

    # Wait for all devices to finish connection attempts
    while device_counter < Total_detected_device:
        await asyncio.sleep(0.5)
    
    print(f"Starting data collection from: {BadgeName}")

    # First, let's discover all available services and characteristics
    print(f"\n=== Discovering services and characteristics for {BadgeName} ===")
    try:
        services = client.services
        for service in services:
            print(f"\nService: {service.uuid} ({service.description})")
            for char in service.characteristics:
                print(f"  Characteristic: {char.uuid}")
                print(f"    Description: {char.description}")
                print(f"    Properties: {char.properties}")
                
                # Try to read characteristics that support reading
                if "read" in char.properties:
                    try:
                        value = await client.read_gatt_char(char.uuid)
                        print(f"    Current value: {value} (hex: {value.hex()})")
                    except Exception as e:
                        print(f"    Read error: {e}")
                
                # Check for notifications/indications
                if "notify" in char.properties or "indicate" in char.properties:
                    print(f"    -> Supports notifications/indications")
    except Exception as e:
        print(f"Service discovery error: {e}")

    # Clear any previous data
    global received_data, stop_collection, csv_filename
    received_data = []
    stop_collection = False
    # Ensure unified CSV file exists (will be shared by all badges)
    csv_file = ensure_unified_csv_exists(DBName)
    # Live graphing will be started in a background thread

    print(f"\n=== Setting up continuous data collection from {BadgeName} ===")
    print(f"📊 Data will be saved to unified file: {csv_filename}")
    
    # Create a badge-specific notification handler
    badge_notification_handler = create_notification_handler(BadgeName)
    
    try:
        # Subscribe to notifications from the actual data characteristic
        await client.start_notify(DATA_CHAR_UUID, badge_notification_handler)
        print(f"✅ Successfully subscribed to notifications from {BadgeName}")
        
        # Read initial value
        try:
            initial_data = await client.read_gatt_char(DATA_CHAR_UUID)
            initial_decoded = initial_data.decode('utf-8')
            print(f"📖 Initial reading: {initial_decoded}")
            
            # Save initial reading to CSV
            timestamp = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]
            values = initial_decoded.split(',')
            if len(values) == 3:
                save_to_csv(timestamp, BadgeName, values[0].strip(), values[1].strip(), values[2].strip(), initial_decoded)
        except Exception as e:
            print(f"⚠️  Could not read initial value: {e}")
        
        # Start input handler thread
        input_thread = threading.Thread(target=input_handler, daemon=True)
        input_thread.start()
        
        print(f"� Starting continuous data collection...")
        print(f"📊 Data is being saved to: {csv_file}")
        print(f"🔄 Collecting data until you press ENTER...")
        
        # Continuous collection loop
        collection_start = datetime.datetime.now()
        last_status_update = datetime.datetime.now()
        status_interval = 10  # Print status every 10 seconds
        
        while not stop_collection:
            await asyncio.sleep(0.5)  # Reasonable delay to prevent busy waiting
            
            # Check if still connected
            if not client.is_connected:
                print(f"⚠️ Connection lost to {BadgeName}, attempting to reconnect...")
                try:
                    await client.connect(timeout=5)
                    if client.is_connected:
                        print(f"✅ Reconnected to {BadgeName}")
                        await client.start_notify(DATA_CHAR_UUID, badge_notification_handler)
                    else:
                        print(f"❌ Failed to reconnect to {BadgeName}")
                        break
                except Exception as e:
                    print(f"❌ Reconnection failed for {BadgeName}: {e}")
                    break
            
            # Print periodic status updates
            current_time = datetime.datetime.now()
            if (current_time - last_status_update).seconds >= status_interval:
                print(f"📊 {BadgeName}: {len(received_data)} data points collected, still running...")
                last_status_update = current_time
        
        # Stop notifications
        await client.stop_notify(DATA_CHAR_UUID)
        print(f"🛑 Stopped notifications from {BadgeName}")
        
        # Final summary
        collection_end = datetime.datetime.now()
        duration = collection_end - collection_start
        print(f"\n=== Data Collection Complete ===")
        print(f"📊 Total data points collected: {len(received_data)}")
        print(f"⏱️  Collection duration: {duration}")
        print(f"📈 Average rate: {len(received_data)/duration.total_seconds():.1f} readings/second")
        print(f"📝 Data saved to: {csv_file}")
        
        if received_data:
            print("📋 Last 3 data points:")
            for i, entry in enumerate(received_data[-3:]):
                print(f"  {i+1}. [{entry['timestamp']}] {entry['raw_data']}")
        
    except Exception as e:
        print(f"❌ Error during data collection: {e}")
        
        # Try the old characteristic method as fallback
        print(f"\n=== Attempting fallback to legacy characteristics ===")
        try:
            # Try to read data from the original characteristic
            read_data = await client.read_gatt_char(SND_CHAR_UUID)
            read_data_decoded = read_data.decode('utf-8')
            print(f"{BadgeName} (legacy): {read_data_decoded}")
        except Exception as e2:
            print(f"Legacy characteristic also failed: {e2}")
            print("This characteristic may not exist on this device")
    
    # Disconnect when done
    try:
        await client.disconnect()
        print(f"Disconnected from {BadgeName}")
    except Exception as e:
        print(f"Disconnect error for {BadgeName}: {e}")
    
    return f"Completed data collection from {BadgeName}"


# TABLENAME = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')  # 프로그램을 실행시키는 시간으로 테이블 생성

async def main():

    global detected_badge_addresses,Total_detected_device,DBName,client_badge_mapping,csv_filename
    DBName=datetime.datetime.now().strftime('%Y%m%d_%H%M%S')  # 프로그램을 실행시키는 시간으로 테이블 생성
    
    # Initialize unified CSV file for all badges
    print("📝 Initializing unified CSV file for all badge data...")
    init_unified_csv_file(DBName)
    
    # Reset the client badge mapping
    client_badge_mapping = {}

    # Simple scan without callback to see all devices
    print(f'\nScanning devices for 5 seconds...')
    devices = await BleakScanner.discover(timeout=5.0)
    
    print(f'\nFound {len(devices)} devices:')
    for device in devices:
        print(f'Address: {device.address}, Name: {device.name}')
    
    detected_badge_addresses = [d.address for d in devices if d.address in BADGE_ADDRESS]  # 검색된 장치 중 뱃지만 저장
    Total_detected_device = len(detected_badge_addresses)

    detected_badge_localnames = [BADGE_ADDRESS[bdg] for bdg in detected_badge_addresses]  # 뱃지의 로컬이름 저장
    print(f'\nDetected Badge LocalNames : {detected_badge_localnames}')
    
    if Total_detected_device == 0:
        print("No device detected : Exit program")
        return
    else:
        print(f'Try to connect to {Total_detected_device} devices')

    print('DataBase Name : ',DBName)
    
    # Reset device counter for this run
    global device_counter
    device_counter = 0
    
    # Only connect to detected devices
    connection_tasks = []
    for address in detected_badge_addresses:
        connection_tasks.append(connection_run(address))

    # Start data collection tasks
    print("🚀 Starting data collection tasks...")
    print("📊 To view live graphs, run: python live_graph_viewer.py")
    
    try:
        # Run data collection
        result = await asyncio.gather(*connection_tasks, return_exceptions=True)
        
        print("Connection results:", result)
        print(f"📊 Total data points collected: {len(received_data)}")
        print("� Data saved to CSV files in the current directory")
            
    except KeyboardInterrupt:
        print("\n⏹️ Stopping data collection...")
        global stop_collection
        stop_collection = True

if __name__ == '__main__':
    asyncio.run(main())