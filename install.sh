#!/usr/bin/env sh
# Install Charlie as the `charlie` command for the current user.
# No root needed. No network needed. Nothing phones home.
set -e

SRC_DIR="$(cd "$(dirname "$0")" && pwd)"
BIN_DIR="${HOME}/.local/bin"

if ! command -v python3 >/dev/null 2>&1; then
    echo "Charlie needs Python 3.9+. Install it first:"
    echo "  - macOS:          brew install python3   (or from python.org)"
    echo "  - Debian/Ubuntu:  sudo apt install python3"
    echo "  - Fedora:         sudo dnf install python3"
    echo "  - Windows:        use WSL, or run: python charlie.py"
    exit 1
fi

mkdir -p "$BIN_DIR"
cp "$SRC_DIR/charlie.py" "$BIN_DIR/charlie"
chmod +x "$BIN_DIR/charlie"

echo "✓ Installed: $BIN_DIR/charlie"

case ":$PATH:" in
  *":$BIN_DIR:"*) ;;
  *)
    echo ""
    echo "  $BIN_DIR is not on your PATH yet. Add this line to your"
    echo "  ~/.bashrc or ~/.zshrc, then open a new terminal:"
    echo ""
    echo "      export PATH=\"\$HOME/.local/bin:\$PATH\""
    ;;
esac

echo ""
if command -v ollama >/dev/null 2>&1; then
    echo "✓ Ollama found."
    echo "  If you haven't yet, pull a model:  ollama pull qwen2.5:7b"
else
    echo "Next step — install Ollama (Charlie's free, local brain):"
    echo "  https://ollama.com/download"
    echo "  then:  ollama pull qwen2.5:7b"
fi
echo ""
echo "Start her with:  charlie"
