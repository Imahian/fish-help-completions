#!/usr/bin/env fish
# Install the pacman/yay/paru integration for help2fish.
# Requires sudo (writes to /usr/local/share and /etc/pacman.d/hooks).
#
#   ./pkg-hooks/install-pacman-hook.fish
#
# Completions are written to /usr/share/fish/vendor_completions.d so every user
# on the machine benefits. Uninstall: ./pkg-hooks/install-pacman-hook.fish --remove

set -l src (status dirname)/..
set -l share /usr/local/share/help2fish
set -l hookdir /etc/pacman.d/hooks

if test "$argv[1]" = --remove
    echo "Removing help2fish pacman hook..."
    sudo rm -f $hookdir/help2fish.hook $share/help2fish-pkghook $share/help2fish.py
    echo "Done."
    exit 0
end

if not type -q pacman
    echo "pacman not found — this integration is for Arch-based systems." >&2
    exit 1
end
if not type -q python3
    echo "python3 is required." >&2
    exit 1
end

echo "help2fish: installing pacman/yay/paru integration (needs sudo)."
echo "NOTE: after each install, the hook runs '<newcmd> --help' as root to parse"
echo "      flags. Only enable this if you trust the packages you install."
echo ""

sudo mkdir -p $share $hookdir /usr/share/fish/vendor_completions.d
sudo install -m755 "$src/bin/help2fish.py"       $share/help2fish.py
sudo install -m755 "$src/bin/help2fish-pkghook"  $share/help2fish-pkghook
sudo install -m644 "$src/pkg-hooks/pacman/help2fish.hook" $hookdir/help2fish.hook

echo "Installed:"
echo "  $hookdir/help2fish.hook"
echo "  $share/help2fish-pkghook"
echo "  $share/help2fish.py"
echo ""
echo "Next time you 'pacman -S <pkg>' (or yay/paru), completions are generated"
echo "into /usr/share/fish/vendor_completions.d and summarised at the end."
