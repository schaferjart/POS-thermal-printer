#!/usr/bin/env bash
set -e

# POS Thermal Printer — setup script
# Works on macOS and Raspberry Pi (Debian/Ubuntu)
#
# Usage:
#   chmod +x setup.sh
#   ./setup.sh              # install deps + auto-start service
#   ./setup.sh --deps-only  # just install dependencies, no service

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
SERVICE_NAME="pos-printer"
DEPS_ONLY=false

if [ "$1" = "--deps-only" ]; then
    DEPS_ONLY=true
fi

OS="$(uname -s)"
echo "==> Detected OS: $OS"
echo "==> Project dir: $SCRIPT_DIR"

# --- Install system dependencies ---

if [ "$OS" = "Linux" ]; then
    echo "==> Installing system packages..."
    sudo apt-get update -qq
    sudo apt-get install -y python3 python3-pip python3-venv libusb-1.0-0-dev fonts-dejavu-core locales

    # Generate UTF-8 locale to avoid locale warnings
    if ! locale -a 2>/dev/null | grep -q "en_US.utf8"; then
        echo "==> Generating en_US.UTF-8 locale..."
        sudo sed -i 's/^# *en_US.UTF-8/en_US.UTF-8/' /etc/locale.gen
        sudo locale-gen en_US.UTF-8
    fi

    # udev rule so the printer is accessible without root
    UDEV_RULE='/etc/udev/rules.d/99-thermal-printer.rules'
    if [ ! -f "$UDEV_RULE" ]; then
        echo "==> Adding USB permission rule for thermal printer..."
        echo 'SUBSYSTEM=="usb", ATTR{idVendor}=="1fc9", ATTR{idProduct}=="2016", MODE="0666"' \
            | sudo tee "$UDEV_RULE" > /dev/null
        sudo udevadm control --reload-rules
        sudo udevadm trigger
    fi

    # Blacklist usblp kernel module so it doesn't grab the printer
    BLACKLIST='/etc/modprobe.d/no-usblp.conf'
    if [ ! -f "$BLACKLIST" ]; then
        echo "==> Blacklisting usblp kernel module..."
        echo 'blacklist usblp' | sudo tee "$BLACKLIST" > /dev/null
        sudo rmmod usblp 2>/dev/null || true
    fi

elif [ "$OS" = "Darwin" ]; then
    echo "==> macOS: checking for python3..."
    if ! command -v python3 &>/dev/null; then
        echo "ERROR: python3 not found. Install it via: brew install python"
        exit 1
    fi
fi

# --- Python virtual environment + dependencies ---

VENV="$SCRIPT_DIR/venv"
if [ ! -d "$VENV" ]; then
    echo "==> Creating virtual environment..."
    python3 -m venv "$VENV"
fi

echo "==> Installing Python dependencies..."
"$VENV/bin/pip" install -q -r "$SCRIPT_DIR/requirements.txt"

echo "==> Dependencies installed."

if [ "$DEPS_ONLY" = true ]; then
    echo "==> Done (deps only). Start manually with:"
    echo "    $VENV/bin/python $SCRIPT_DIR/print_server.py"
    exit 0
fi

# --- Auto-start service ---

if [ "$OS" = "Linux" ]; then
    # systemd service for Raspberry Pi
    echo "==> Setting up systemd service..."
    sudo tee /etc/systemd/system/${SERVICE_NAME}.service > /dev/null <<EOF
[Unit]
Description=POS Thermal Printer Server
After=network.target
StartLimitIntervalSec=60
StartLimitBurst=3

[Service]
Type=simple
User=$(whoami)
WorkingDirectory=$SCRIPT_DIR
ExecStart=$VENV/bin/python $SCRIPT_DIR/print_server.py
Restart=on-failure
RestartSec=10
MemoryMax=400M
TasksMax=100
KillMode=mixed
TimeoutStopSec=15

[Install]
WantedBy=multi-user.target
EOF

    sudo systemctl daemon-reload
    sudo systemctl enable ${SERVICE_NAME}
    sudo systemctl restart ${SERVICE_NAME}
    echo "==> Service started and enabled on boot."
    echo "    Status:  sudo systemctl status ${SERVICE_NAME}"
    echo "    Logs:    journalctl -u ${SERVICE_NAME} -f"
    echo "    Stop:    sudo systemctl stop ${SERVICE_NAME}"

elif [ "$OS" = "Darwin" ]; then
    # launchd plist for macOS
    PLIST="$HOME/Library/LaunchAgents/com.pos.printer.plist"
    echo "==> Setting up launchd service..."
    mkdir -p "$HOME/Library/LaunchAgents"
    cat > "$PLIST" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.pos.printer</string>
    <key>ProgramArguments</key>
    <array>
        <string>$VENV/bin/python</string>
        <string>$SCRIPT_DIR/print_server.py</string>
    </array>
    <key>WorkingDirectory</key>
    <string>$SCRIPT_DIR</string>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>
    <key>StandardOutPath</key>
    <string>/tmp/pos-printer.log</string>
    <key>StandardErrorPath</key>
    <string>/tmp/pos-printer.log</string>
</dict>
</plist>
EOF

    # Unload first if already loaded
    launchctl bootout gui/$(id -u) "$PLIST" 2>/dev/null || true
    launchctl bootstrap gui/$(id -u) "$PLIST"
    echo "==> Service started and will auto-start on login."
    echo "    Logs:    tail -f /tmp/pos-printer.log"
    echo "    Stop:    launchctl bootout gui/\$(id -u) $PLIST"
    echo "    Start:   launchctl bootstrap gui/\$(id -u) $PLIST"
fi

echo ""
echo "==> Done! Open http://$(hostname -s).local:9100 from any device on the network."
