#!/usr/bin/env python3
"""
Simple Badge MAC Finder
=======================

A lightweight script to quickly find badge MAC addresses.
Perfect for updating the BADGE_ADDRESS dictionary.

Usage:
    python find_badge_macs.py

Output:
    - List of all discovered BLE devices
    - Highlighted potential badge devices
    - Copy-paste ready BADGE_ADDRESS entries
"""

import asyncio
import datetime
from bleak import BleakScanner

# Current known badge patterns to help identify badges
BADGE_NAME_PATTERNS = ["badge", "arduino", "esp32", "sensor"]

async def find_badge_macs(scan_time=15):
    """Simple scan to find badge MAC addresses"""
    
    print("🔍 Scanning for Badge MAC Addresses...")
    print(f"⏱️  Scan duration: {scan_time} seconds")
    print("=" * 50)
    
    try:
        # Discover all BLE devices
        devices = await BleakScanner.discover(timeout=scan_time)
        
        if not devices:
            print("❌ No BLE devices found")
            return
        
        print(f"📡 Found {len(devices)} BLE devices:\n")
        
        # Separate badges from other devices
        potential_badges = []
        other_devices = []
        
        for device in devices:
            device_name = device.name or "Unknown"
            device_rssi = getattr(device, 'rssi', 'N/A')
            
            # Check if this might be a badge
            is_potential_badge = any(pattern in device_name.lower() for pattern in BADGE_NAME_PATTERNS)
            
            device_info = {
                'address': device.address,
                'name': device_name,
                'rssi': device_rssi
            }
            
            if is_potential_badge or "badge" in device_name.lower():
                potential_badges.append(device_info)
            else:
                other_devices.append(device_info)
        
        # Display potential badges first
        if potential_badges:
            print("🏷️  POTENTIAL BADGES:")
            print("-" * 30)
            for i, device in enumerate(potential_badges, 1):
                print(f"{i:2d}. {device['address']} | {device['name']:<15} | RSSI: {device['rssi']}")
            
            print("\n📝 Copy-paste ready BADGE_ADDRESS entries:")
            print("```python")
            for i, device in enumerate(potential_badges, 1):
                badge_name = device['name'] if device['name'] != "Unknown" else f"Badge{i:02d}"
                print(f'    "{device["address"]}": "{badge_name}",')
            print("```\n")
        
        # Display all other devices
        print("📱 ALL DISCOVERED DEVICES:")
        print("-" * 30)
        all_devices = potential_badges + other_devices
        
        for i, device in enumerate(all_devices, 1):
            badge_indicator = "🏷️ " if device in potential_badges else "   "
            print(f"{badge_indicator}{i:2d}. {device['address']} | {device['name']:<15} | RSSI: {device['rssi']}")
        
        # Save to file
        timestamp = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f"badge_macs_{timestamp}.txt"
        
        with open(filename, 'w') as f:
            f.write(f"Badge MAC Address Scan Results\n")
            f.write(f"Timestamp: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"Total devices found: {len(devices)}\n")
            f.write(f"Potential badges: {len(potential_badges)}\n")
            f.write("=" * 50 + "\n\n")
            
            if potential_badges:
                f.write("POTENTIAL BADGES:\n")
                f.write("-" * 20 + "\n")
                for device in potential_badges:
                    f.write(f"{device['address']} | {device['name']} | RSSI: {device['rssi']}\n")
                
                f.write("\nBADGE_ADDRESS Dictionary Entries:\n")
                for i, device in enumerate(potential_badges, 1):
                    badge_name = device['name'] if device['name'] != "Unknown" else f"Badge{i:02d}"
                    f.write(f'    "{device["address"]}": "{badge_name}",\n')
                f.write("\n")
            
            f.write("ALL DEVICES:\n")
            f.write("-" * 15 + "\n")
            for device in all_devices:
                f.write(f"{device['address']} | {device['name']} | RSSI: {device['rssi']}\n")
        
        print(f"💾 Results saved to: {filename}")
        
        return potential_badges
        
    except Exception as e:
        print(f"❌ Error during scan: {e}")
        return None

async def main():
    """Main function"""
    print("🏷️  BADGE MAC ADDRESS FINDER")
    print("=" * 35)
    print("This tool quickly scans for Bluetooth LE devices")
    print("and identifies potential badge devices.\n")
    
    # Ask for scan duration
    try:
        duration = input("🕐 Scan duration in seconds (default: 15): ").strip()
        scan_time = int(duration) if duration else 15
    except ValueError:
        scan_time = 15
        print("Using default scan time of 15 seconds")
    
    print()  # Add spacing
    
    # Run the scan
    badges = await find_badge_macs(scan_time)
    
    if badges:
        print(f"\n🎯 Summary: Found {len(badges)} potential badge device(s)")
        print("\n📋 Next steps:")
        print("1. Copy the BADGE_ADDRESS entries above")
        print("2. Update your main script's BADGE_ADDRESS dictionary")
        print("3. Run your main script to connect to the badges")
    else:
        print("\n❌ No potential badge devices found")
        print("💡 Tips:")
        print("   • Make sure badges are powered on and advertising")
        print("   • Try scanning for a longer duration")
        print("   • Check if badges are already connected to another device")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n\n👋 Scan interrupted by user. Goodbye!")
    except Exception as e:
        print(f"\n❌ Unexpected error: {e}")
