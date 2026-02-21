# Teensy USB on Windows – Work on All USB Ports

The Hamamatsu C7942 module talks to the Teensy 4.1 over USB using libusb (via the `usb1` Python package). On Windows, each USB port can get a different driver. If the Teensy is not using a libusb‑compatible driver on a given port, the app will not see it.

## Make the Teensy work on every port

Install the **WinUSB** driver for the Teensy so Windows uses it no matter which port you use.

### Option A: One-time setup per port (recommended)

Do this **once per physical USB port** you use:

1. **Plug the Teensy** into the USB port you want to use.
2. **Download Zadig**: [zadig.akeo.ie](https://zadig.akeo.ie/)
3. **Run Zadig as Administrator** (right‑click → Run as administrator).
4. **Menu: Options → List All Devices** (so you see every USB device).
5. In the dropdown, select **Teensy** or **USB Serial** or the device with:
   - **Vendor ID:** `16C0`
   - **Product ID:** `0483`
6. In the driver area, ensure **WinUSB** is selected (not “USB Serial” or “Teensy”).
7. Click **Replace Driver** or **Install Driver**.
8. When it finishes, that port is set. You can unplug and replug the Teensy on that port and it will keep working.

Repeat these steps with the Teensy plugged into each **other** USB port you use. After that, the Teensy will work on all those ports.

### Option B: If the Teensy does not appear in the list

- Unplug other USB devices so the right device is easy to spot.
- Plug only the Teensy in and run Zadig again.
- Look for a device with VID `16C0` and PID `0483` (shown in the list or in Device Manager under the device’s details).

### Check that it works

From the `app` folder, with your venv activated:

```powershell
python -c "import usb1; ctx = usb1.USBContext(); h = ctx.openByVendorIDAndProductID(0x16c0, 0x0483); print('Teensy found: YES' if h else 'Teensy found: NO')"
```

If you see `Teensy found: YES`, the app will be able to connect to the Teensy on that port.

## Why this is needed

Windows assigns a driver the first time a device is seen on a port. By default it may use a “USB Serial” or vendor driver that reserves the device, so libusb cannot open it. Installing WinUSB for the Teensy (VID 16C0, PID 0483) on each port tells Windows to use a driver that works with libusb, so the C7942 module can connect no matter which port you use.
