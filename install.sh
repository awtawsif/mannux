#!/usr/bin/env bash
set -e

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "Installing Mannux Settings..."

# 1. Create ~/.local/bin wrapper
mkdir -p ~/.local/bin
cat << BIN_EOF > ~/.local/bin/mannux
#!/usr/bin/env bash
export PYTHONPATH="${DIR}:\${PYTHONPATH}"
exec python3 -m mannux "\$@"
BIN_EOF
chmod +x ~/.local/bin/mannux

# 2. Install Icon
mkdir -p ~/.local/share/icons/hicolor/scalable/apps
cp "${DIR}/data/icons/hicolor/scalable/apps/com.mannux.Settings.svg" ~/.local/share/icons/hicolor/scalable/apps/

# 3. Install Desktop File
mkdir -p ~/.local/share/applications
cp "${DIR}/data/com.mannux.Settings.desktop" ~/.local/share/applications/

# 4. Update desktop database if tool exists
if command -v update-desktop-database >/dev/null 2>&1; then
    update-desktop-database ~/.local/share/applications/ 2>/dev/null || true
fi

echo "Installation complete! You can now launch Mannux with 'mannux' or via your app launcher (Rofi/Wofi/Fuzzel)."
