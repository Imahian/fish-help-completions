#!/usr/bin/env fish
# Install the apt integration for help2fish (Debian/Ubuntu). Requires sudo.
#   ./pkg-hooks/install-apt-hook.fish            install
#   ./pkg-hooks/install-apt-hook.fish --remove   uninstall

set -l src (status dirname)/..
set -l share /usr/local/share/help2fish
set -l aptdir /etc/apt/apt.conf.d

if test "$argv[1]" = --remove
    sudo rm -f $aptdir/99help2fish $share/help2fish-pkghook-apt $share/help2fish-pkghook $share/help2fish.py
    echo "Removed apt integration."
    exit 0
end

if not type -q apt; and not type -q apt-get
    echo "apt not found — this integration is for Debian/Ubuntu systems." >&2
    exit 1
end

echo "help2fish: installing apt integration (needs sudo)."
echo "NOTE: runs '<newcmd> --help' after installs to parse flags."
echo ""

sudo mkdir -p $share $aptdir /usr/share/fish/vendor_completions.d
sudo install -m755 "$src/bin/help2fish.py"                   $share/help2fish.py
sudo install -m755 "$src/bin/help2fish-pkghook"              $share/help2fish-pkghook
sudo install -m755 "$src/pkg-hooks/apt/help2fish-pkghook-apt" $share/help2fish-pkghook-apt
sudo install -m644 "$src/pkg-hooks/apt/99help2fish"          $aptdir/99help2fish

echo "Installed apt Post-Invoke hook. Next 'apt install <pkg>' generates completions."
