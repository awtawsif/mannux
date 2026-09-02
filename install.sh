#!/usr/bin/env bash
set -e

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "Installing Mannux Settings..."

mkdir -p ~/.local/bin

if [ -f "${DIR}/mannux" ] && [ -x "${DIR}/mannux" ]; then
    echo "Found precompiled standalone binary. Installing binary to ~/.local/bin/mannux..."
    cp "${DIR}/mannux" ~/.local/bin/mannux
    chmod +x ~/.local/bin/mannux
else
    echo "Installing Python runner to ~/.local/bin/mannux..."
    cat << BIN_EOF > ~/.local/bin/mannux
#!/usr/bin/env bash
export PYTHONPATH="${DIR}:\${PYTHONPATH}"
exec python3 -m mannux "\$@"
BIN_EOF
    chmod +x ~/.local/bin/mannux
fi

# Install Icon
mkdir -p ~/.local/share/icons/hicolor/scalable/apps
if [ -f "${DIR}/data/icons/hicolor/scalable/apps/com.mannux.Settings.svg" ]; then
    cp "${DIR}/data/icons/hicolor/scalable/apps/com.mannux.Settings.svg" ~/.local/share/icons/hicolor/scalable/apps/
fi

# Install Desktop File
mkdir -p ~/.local/share/applications
if [ -f "${DIR}/data/com.mannux.Settings.desktop" ]; then
    cp "${DIR}/data/com.mannux.Settings.desktop" ~/.local/share/applications/
fi

# Update desktop database if tool exists
if command -v update-desktop-database >/dev/null 2>&1; then
    update-desktop-database ~/.local/share/applications/ 2>/dev/null || true
fi

echo "Installation complete! You can now launch Mannux with 'mannux' or via your app launcher (Rofi/Wofi/Fuzzel)."
