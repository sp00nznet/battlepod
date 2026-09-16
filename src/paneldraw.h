/* Drawing the cockpit panel: a 5x7 font, and one window per device class.
 *
 * Split out of src/panel.c so the emulator can host the same windows in its own
 * process while the firmware is running, rather than only replaying a capture
 * after the fact. Everything here draws `struct rio_panel` and knows nothing
 * about where the bytes came from.
 */
#ifndef BATTLEPOD_PANELDRAW_H
#define BATTLEPOD_PANELDRAW_H

#include <stdio.h>
#include <SDL2/SDL.h>

#include "rio.h"

/* Which ids the firmware's own diagnostic menu accepts. Anything else is not
 * a device, so drawing a cell for it would be inventing hardware. */
static int lamp_id(int i)
{
	return (i >= 0x00 && i <= 0x3B) || (i >= 0x50 && i <= 0x53) || i == 0x60;
}

/* Bar graphs share the display id range but skip three. */
static int bar_id(int i)
{
	return i >= RIO_DEV_LO && i < RIO_DEV_HI && i != 0x8C && i != 0x8D && i != 0x8F;
}

/* ------------------------------------------------------------ a 5x7 font */

/* Five columns per glyph, one bit per row, bit 0 at the top. The displays
 * carry eight ASCII characters and nothing here needs lower case. */
static const unsigned char GLYPH[][5] = {
	{0x00,0x00,0x00,0x00,0x00}, /* space */
	{0x3E,0x51,0x49,0x45,0x3E}, /* 0 */
	{0x00,0x42,0x7F,0x40,0x00}, {0x42,0x61,0x51,0x49,0x46},
	{0x21,0x41,0x45,0x4B,0x31}, {0x18,0x14,0x12,0x7F,0x10},
	{0x27,0x45,0x45,0x45,0x39}, {0x3C,0x4A,0x49,0x49,0x30},
	{0x01,0x71,0x09,0x05,0x03}, {0x36,0x49,0x49,0x49,0x36},
	{0x06,0x49,0x49,0x29,0x1E}, /* 9 */
	{0x7E,0x11,0x11,0x11,0x7E}, /* A */
	{0x7F,0x49,0x49,0x49,0x36}, {0x3E,0x41,0x41,0x41,0x22},
	{0x7F,0x41,0x41,0x22,0x1C}, {0x7F,0x49,0x49,0x49,0x41},
	{0x7F,0x09,0x09,0x09,0x01}, {0x3E,0x41,0x49,0x49,0x7A},
	{0x7F,0x08,0x08,0x08,0x7F}, {0x00,0x41,0x7F,0x41,0x00},
	{0x20,0x40,0x41,0x3F,0x01}, {0x7F,0x08,0x14,0x22,0x41},
	{0x7F,0x40,0x40,0x40,0x40}, {0x7F,0x02,0x0C,0x02,0x7F},
	{0x7F,0x04,0x08,0x10,0x7F}, {0x3E,0x41,0x41,0x41,0x3E},
	{0x7F,0x09,0x09,0x09,0x06}, {0x3E,0x41,0x51,0x21,0x5E},
	{0x7F,0x09,0x19,0x29,0x46}, {0x46,0x49,0x49,0x49,0x31},
	{0x01,0x01,0x7F,0x01,0x01}, {0x3F,0x40,0x40,0x40,0x3F},
	{0x1F,0x20,0x40,0x20,0x1F}, {0x3F,0x40,0x38,0x40,0x3F},
	{0x63,0x14,0x08,0x14,0x63}, {0x07,0x08,0x70,0x08,0x07},
	{0x61,0x51,0x49,0x45,0x43}, /* Z */
	{0x08,0x08,0x08,0x08,0x08}, /* - */
	{0x00,0x60,0x60,0x00,0x00}, /* . */
	{0x00,0x36,0x36,0x00,0x00}, /* : */
	{0x20,0x10,0x08,0x04,0x02}, /* / */
	{0x2A,0x1C,0x7F,0x1C,0x2A}, /* anything else */
};

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

static void text(SDL_Renderer *r, int x, int y, int px, const char *s, int n)
{
	int i, col, row;

	for (i = 0; i < n && s[i]; i++) {
		const unsigned char *g = GLYPH[glyph_of((unsigned char)s[i])];
		for (col = 0; col < 5; col++)
			for (row = 0; row < 7; row++)
				if (g[col] & (1 << row)) {
					SDL_Rect d = { x + (i * 6 + col) * px, y + row * px, px, px };
					SDL_RenderFillRect(r, &d);
				}
	}
}

