#!/bin/sh
# Quick start: from a fresh download to a pod you can fly, in one go. Runs the
# same commands as README.md's "Step by step" route - checks what's needed,
# asks before installing anything, asks where your copy of the VWE release
# is, builds, self-checks, and leaves a launcher (Play.cmd on Windows, ./play
# elsewhere). Safe to run again: every step it has already done is skipped.
#
# On Windows, run Setup.cmd, which finds (or offers to install) MSYS2 and runs
# this inside it.
#
# It never downloads or copies the VWE release: you point it at your own.

set -u
cd "$(dirname "$0")"
LOG=$PWD/setup.log
: > "$LOG"

say()  { printf '%s\n' "$*"; printf '%s\n' "$*" >> "$LOG"; }
fail() { say ""; say "Setup stopped: $*"; say "The details are in $LOG"; exit 1; }
run()  { printf '\n$ %s\n' "$*" >> "$LOG"; "$@" >> "$LOG" 2>&1; }
ask()  { printf '%s [y/N] ' "$1"; read -r a; case $a in y*|Y*) return 0 ;; *) return 1 ;; esac; }
have() { command -v "$1" >/dev/null 2>&1; }

say "battlepod setup - log: $LOG"

# 1. Prerequisites: a C compiler, make, git, Python 3, and SDL2 (for the
#    cockpit's windows) found through pkg-config.
missing=
for t in gcc make git python pkg-config; do have "$t" || missing="$missing $t"; done
have pkg-config && pkg-config --exists sdl2 || missing="$missing sdl2"
if [ -n "$missing" ]; then
    say "Missing:$missing"
    if [ -n "${MSYSTEM:-}" ]; then
        pkgs="mingw-w64-x86_64-gcc mingw-w64-x86_64-SDL2 mingw-w64-x86_64-pkgconf mingw-w64-x86_64-python make git"
        ask "Install them with pacman ($pkgs, about 400 MB)?" || fail "install$missing, then run setup again."
        run pacman -S --needed --noconfirm $pkgs || fail "pacman could not install them."
    elif have apt-get; then
        pkgs="build-essential git python3 python-is-python3 pkg-config libsdl2-dev"
        ask "Install them with apt ($pkgs, about 300 MB; asks for your password)?" || fail "install$missing, then run setup again."
        run sudo apt-get install -y $pkgs || fail "apt could not install them."
    elif have brew; then
        pkgs="git python sdl2 pkg-config"
        ask "Install them with Homebrew ($pkgs, about 200 MB)?" || fail "install$missing, then run setup again."
        run brew install $pkgs || fail "Homebrew could not install them."
    else
        fail "install$missing with your system's package manager, then run setup again."
    fi
fi
say "prerequisites: ok"

# 2. Your copy of the release: the "Game Files" folder that holds Full_Load_3_0.
GF=
[ -f .vwe ] && GF=$(cat .vwe)
if [ ! -f "$GF/Full_Load_3_0" ]; then
    GF=$(find . -path ./third_party -prune -o -name Full_Load_3_0 -print 2>/dev/null | head -1)
    GF=${GF%/Full_Load_3_0}
fi
while [ ! -f "$GF/Full_Load_3_0" ]; do
    say ""
    say "Where is your copy of VWE Release 13.1.8? (https://archive.org/details/vwe-release-13.1.8)"
    printf 'Path to the extracted release, its "Game Files" folder, or the .sit: '
    read -r p
    [ -n "$p" ] || fail "no release given."
    case $p in
    *.sit)
        have unar || fail "unar is needed to open a .sit (https://theunarchiver.com/command-line); or extract it elsewhere and give the folder."
        run unar -k visible -o _dump "$p" || fail "unar could not extract $p."
        p=_dump ;;
    esac
    GF=$(find "$p" -name Full_Load_3_0 2>/dev/null | head -1)
    GF=${GF%/Full_Load_3_0}
    [ -f "$GF/Full_Load_3_0" ] || say "No Full_Load_3_0 under $p."
done
GF=$(cd "$GF" && pwd)
printf '%s\n' "$GF" > .vwe
say "release: $GF"

# 3. Build and self-check: the commands Step by step lists.
say "building (a minute or two the first time)..."
run make deps || fail "make deps could not fetch Musashi (is git online?)."
run make || fail "the build failed."
run make cockpit || fail "the cockpit (SDL2) build failed."
run make test || fail "the self-check failed."
say "built and self-checked: ok"

# 4. A launcher.
case $(uname -s) in
MINGW*|MSYS*)
    w=$(cygpath -w "$PWD")
    printf '@echo off\r\nset MSYSTEM=MINGW64\r\nset CHERE_INVOKING=1\r\ncd /d "%s"\r\n"%s" -lc "VWE_GAME_FILES=\\"%s\\" tools/play.sh %%*"\r\n' \
        "$w" "$(cygpath -w /usr/bin/bash.exe)" "$GF" > Play.cmd
    launcher=Play.cmd ;;
*)
    printf '#!/bin/sh\ncd "$(dirname "$0")"\nVWE_GAME_FILES="$(cat .vwe)" exec tools/play.sh "$@"\n' > play
    chmod +x play
    launcher=./play ;;
esac
say ""
say "Done. Start a game with $launcher (W/S throttle, A/D stick, space fires, T targets, Esc quits)."
