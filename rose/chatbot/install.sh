#!/bin/sh
set -eu
cd "$(dirname "$0")"
python3 -m venv --system-site-packages .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python create_wrappers.py
make -C ../shell install-user
chmod +x rose-chat
mkdir -p "$HOME/.local/bin" "$HOME/.config/systemd/user" "$HOME/.local/share/applications"
mkdir -p "$HOME/.config/autostart"
ln -sf /noobia/rose_tools/chatbot/rose-chat "$HOME/.local/bin/rose-chat"
cp rose-chat.service "$HOME/.config/systemd/user/rose-chat.service"
cp rose-chat-gui.service "$HOME/.config/systemd/user/rose-chat-gui.service"
cp rose-hardware-watch.service "$HOME/.config/systemd/user/rose-hardware-watch.service"
cp rose-display-media.service "$HOME/.config/systemd/user/rose-display-media.service"
cat > "$HOME/.config/autostart/rose-chat.desktop" <<'EOF'
[Desktop Entry]
Type=Application
Name=Rose Chat and Display
Exec=systemctl --user start rose-chat-gui.service
Terminal=false
X-GNOME-Autostart-enabled=true
EOF
cat > "$HOME/.local/share/applications/rose-chat.desktop" <<'EOF'
[Desktop Entry]
Type=Application
Name=Rose Chat
Comment=Talk to Rose by keyboard or English microphone
Exec=/noobia/rose_tools/chatbot/rose-chat
Icon=audio-input-microphone
Terminal=false
Categories=Utility;
EOF
systemctl --user daemon-reload
systemctl --user enable --now rose-chat.service
systemctl --user enable --now rose-hardware-watch.service rose-display-media.service
