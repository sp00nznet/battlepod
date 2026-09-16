# battlepod - phase 0 bring-up harness
#
# Needs a C compiler and the Musashi 68k core:
#   git clone --depth 1 https://github.com/kstenerud/Musashi third_party/musashi

MUSASHI := third_party/musashi
BUILD   := build

CC      := gcc
CFLAGS  := -pipe -O2 -g -Wall -Wno-unused-parameter
INC     := -Isrc -I$(MUSASHI) -I$(BUILD)
# Musashi's documented hook for supplying your own configuration.
CFLAGS  += -DMUSASHI_CNF='"battlepod_m68kconf.h"'

# Windows toolchains inherit a TMP that may not be writable; keep scratch local.
export TMPDIR := $(CURDIR)/$(BUILD)/tmp
export TMP    := $(TMPDIR)
export TEMP   := $(TMPDIR)

OBJS := $(BUILD)/battlepod.o $(BUILD)/m68kcpu.o $(BUILD)/m68kdasm.o \
        $(BUILD)/softfloat.o $(BUILD)/m68kops.o

all: $(BUILD)/battlepod.exe

$(BUILD)/battlepod.exe: $(OBJS)
	$(CC) $(CFLAGS) -o $@ $(OBJS) -lm

$(BUILD)/battlepod.o: src/battlepod.c $(BUILD)/m68kops.h | $(BUILD)
	$(CC) $(CFLAGS) $(INC) -c -o $@ $<

$(BUILD)/m68kcpu.o: $(MUSASHI)/m68kcpu.c $(BUILD)/m68kops.h | $(BUILD)
	$(CC) $(CFLAGS) $(INC) -c -o $@ $<

$(BUILD)/m68kdasm.o: $(MUSASHI)/m68kdasm.c $(BUILD)/m68kops.h | $(BUILD)
	$(CC) $(CFLAGS) $(INC) -c -o $@ $<

$(BUILD)/softfloat.o: $(MUSASHI)/softfloat/softfloat.c | $(BUILD)
	$(CC) $(CFLAGS) $(INC) -c -o $@ $<

$(BUILD)/m68kops.o: $(BUILD)/m68kops.c | $(BUILD)
	$(CC) $(CFLAGS) $(INC) -c -o $@ $<

# m68kmake generates the opcode dispatch table from m68k_in.c.
$(BUILD)/m68kops.c $(BUILD)/m68kops.h: $(BUILD)/m68kmake.exe $(MUSASHI)/m68k_in.c
	./$(BUILD)/m68kmake.exe $(BUILD)/ $(MUSASHI)/m68k_in.c

$(BUILD)/m68kmake.exe: $(MUSASHI)/m68kmake.c | $(BUILD)
	$(CC) -pipe -O2 -o $@ $<

$(BUILD):
	mkdir -p $(BUILD)/tmp

deps:
	@test -d $(MUSASHI) || git clone --depth 1 https://github.com/kstenerud/Musashi $(MUSASHI)

test: $(BUILD)/battlepod.exe $(BUILD)/paneltest.exe
	./$(BUILD)/battlepod.exe --selftest
	./$(BUILD)/paneltest.exe --selftest

# Replays the cockpit boot and counts milestones. Skips if no release present;
# point VWE_GAME_FILES at the extracted "Console Files/Game Files" directory.
# Passed through explicitly: on Windows the shell make invokes may not inherit
# the environment make itself was given.
VWE_GAME_FILES ?=
conformance: $(BUILD)/battlepod.exe
	VWE_GAME_FILES="$(VWE_GAME_FILES)" sh tools/conformance.sh

# The panel renderer is optional: it needs SDL2, and nothing else here does.
# It reads the Remote I/O byte stream `battlepod --rio-dump` writes, so it runs
# with no emulator present.
SDL_CFLAGS := $(shell pkg-config --cflags sdl2 2>/dev/null)
SDL_LIBS   := $(shell pkg-config --static --libs sdl2 2>/dev/null)

panel: $(BUILD)/panel.exe

$(BUILD)/panel.exe: src/panel.c src/rio.h | $(BUILD)
	@test -n "$(SDL_LIBS)" || { echo "panel needs SDL2 (pkg-config --libs sdl2 found nothing)"; exit 1; }
	$(CC) $(CFLAGS) -Isrc $(SDL_CFLAGS) -o $@ src/panel.c -static $(SDL_LIBS)

# Built without SDL so the self-check runs anywhere, including in CI.
$(BUILD)/paneltest.exe: src/panel.c src/rio.h | $(BUILD)
	$(CC) $(CFLAGS) -Isrc -DPANEL_NO_SDL -o $@ src/panel.c

clean:
	rm -rf $(BUILD)

.PHONY: all clean test deps conformance panel
