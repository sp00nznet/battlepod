/* The cockpit panel, in windows you can move around.
 *
 * The pod drives its lamps, bar graphs and soft-label displays over one 9600
 * baud serial link. `battlepod --rio-dump` writes that byte stream to a file
 * and this draws it - so the panel is a consumer of the wire the real hardware
 * used, not of an interface we invented. It follows that this runs with no
 * emulator present, from a capture, which is how it gets tested.
 *
 * The windows are one per device class, not one per cockpit panel, and that is
 * deliberate. The System 3.0 manual names the real boards - Weapons A, Weapons
 * B, Buttons, Keypad, LCD - but which lamp id belongs to which of them is not
 * known yet, and grouping them by guess would put a wrong cockpit on screen.
 * Scrubbing through the stream a frame at a time is how that gets settled:
 * watch which id changes when the firmware prints what it did.
 *
 *   left / right   one frame back or forward
 *   home / end     the start of the stream, or all of it
 *   escape         quit
 *
 * usage:
 *   panel <capture.rio>
 *   panel --selftest
 */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "rio.h"

#ifndef PANEL_NO_SDL
#include <SDL2/SDL.h>
#else
/* Without SDL the drawing never compiles, but the rules it uses are still
 * worth checking, so they are declared here too. */
static int lamp_id(int i)
{
	return (i >= 0x00 && i <= 0x3B) || (i >= 0x50 && i <= 0x53) || i == 0x60;
}
static int bar_id(int i)
{
	return i >= RIO_DEV_LO && i < RIO_DEV_HI && i != 0x8C && i != 0x8D && i != 0x8F;
}
static int glyph_of(int c)
{
	if (c == ' ' || c == 0) return 0;
	if (c >= '0' && c <= '9') return 1 + (c - '0');
	if (c >= 'a' && c <= 'z') c -= 32;
	if (c >= 'A' && c <= 'Z') return 11 + (c - 'A');
	switch (c) {
	case '-': return 37;
	case '.': return 38;
	case ':': return 39;
	case '/': return 40;
	}
	return 41;
}
#endif

/* --------------------------------------------------------------- replay */

/* How many whole frames a capture holds, and where each one starts. Rebuilding
 * the panel from the start for every scrub is cheap and keeps one code path:
 * there is no "undo a frame". */
#define MAXFRAMES 4096
static uint32_t g_start[MAXFRAMES + 1];
static int g_frames;

static void index_frames(const uint8_t *buf, uint32_t n)
{
	uint32_t at = 0;

	g_frames = 0;
	while (at + 4 <= n && g_frames < MAXFRAMES) {
		uint32_t len;
		if (buf[at] != 0x01) { at++; continue; }
		len = buf[at + 2];
		if (at + 5 + len > n) break;
		g_start[g_frames++] = at;
		at += 5 + len;
	}
	g_start[g_frames] = at;
}

static void replay(struct rio_panel *p, const uint8_t *buf, int upto)
{
	rio_reset(p);
	if (upto > 0) rio_walk(p, buf, g_start[upto]);
}


#ifndef PANEL_NO_SDL
#include "paneldraw.h"

struct win {
	SDL_Window *w;
	SDL_Renderer *r;
	const char *title;
	void (*draw)(SDL_Renderer *, const struct rio_panel *);
};

/* The build links -mwindows, so there may be no console to print to: the
 * scrub position goes in a title bar instead. */
static void title(struct win *w, int at)
{
	char t[80];

	snprintf(t, sizeof t, "%s  -  frame %d/%d", w->title, at, g_frames);
	SDL_SetWindowTitle(w->w, t);
}

