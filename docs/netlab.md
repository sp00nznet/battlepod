# Building and testing on netlab

Day-to-day builds and test runs go to
[netlab](https://github.com/sp00nznet/recomp-netlab), the lab's build farm
and test machines, so the workstation stays free. This is the recipe, what
a run looks like, and the three things that took most of a day to find.

## The recipe

battlepod is a private repository, so its recipe lives in netlab's
git-ignored `local/projects/battlepod.env`:

```sh
REPO=https://github.com/sp00nznet/battlepod
TOOLSET=script
BUILDS_ON=mingw
EXCLUDE='_dump *.sit out'
BUILD='make deps PYTHON=python3 && make -j8 BUILD=build-linux CC=clang test && make -j8 CC=x86_64-w64-mingw32-gcc HOSTCC=clang PKG_CONFIG=mingw-pkg-config all cockpit view panel build/paneltest.exe build/viewtest.exe'
ARTIFACTS='build/battlepod.exe build/cockpit.exe build/view.exe build/panel.exe build/paneltest.exe build/viewtest.exe'
EXE=cockpit.exe
RUN='${SDL_RENDER_DRIVER:+set SDL_RENDER_DRIVER=$SDL_RENDER_DRIVER&& }$EXE $VWE_GAME_FILES\Full_Load_3_0 --duart 11000 --rstub 3FF00000 --rirq --astub --monitor --clock 2000808 --set 40000100=1234567 --packet-file out\play.pkt --live-pod --steps 100000000000 --top 0'
RUN_FILES=out/play.pkt
PROC=cockpit
WINDOW='battlepod - main view'
QA='battlepod.exe --selftest && paneltest.exe --selftest && viewtest.exe --selftest'
QA_STEPS=local/projects/battlepod.qa
SHIP=none
```

- **`EXCLUDE`** keeps the release (`_dump/`, the `.sit` files) and `out/`
  off the farm. Only source goes to a builder.
- **`BUILD`** runs `make test` natively first, into `build-linux/`, because
  the cross-built exes can't run on the builder; then the Windows exes.
  `HOSTCC` builds Musashi's table generator for the builder itself.
- **`out/play.pkt`** is the start-of-game packets, made on the workstation,
  since the test VM has no Python:
  `PLAY_PKT=out/play.pkt BIN=none tools/play.sh [scenario] [vehicle]`.
- The test machine names its copy of the release's Game Files, at a path
  with no spaces, in `local/machines/<machine>.env`:
  `VWE_GAME_FILES='C:\netlab\vwe\GameFiles'`.

The steps file starts a game, throttles up, throttles back, targets, fires
and turns, with a screenshot at each stage:

```
expect-window battlepod - main view 60
wait 15
snap drop.png
key w
...
snap walking.png
wait 4
snap closer.png
...
snap fire.png
key a
wait 2
snap turn.png
```

## A run

```
$ ./netlab build battlepod
...
build wall 7.82 s
-> <checkout>/build-farm/cockpit.exe
...
$ ./netlab qa battlepod --on <windows-vm>
== qa: battlepod.exe --selftest && paneltest.exe --selftest && viewtest.exe --selftest
== qa: local/projects/battlepod.qa
run on <windows-vm>: C:\netlab\battlepod\cockpit.exe C:\netlab\vwe\GameFiles\Full_Load_3_0 ...
ok   window 'battlepod - main view'
snap drop.png
snap walking.png
snap closer.png
snap fire.png
snap turn.png
PASS
```

The screenshots land in netlab's `local/qa/battlepod/<time>/`;
[the one in the README](screenshots/cockpit-loki.png) is `closer.png`.

## What it took

**The builders had no compiler for this.** netlab's Windows builds were all
clang-cl and CMake; battlepod is a GNU Makefile with SDL2. netlab now has a
`mingw` builder kind (`builders/mingw/setup.sh`: mingw-w64 GCC and SDL2's
mingw build, behind a `mingw-pkg-config` that sees only SDL2), installed
alongside clang-cl on the same containers. The Makefile grew `HOSTCC`,
`PYTHON` and `PKG_CONFIG` so a cross build can name them, and the first
Linux build found `src/battlepod.c` calling `clock_gettime` without
`<time.h>`.

**On the test VM the game crawled and the view looked frozen.** Every
screenshot was the same frame. Headless (`SDL_VIDEODRIVER=dummy`) the same
400M instructions took 24 s; windowed they hadn't finished after 90 s, with
three cores busy in the display driver. With SDL's software renderer they
took 23 s, so it is the VM's Direct3D path: both Direct3D renderers crawl,
and OpenGL is slow too. The machine variable `SDL_RENDER_DRIVER=software`
puts the recipe on the software renderer there, and only there. Redrawing
less often did not help; the presents are not the cost.

**Keys never arrived.** Esc didn't even close the cockpit. netlab sent keys
with .NET's `SendKeys`, which carries no scan codes, and SDL2 reads the scan
code. A `keybd_event` with one quit the cockpit at once. netlab's `play.ps1`
now sends real key events with scan codes, which any game reading scan codes
(SDL, DirectInput) needs.

## Without netlab

Everything here is `make` underneath. The README's *Step by step* is the
same build on a workstation, and `--headless --record out.mp4` is the same
proof of play without a window.
