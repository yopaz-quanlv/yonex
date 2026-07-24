#!/bin/zsh

set -u

launcher_dir="${0:A:h}"

wait_for_key() {
    if [[ -t 0 ]]; then
        read -k 1 "?Press any key to close..."
        echo
    fi
}

if [[ "$(uname -s)" != "Darwin" ]]; then
    echo "This launcher is intended for macOS."
    exit 1
fi

python_bin=""
for candidate in /opt/homebrew/bin/python3 /usr/local/bin/python3 /usr/bin/python3; do
    if [[ -x "$candidate" ]] \
        && "$candidate" -c 'import gi, PIL; gi.require_version("Gtk", "4.0")' 2>/dev/null; then
        python_bin="$candidate"
        break
    fi
done

if [[ -z "$python_bin" ]]; then
    echo "GTK 4 and Pillow for Python are not installed."
    echo "Install Homebrew, then run: brew install gtk4 pygobject3 pillow"
    echo "After installation, double-click this file again."
    wait_for_key
    exit 1
fi

if ! command -v fceux >/dev/null 2>&1 \
    && [[ ! -x /opt/homebrew/bin/fceux ]] \
    && [[ ! -x /usr/local/bin/fceux ]]; then
    echo "FCEUX was not found."
    echo "Install it with: brew install fceux"
    wait_for_key
    exit 1
fi

cd "$launcher_dir"
for qt_plugins in /opt/homebrew/opt/qtbase/share/qt/plugins /usr/local/opt/qtbase/share/qt/plugins; do
    if [[ -d "$qt_plugins" ]]; then
        export QT_PLUGIN_PATH="$qt_plugins"
        break
    fi
done
exec "$python_bin" "$launcher_dir/game_launcher.py"