static int run(const uint8_t *buf, uint32_t n)
{
	static struct win wins[] = {
		{ NULL, NULL, "battlepod - lamps",     draw_lamps },
		{ NULL, NULL, "battlepod - displays",  draw_text  },
		{ NULL, NULL, "battlepod - bar graphs", draw_bars },
	};
	static const int W[] = { 8 * 58 + 16, 380, 40 * 12 + 20 };
	static const int H[] = { 9 * 44 + 16, 18 * 26 + 16, 270 };
	struct rio_panel panel;
	int i, at, quit = 0;

	if (SDL_Init(SDL_INIT_VIDEO) != 0) {
		fprintf(stderr, "SDL_Init: %s\n", SDL_GetError());
		return 1;
	}
	for (i = 0; i < 3; i++) {
		wins[i].w = SDL_CreateWindow(wins[i].title, SDL_WINDOWPOS_UNDEFINED,
					     SDL_WINDOWPOS_UNDEFINED, W[i], H[i],
					     SDL_WINDOW_RESIZABLE);
		if (!wins[i].w) { fprintf(stderr, "SDL_CreateWindow: %s\n", SDL_GetError()); return 1; }
		wins[i].r = SDL_CreateRenderer(wins[i].w, -1, SDL_RENDERER_ACCELERATED);
		if (!wins[i].r) wins[i].r = SDL_CreateRenderer(wins[i].w, -1, 0);
		SDL_RenderSetLogicalSize(wins[i].r, W[i], H[i]);
	}

	index_frames(buf, n);
	at = g_frames;				/* open on the end state */
	replay(&panel, buf, at);
	title(&wins[0], at);

	while (!quit) {
		SDL_Event e;
		int moved = 0;

		while (SDL_PollEvent(&e)) {
			if (e.type == SDL_QUIT) quit = 1;
			if (e.type == SDL_WINDOWEVENT && e.window.event == SDL_WINDOWEVENT_CLOSE)
				quit = 1;
			if (e.type != SDL_KEYDOWN) continue;
			switch (e.key.keysym.sym) {
			case SDLK_ESCAPE: quit = 1; break;
			case SDLK_LEFT:  if (at > 0) { at--; moved = 1; } break;
			case SDLK_RIGHT: if (at < g_frames) { at++; moved = 1; } break;
			case SDLK_HOME:  at = 0; moved = 1; break;
			case SDLK_END:   at = g_frames; moved = 1; break;
			default: break;
			}
		}
		if (moved) {
			replay(&panel, buf, at);
			title(&wins[0], at);
		}
		for (i = 0; i < 3; i++) {
			wins[i].draw(wins[i].r, &panel);
			SDL_RenderPresent(wins[i].r);
		}
		SDL_Delay(16);
	}

	for (i = 0; i < 3; i++) {
		SDL_DestroyRenderer(wins[i].r);
		SDL_DestroyWindow(wins[i].w);
	}
	SDL_Quit();
	return 0;
}

#endif /* PANEL_NO_SDL */

/* ------------------------------------------------------------- selftest */

/* Build a capture here and drive the panel from it, so the decode and the
 * replay are tested without a display, a release, or an emulator. */
static int selftest(void)
{
	static uint8_t cap[] = {
		0x01, 0x00, 0x03, 0x03, 0xD3, 0x05, 0x01, 0xD9,			/* lamp 05 = 1 */
		0x01, 0x00, 0x03, 0x03, 0xD2, 0x80, 0x05, 0x57,			/* bar 80 = 5 */
		0x01, 0x00, 0x0A, 0x0A, 0xD1, 0x80, 'B','A','T','T','L','T','E','C', 0xA4,
		0x01, 0x00, 0x03, 0x03, 0xD3, 0x05, 0x00, 0xD8,			/* lamp 05 off */
	};
	struct rio_panel p;

	/* These are the three frames DEVICES.md records from the real firmware,
	 * checksums and all, so a change here fails against the hardware. */
	rio_reset(&p);
	rio_walk(&p, cap, sizeof cap);
	if (p.frames != 4 || p.bad != 0) { printf("frames %u bad %u\n", p.frames, p.bad); return 1; }
	if (!p.lamp_set[5] || p.lamp[5] != 0) return 1;
	if (!p.bar_set[0x80] || p.bar[0x80] != 5) return 1;
	if (!p.text_set[0x80] || memcmp(p.text[0x80], "BATTLTEC", 8)) return 1;
	if (p.lamp_set[6] || p.text_set[0x81]) return 1;	/* nothing invented */

	index_frames(cap, sizeof cap);
	if (g_frames != 4) { printf("indexed %d\n", g_frames); return 1; }

	/* Scrubbing back has to undo: three frames in, the lamp is still lit. */
	replay(&p, cap, 3);
	if (!p.lamp_set[5] || p.lamp[5] != 1) return 1;
	replay(&p, cap, 0);
	if (p.lamp_set[5] || p.frames != 0) return 1;

	/* A device id the firmware's menu does not offer is not a device. */
	if (lamp_id(0x3C) || lamp_id(0x61) || !lamp_id(0x60) || !lamp_id(0x53)) return 1;
	if (bar_id(0x8C) || bar_id(0x8F) || !bar_id(0x8B)) return 1;
	if (glyph_of('B') != 12 || glyph_of('7') != 8 || glyph_of('~') != 41) return 1;

	printf("selftest: ok\n");
	return 0;
}

int main(int argc, char **argv)
{
	uint8_t *buf;
	long n;
	FILE *f;
	int rc;

	if (argc > 1 && !strcmp(argv[1], "--selftest")) return selftest();
	if (argc < 2) {
		fprintf(stderr, "usage: panel <capture.rio>   (battlepod --rio-dump writes one)\n");
		return 2;
	}
#ifdef PANEL_NO_SDL
	fprintf(stderr, "built without SDL2\n");
	return 2;
#else
	f = fopen(argv[1], "rb");
	if (!f) { fprintf(stderr, "cannot open %s\n", argv[1]); return 2; }
	fseek(f, 0, SEEK_END);
	n = ftell(f);
	fseek(f, 0, SEEK_SET);
	buf = malloc(n > 0 ? (size_t)n : 1);
	if (!buf || fread(buf, 1, (size_t)n, f) != (size_t)n) {
		fprintf(stderr, "cannot read %s\n", argv[1]);
		fclose(f);
		return 2;
	}
	fclose(f);
	rc = run(buf, (uint32_t)n);
	free(buf);
	return rc;
#endif
}
