# Session Context

## User Prompts

### Prompt 1

Implement the following plan:

# iPad Wireless Printing Support

## Context

The POS thermal printer (Xprinter XP-V330M) has USB + Serial + **LAN (Ethernet)** ports. Currently `printer_core.py` only supports USB connections. The goal is to let an iPad print wirelessly. The printer has no WiFi/Bluetooth, so the path is:

**iPad → WiFi → Router → Ethernet → Printer** (direct network print)
or
**iPad → WiFi → Router → Server (Mac/RPi) → USB/Ethernet → Printer**

The HTTP server al...

### Prompt 2

commit this

