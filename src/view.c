/* The pod's main view, in a window.
 *
 * The primary monitor ran 480x360. `tools/render.py --raw` writes frames at
 * exactly that size as plain RGB - no container, no compression - and this
 * shows them, scaled up with the aspect kept.
 *
 * Keeping the seam at a raw frame is the same bargain the panel makes with the
 * Remote I/O byte stream. The rasteriser that produces the frames is Python
 * today and will be C in the pod eventually; the window does not care, and
 * swapping one for the other changes nothing here.
 *
 *   space          play or pause
 *   left / right   one frame back or forward
 *   home           the first frame
 *   escape         quit
 *
 * usage:
 *   view <frames.rgb> [--size 480x360] [--fps 30]
 *   view --selftest
 */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stdint.h>

#ifndef VIEW_NO_SDL
#include <SDL2/SDL.h>
#endif

#define VIEW_W 480		/* what the display list says the pod ran */
#define VIEW_H 360

/* How many whole frames a file holds at this size, and whether it divides
 * evenly. A file that does not divide is a size mismatch, not a short frame,
 * and saying so beats showing a picture sheared by one row. */
static long frame_count(long bytes, int w, int h, long *leftover)
{
	long one = (long)w * h * 3;

	if (one <= 0) { *leftover = bytes; return 0; }
	*leftover = bytes % one;
	return bytes / one;
}

static int parse_size(const char *s, int *w, int *h)
{
	int a = 0, b = 0;

	if (sscanf(s, "%dx%d", &a, &b) != 2 || a <= 0 || b <= 0) return 0;
	*w = a;
	*h = b;
	return 1;
}

#ifndef VIEW_NO_SDL

static int run(const uint8_t *buf, long frames, int w, int h, int fps)
{
	SDL_Window *win;
	SDL_Renderer *r;
	SDL_Texture *tex;
	long at = 0;
	int quit = 0, playing = frames > 1, shown = -1;
	Uint32 last = 0;

	if (SDL_Init(SDL_INIT_VIDEO) != 0) {
		fprintf(stderr, "SDL_Init: %s\n", SDL_GetError());
		return 1;
	}
	/* Open at two-to-one so the pod's 480x360 is legible on a modern
	 * display, and let the window be dragged and resized from there. */
	win = SDL_CreateWindow("battlepod - main view", SDL_WINDOWPOS_UNDEFINED,
			       SDL_WINDOWPOS_UNDEFINED, w * 2, h * 2,
			       SDL_WINDOW_RESIZABLE);
	if (!win) { fprintf(stderr, "SDL_CreateWindow: %s\n", SDL_GetError()); return 1; }
	r = SDL_CreateRenderer(win, -1, SDL_RENDERER_ACCELERATED);
	if (!r) r = SDL_CreateRenderer(win, -1, 0);
	/* Logical size keeps the 4:3 the pod had, letterboxing rather than
	 * stretching when the window is dragged to some other shape. */
	SDL_RenderSetLogicalSize(r, w, h);
	tex = SDL_CreateTexture(r, SDL_PIXELFORMAT_RGB24, SDL_TEXTUREACCESS_STREAMING, w, h);
	if (!tex) { fprintf(stderr, "SDL_CreateTexture: %s\n", SDL_GetError()); return 1; }

	while (!quit) {
		SDL_Event e;
		Uint32 now;

		while (SDL_PollEvent(&e)) {
			if (e.type == SDL_QUIT) quit = 1;
			if (e.type != SDL_KEYDOWN) continue;
			switch (e.key.keysym.sym) {
			case SDLK_ESCAPE: quit = 1; break;
			case SDLK_SPACE:  playing = !playing; break;
			case SDLK_LEFT:   playing = 0; at = (at + frames - 1) % frames; break;
			case SDLK_RIGHT:  playing = 0; at = (at + 1) % frames; break;
			case SDLK_HOME:   playing = 0; at = 0; break;
			default: break;
			}
		}

		now = SDL_GetTicks();
		if (playing && frames > 1 && now - last >= (Uint32)(1000 / (fps > 0 ? fps : 30))) {
			at = (at + 1) % frames;
			last = now;
		}

		if (at != shown) {
			char t[80];
			SDL_UpdateTexture(tex, NULL, buf + at * (long)w * h * 3, w * 3);
			snprintf(t, sizeof t, "battlepod - main view  -  %ldx%ld  frame %ld/%ld",
				 (long)w, (long)h, at + 1, frames);
			SDL_SetWindowTitle(win, t);
			shown = (int)at;
		}
		SDL_RenderClear(r);
		SDL_RenderCopy(r, tex, NULL, NULL);
		SDL_RenderPresent(r);
		SDL_Delay(4);
	}

	SDL_DestroyTexture(tex);
	SDL_DestroyRenderer(r);
	SDL_DestroyWindow(win);
	SDL_Quit();
	return 0;
}

