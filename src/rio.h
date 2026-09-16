/* The cockpit's Remote I/O panel, as state.
 *
 * The pod drives its lamps, bar graphs and soft-label displays over a 9600
 * baud serial link in frames of
 *
 *     01  <node & 0x3F>  <len>  <node+len>  <payload>  <sum(payload)>
 *
 * with three payload opcodes - D1 display, D2 bar graph, D3 lamp - recovered
 * from the firmware's own diagnostic menu. See DEVICES.md.
 *
 * This is deliberately the seam between the emulator and anything that draws a
 * panel: both ends speak the byte stream the real hardware spoke, so a panel
 * can be drawn in this process, driven from a captured file with no emulator
 * running, or one day pointed at a serial port with a salvaged cockpit on the
 * end of it. Nothing here knows about SDL, and nothing here allocates.
 */
#ifndef BATTLEPOD_RIO_H
#define BATTLEPOD_RIO_H

#include <stdint.h>
#include <string.h>

#define RIO_LAMP_MAX  0x80
#define RIO_DEV_LO    0x80		/* displays and bar graphs share these ids */
#define RIO_DEV_HI    0x92

struct rio_panel {
	uint8_t lamp[RIO_LAMP_MAX];
	int     lamp_set[RIO_LAMP_MAX];
	uint8_t bar[RIO_DEV_HI];
	int     bar_set[RIO_DEV_HI];
	char    text[RIO_DEV_HI][9];
	int     text_set[RIO_DEV_HI];
	uint32_t frames;		/* well-formed frames applied */
	uint32_t bad;			/* framing or checksum failures seen */
};

static void rio_reset(struct rio_panel *p)
{
	memset(p, 0, sizeof(*p));
}

/* Apply one payload. Ids outside the ranges the firmware's menu accepts are
 * dropped rather than clamped: a clamp would invent a lit lamp. */
static void rio_apply(struct rio_panel *s, const uint8_t *p, uint32_t n)
{
	uint32_t i;

	if (n < 1) return;
	switch (p[0]) {
	case 0xD1:				/* display: id, 8 characters */
		if (n >= 2 && p[1] >= RIO_DEV_LO && p[1] < RIO_DEV_HI) {
			for (i = 0; i + 2 < n && i < 8; i++)
				s->text[p[1]][i] = (char)p[2 + i];
			s->text_set[p[1]] = 1;
		}
		break;
	case 0xD2:				/* bar graph: id, bars lit */
		if (n >= 3 && p[1] >= RIO_DEV_LO && p[1] < RIO_DEV_HI) {
			s->bar[p[1]] = p[2];
			s->bar_set[p[1]] = 1;
		}
		break;
	case 0xD3:				/* lamp: id, brightness */
		if (n >= 3 && p[1] < RIO_LAMP_MAX) {
			s->lamp[p[1]] = p[2];
			s->lamp_set[p[1]] = 1;
		}
		break;
	default:
		break;			/* D5 and anything else: no panel state */
	}
}

/* Walk a byte stream, applying every frame in it. Returns how far it got, so a
 * caller feeding bytes as they arrive can keep the tail and try again. */
static uint32_t rio_walk(struct rio_panel *s, const uint8_t *buf, uint32_t n)
{
	uint32_t at = 0;

	while (at + 4 <= n) {
		uint32_t len, j;
		uint8_t sum = 0;

		if (buf[at] != 0x01) { at++; s->bad++; continue; }
		len = buf[at + 2];
		if (at + 5 + len > n) break;		/* incomplete: keep the tail */
		if ((uint8_t)(buf[at + 1] + buf[at + 2]) != buf[at + 3]) s->bad++;
		for (j = 0; j < len; j++) sum = (uint8_t)(sum + buf[at + 4 + j]);
		if (sum != buf[at + 4 + len]) s->bad++;
		rio_apply(s, &buf[at + 4], len);
		s->frames++;
		at += 5 + len;
	}
	return at;
}

#endif /* BATTLEPOD_RIO_H */