/* ------------------------------------------------------------ the windows */

static void bg(SDL_Renderer *r, int v)
{
	SDL_SetRenderDrawColor(r, v, v, v + 4, 255);
	SDL_RenderClear(r);
}

static void draw_lamps(SDL_Renderer *r, const struct rio_panel *p)
{
	int i, n = 0;

	bg(r, 16);
	for (i = 0; i < RIO_LAMP_MAX; i++) {
		SDL_Rect box;
		int x, y, lit;
		char id[3];

		if (!lamp_id(i)) continue;
		x = 8 + (n % 8) * 58;
		y = 8 + (n / 8) * 44;
		n++;

		/* Brightness is the lamp's own byte. A lamp we have never been told
		 * about is drawn as an outline, not as dark: unknown is not off. */
		lit = p->lamp_set[i] ? p->lamp[i] : -1;
		box.x = x; box.y = y; box.w = 50; box.h = 26;
		if (lit < 0) {
			SDL_SetRenderDrawColor(r, 60, 60, 70, 255);
			SDL_RenderDrawRect(r, &box);
		} else {
			int v = lit ? 90 + (lit > 165 ? 165 : lit) : 30;
			SDL_SetRenderDrawColor(r, v, v / 5, v / 8, 255);
			SDL_RenderFillRect(r, &box);
		}
		SDL_SetRenderDrawColor(r, 150, 150, 160, 255);
		snprintf(id, sizeof id, "%02X", i);
		text(r, x + 4, y + 30, 1, id, 2);
	}
}

static void draw_text(SDL_Renderer *r, const struct rio_panel *p)
{
	int i, n = 0;

	bg(r, 10);
	for (i = RIO_DEV_LO; i < RIO_DEV_HI; i++, n++) {
		int y = 10 + n * 26;
		char id[3];

		SDL_SetRenderDrawColor(r, 110, 110, 120, 255);
		snprintf(id, sizeof id, "%02X", i);
		text(r, 8, y + 4, 2, id, 2);

		if (p->text_set[i]) SDL_SetRenderDrawColor(r, 70, 255, 120, 255);
		else SDL_SetRenderDrawColor(r, 40, 60, 45, 255);
		text(r, 44, y, 3, p->text_set[i] ? p->text[i] : "        ", 8);
	}
}

static void draw_bars(SDL_Renderer *r, const struct rio_panel *p)
{
	int i, n = 0;

	bg(r, 10);
	for (i = RIO_DEV_LO; i < RIO_DEV_HI; i++) {
		int x, seg, bars;
		char id[3];

		if (!bar_id(i)) continue;
		x = 10 + n * 40;
		n++;
		bars = p->bar_set[i] ? p->bar[i] : 0;
		/* The firmware's menu offers a small number of bars; anything higher
		 * is drawn full rather than off the top of the window. */
		if (bars > 16) bars = 16;
		for (seg = 0; seg < 16; seg++) {
			SDL_Rect d = { x, 8 + (15 - seg) * 14, 26, 10 };
			if (seg < bars) SDL_SetRenderDrawColor(r, 60, 200 - seg * 6, 255 - seg * 9, 255);
			else SDL_SetRenderDrawColor(r, 28, 28, 34, 255);
			SDL_RenderFillRect(r, &d);
		}
		SDL_SetRenderDrawColor(r, p->bar_set[i] ? 170 : 90, 170, 180, 255);
		snprintf(id, sizeof id, "%02X", i);
		text(r, x + 6, 240, 2, id, 2);
	}
}


/* The three windows, one per device class. Grouping by the cockpit's real
 * boards - Weapons A, Weapons B, Buttons, Keypad, LCD - waits on knowing which
 * lamp id sits on which, which is what scrubbing a capture is for. */
static const struct { const char *title; int w, h;
                      void (*draw)(SDL_Renderer *, const struct rio_panel *); }
PANELS[] = {
	{ "battlepod - lamps",      8 * 58 + 16, 9 * 44 + 16,  draw_lamps },
	{ "battlepod - displays",   380,         18 * 26 + 16, draw_text  },
	{ "battlepod - bar graphs", 40 * 12 + 20, 270,         draw_bars  },
};
#define NPANELS 3

#endif /* BATTLEPOD_PANELDRAW_H */