#endif /* VIEW_NO_SDL */

static int selftest(void)
{
	long left;

	/* One frame at the pod's own size, and the arithmetic that says so. */
	if (frame_count(480L * 360 * 3, VIEW_W, VIEW_H, &left) != 1 || left) return 1;
	if (frame_count(480L * 360 * 3 * 60, VIEW_W, VIEW_H, &left) != 60 || left) return 1;

	/* A file that does not divide is a size mismatch and has to be caught,
	 * not rounded down into a sheared picture. */
	if (frame_count(480L * 360 * 3 + 7, VIEW_W, VIEW_H, &left) != 1 || left != 7) return 1;
	if (frame_count(100, VIEW_W, VIEW_H, &left) != 0 || left != 100) return 1;

	{
		int w = 0, h = 0;
		if (!parse_size("640x480", &w, &h) || w != 640 || h != 480) return 1;
		if (parse_size("480", &w, &h)) return 1;
		if (parse_size("0x0", &w, &h)) return 1;
	}

	printf("selftest: ok\n");
	return 0;
}

int main(int argc, char **argv)
{
	int w = VIEW_W, h = VIEW_H, fps = 30, i, rc;
	const char *path = NULL;
	uint8_t *buf;
	long n, frames, left;
	FILE *f;

	if (argc > 1 && !strcmp(argv[1], "--selftest")) return selftest();
	for (i = 1; i < argc; i++) {
		if (!strcmp(argv[i], "--size") && i + 1 < argc) {
			if (!parse_size(argv[++i], &w, &h)) {
				fprintf(stderr, "bad --size, want WxH\n");
				return 2;
			}
		} else if (!strcmp(argv[i], "--fps") && i + 1 < argc) {
			fps = atoi(argv[++i]);
		} else if (argv[i][0] != '-') {
			path = argv[i];
		}
	}
	if (!path) {
		fprintf(stderr, "usage: view <frames.rgb> [--size 480x360] [--fps 30]\n"
				"       tools/render.py --raw writes one\n");
		return 2;
	}

	f = fopen(path, "rb");
	if (!f) { fprintf(stderr, "cannot open %s\n", path); return 2; }
	fseek(f, 0, SEEK_END);
	n = ftell(f);
	fseek(f, 0, SEEK_SET);
	frames = frame_count(n, w, h, &left);
	if (frames < 1) {
		fprintf(stderr, "%s holds %ld bytes, less than one %dx%d frame\n", path, n, w, h);
		fclose(f);
		return 2;
	}
	if (left)
		fprintf(stderr, "warning: %ld bytes left over - is it really %dx%d?\n", left, w, h);
	buf = malloc((size_t)n);
	if (!buf || fread(buf, 1, (size_t)n, f) != (size_t)n) {
		fprintf(stderr, "cannot read %s\n", path);
		fclose(f);
		return 2;
	}
	fclose(f);

#ifdef VIEW_NO_SDL
	fprintf(stderr, "built without SDL2\n");
	rc = 2;
#else
	rc = run(buf, frames, w, h, fps);
#endif
	free(buf);
	return rc;
}
