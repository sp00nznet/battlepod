/* battlepod - VWE cockpit bring-up harness (phase 0).
 *
 * Loads a pod image set exactly as the VWE "Load" scripts describe, runs the
 * 68020, and reports every bus access that falls outside declared RAM. The
 * point is to discover the cockpit CPU board's device map by observation,
 * since no schematic survives.
 *
 * Nothing here contains or embeds VWE material; it reads the operator's own
 * extraction of the release at runtime.
 */

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stdint.h>
#include <ctype.h>
#include <dirent.h>
#include <stdarg.h>
#include <time.h>

#include "m68k.h"
#include "rio.h"
#include "mesh.h"
#include "raster.h"
#include "rig.h"
#include "scene.h"

/* ---------------------------------------------------------------- memory */

#define PAGE_BITS 16
#define PAGE_SIZE (1u << PAGE_BITS)
#define NPAGES    (1u << (32 - PAGE_BITS))

static uint8_t  *g_page[NPAGES];
static uint32_t  g_openbus = 0xFFFFFFFFu;

static void ram_add(uint32_t base, uint32_t len)
{
	uint64_t a = base, end = (uint64_t)base + len;
	for (a &= ~(uint64_t)(PAGE_SIZE - 1); a < end; a += PAGE_SIZE) {
		uint32_t pg = (uint32_t)(a >> PAGE_BITS);
		if (pg >= NPAGES) break;
		if (!g_page[pg]) {
			g_page[pg] = calloc(1, PAGE_SIZE);
			if (!g_page[pg]) { fprintf(stderr, "out of memory\n"); exit(1); }
		}
	}
}

static int mapped(uint32_t a) { return g_page[a >> PAGE_BITS] != NULL; }

/* ------------------------------------------------------- unmapped access log */

#define HITCAP 65536		/* power of two; also the entry cap */

typedef struct {
	uint32_t addr;
	uint32_t reads, writes;
	uint32_t first_pc;
	uint32_t last_write;
	uint8_t  sizes;		/* bit0 = byte, bit1 = word, bit2 = long */
	uint8_t  used, wrote;
} Hit;

static Hit      g_hit[HITCAP];
static uint32_t g_nhit, g_hit_dropped;
static uint32_t g_reads_total, g_writes_total;
static int      g_note_flag;	/* set by note(), consumed by the trace loop */
static uint32_t g_note_addr;
static uint32_t g_vector_hit;	/* address of an unmapped vector-table fetch */
static uint32_t g_vbr;		/* vector base; the pod's monitor puts it in RAM */
static uint32_t g_vecfetch;	/* last vector-table read, mapped or not */
static unsigned g_dis_cpu = M68K_CPU_TYPE_68040;  /* disassemble with the FPU decoded */

/* --watch: log accesses inside a region that is mapped RAM, which the unmapped
 * log never sees. Pointed at a loaded resource it shows which offsets the
 * firmware actually reads, and from where. */
static uint32_t g_watch_base, g_watch_len;

/* `--watch` reports reads, and reads only, because a write to mapped memory
 * takes the fast path and returns before anything is noted. That is the wrong
 * half for the question that keeps coming up: not "was this value consulted"
 * but "where did it come from". The entity pointer table has 231 references in
 * the ROM and reading them was never going to say which one sets a class.
 *
 * So: a write trap. Any write into the range is printed with the pc that made
 * it, capped so a mistake costs a screenful rather than a log file. */
#define WTRAP_MAX 20000
static uint32_t g_wtrap_base, g_wtrap_len;
static unsigned g_wtrap_n;

/* MC68681 DUART, the cockpit's two serial ports. Register N sits at BASE+N*2,
 * channel A at registers 0-7 and channel B at 8-15, which is how the ROM's
 * driver addresses it:
 *
 *   channel A   status 0x11002  data 0x11006   (Remote I/O board, 9600)
 *   channel B   status 0x11012  data 0x11016   (console, 19200)
 *
 * Only what the driver touches is modelled: the status bits it polls, and the
 * receive and transmit holding registers. Channel B carries the firmware's own
 * narration, and its receiver is what drives the built-in diagnostic monitor. */

#define DUART_SR_RXRDY 0x01
#define DUART_SR_TXRDY 0x04
#define DUART_SR_TXEMT 0x08

#define CONCAP 262144

static uint32_t g_duart;		/* base address, 0 = not modelled */
static char     g_conbuf[CONCAP];	/* channel B output: the console */
static size_t   g_conlen;
#define RIOCAP 8192
static uint8_t  g_riobuf[RIOCAP];	/* channel A output: the Remote I/O protocol */
static uint32_t g_rio_tx;

static const char *g_in[2];		/* pending receive data, per channel */
static size_t      g_inlen[2], g_inpos[2];

/* Interrupt state. The firmware masks everything at reset, then enables
 * IMR = 0x03 - channel A transmit and receive - and drives the Remote I/O
 * board entirely from the interrupt handler. */
static unsigned g_imr;			/* interrupt mask register */
static unsigned g_ivr = 0x0F;		/* interrupt vector register, reset value */
static int      g_txena[2];		/* transmitter enabled, per channel */

/* --rio-late holds the panel's input back until every queued packet has been
 * delivered: a control report only means something once the pod has a Mech
 * to steer, and before the link that is slot 0. The number is how many
 * polls of the quiet wire to wait after that. */
static int      g_rio_late;
static int      g_pkt_delivered;
static unsigned g_npkts;
static unsigned g_pkt_next;		/* the next queued packet to arm */
static int      g_pkt_skip, g_pkt_null;
static unsigned g_pkt_queued;		/* every packet ever queued, for the report */
static int      g_net;			/* --net: packets and panel input from a hub */
static void net_send_packet(uint32_t node, const uint8_t *d, uint32_t n);
static void rx_append(const uint8_t *d, size_t n);
static uint32_t g_clock_val, g_clock_wall;	/* the timebase; see --clock */
static int      g_clock_rt;

static int rx_pending(int chan)
{
	if (chan == 0 && g_rio_late && g_pkt_delivered <= (int)g_npkts + g_rio_late)
		return 0;
	return g_inpos[chan] < g_inlen[chan];
}

/* Register number 0-15, or -1 if the address is not ours. */
static int duart_reg(uint32_t a)
{
	if (!g_duart || a < g_duart || a >= g_duart + 0x20 || (a & 1)) return -1;
	return (int)((a - g_duart) >> 1);
}

/* MC68681 interrupt status: bit 0 TxRDYA, 1 RxRDYA, 4 TxRDYB, 5 RxRDYB.
 * The transmitter is modelled as infinitely fast, so TxRDY simply tracks
 * whether that channel's transmitter is enabled - which is what makes the
 * firmware's "disable the transmitter when the queue drains" idiom work. */
static unsigned duart_isr(void)
{
	return (g_txena[0]     ? 0x01u : 0)
	     | (rx_pending(0)  ? 0x02u : 0)
	     | (g_txena[1]     ? 0x10u : 0)
	     | (rx_pending(1)  ? 0x20u : 0);
}

static int duart_irq(void) { return g_duart && (duart_isr() & g_imr) != 0; }

static int duart_read(uint32_t a, unsigned *out)
{
	int reg = duart_reg(a), chan = reg >> 3;
	if (reg < 0) return 0;

	switch (reg & 7) {
	case 1:					/* SRA / SRB */
		*out = (g_txena[chan] ? DUART_SR_TXRDY | DUART_SR_TXEMT : 0)
		     | (rx_pending(chan) ? DUART_SR_RXRDY : 0);
		return 1;
	case 3:					/* RBA / RBB */
		*out = rx_pending(chan) ? (unsigned char)g_in[chan][g_inpos[chan]++] : 0;
		return 1;
	case 5:
		*out = (reg == 5) ? duart_isr() : 0;	/* reg 5 ISR; reg 13 is the input port */
		return 1;
	}
	*out = 0;
	return 1;
}

static int duart_write(uint32_t a, unsigned v)
{
	int reg = duart_reg(a), chan = reg >> 3;
	if (reg < 0) return 0;

	switch (reg & 7) {
	case 2:					/* CRA / CRB - command register */
		if (v & 0x04) g_txena[chan] = 1;	/* enable transmitter  */
		if (v & 0x08) g_txena[chan] = 0;	/* disable transmitter */
		break;
	case 3:					/* TBA / TBB - transmit */
		if (chan == 1) {
			if (g_conlen < CONCAP - 1) g_conbuf[g_conlen++] = (char)(v & 0xFF);
		} else {
			if (g_rio_tx < RIOCAP) g_riobuf[g_rio_tx] = (uint8_t)v;
			g_rio_tx++;
		}
		break;
	case 4:
		if (reg == 12) g_ivr = v & 0xFF;	/* reg 4 is ACR; reg 12 is the vector */
		break;
	case 5:
		if (reg == 5) g_imr = v & 0xFF;		/* reg 5 IMR; reg 13 is OPCR */
		break;
	}
	return 1;
}

/* The renderer finishes a frame by interrupting. Its handler is on vector
 * 0x42, it reads the cause out of bits 4-6 of the word at 0x3800001C, and it
 * acknowledges by clearing bit 7 of that word. Cause 0x50 is frame-complete:
 * the arm stamps the timebase into 0x0217A326, which `Async_Render` clears on
 * the way out and which the end-of-frame code waits on. Without it the pod
 * builds one frame and waits for ever. */
#define RIRQ_CSR    0x3800001Cu
#define RIRQ_VECTOR 0x42
#define RIRQ_DONE   0x00D0u	/* bit 7 pending, bits 4-6 cause 0x50 */

/* A render cannot complete instantly. `Async_Render` rings the doorbell and
 * then, two instructions later, clears the render-done flag the completion
 * interrupt sets - so an interrupt taken at the doorbell is wiped by the clear
 * that follows it, and the pod waits for ever for a frame it already finished.
 * The board took milliseconds; anything past that clear will do. This is a
 * calibration knob, not a constant: --rirq LEVEL:DELAY sets it. */
#define RIRQ_DELAY 20000	/* instructions */

static int g_rirq;		/* interrupt level, 0 = off */
static int g_rirq_delay = RIRQ_DELAY;
static int g_rirq_pending;	/* instructions left before the line goes up */
static uint32_t g_rirq_next;	/* --realtime: the timebase before which no frame completes */

static int rirq_asserted(void);

/* Musashi asks what vector to use when it takes the interrupt. The 68681 is
 * programmed for vectored interrupts, so answer with whatever the firmware
 * wrote to the interrupt vector register. */
int bp_int_ack(unsigned int level)
{
	if (g_rirq && (int)level == g_rirq && rirq_asserted()) return RIRQ_VECTOR;
	return (int)g_ivr;
}

/* Turn the usual backslash escapes in a --duart-in argument into real bytes.
 * The monitor reads one character at a time and wants a carriage return. */
static char *unescape(const char *s)
{
	char *out = malloc(strlen(s) + 1), *w = out;
	for (; *s; s++) {
		if (*s != '\\' || !s[1]) { *w++ = *s; continue; }
		switch (*++s) {
		case 'r': *w++ = '\r'; break;
		case 'n': *w++ = '\n'; break;
		case 't': *w++ = '\t'; break;
		case '0': *w++ = '\0'; break;
		default:  *w++ = *s;   break;
		}
	}
	*w = 0;
	return out;
}


/* ------------------------------------------------- remote i/o decoder */

/* Turn the captured channel A byte stream back into cockpit panel state. The
 * decoder itself lives in src/rio.h, because the panel renderer consumes the
 * same bytes: that stream is the seam, not an interface of ours. */

static struct rio_panel g_panel;
static const char *g_riodump;
/* Look at memory when the run ends. --watch says what touched an address and
 * --tap says what the registers held somewhere; this just reads, which is what
 * checking a configuration byte wants. */
#define PEEKS 32
static uint32_t g_peek[PEEKS], g_peekn[PEEKS];
static int g_peeks;

static void peek_report(void)
{
	int i;
	uint32_t j;

	for (i = 0; i < g_peeks; i++) {
		printf("peek %08X:", g_peek[i]);
		for (j = 0; j < g_peekn[i]; j++) {
			if (j % 16 == 0) printf("\n  %04X ", j);
			printf(" %02X", (unsigned)m68k_read_memory_8(g_peek[i] + j));
		}
		printf("\n");
	}
}
static const char *g_liveframes;

static void rio_report(void)
{
	uint32_t n = g_rio_tx < RIOCAP ? g_rio_tx : RIOCAP;
	int i, any;

	rio_walk(&g_panel, g_riobuf, n);

	printf("\nremote i/o: %u frames decoded%s\n", g_panel.frames,
	       g_panel.bad ? " (checksum or framing errors)" : "");

	any = 0;
	for (i = 0; i < RIO_LAMP_MAX; i++)
		if (g_panel.lamp_set[i]) { printf("  lamp %02X brightness %02X\n", i, g_panel.lamp[i]); any = 1; }
	for (i = RIO_DEV_LO; i < RIO_DEV_HI; i++)
		if (g_panel.bar_set[i]) { printf("  bargraph %02X bars %u\n", i, g_panel.bar[i]); any = 1; }
	for (i = RIO_DEV_LO; i < RIO_DEV_HI; i++)
		if (g_panel.text_set[i]) { printf("  display %02X \"%.8s\"\n", i, g_panel.text[i]); any = 1; }
	if (!any) printf("  no panel state changed\n");
}

/* Hand the raw stream to a file so the panel renderer can be driven from a
 * capture with no emulator running - which is the point of keeping the seam
 * at the wire. */
static void rio_dump(const char *path)
{
	uint32_t n = g_rio_tx < RIOCAP ? g_rio_tx : RIOCAP;
	FILE *f = fopen(path, "wb");

	if (!f) { fprintf(stderr, "cannot write %s\n", path); return; }
	fwrite(g_riobuf, 1, n, f);
	fclose(f);
	printf("remote i/o: %u bytes written to %s\n", n, path);
}

/* Stop and look when the firmware reaches an address.
 *
 * --watch says what touched a region of memory; this says what the registers
 * held when execution arrived somewhere. That is what reading a routine's
 * arguments needs: the packet sender takes its buffer as a stack argument, so
 * the only way to see a packet the pod is about to transmit is to be standing
 * at the door when it goes out. */

#define TAPS 32
/* Write a longword the first time execution reaches an address. The pod's
 * own network identity is cleared by the firmware's startup and then never
 * written again - it is configuration, and it arrives from outside - so
 * supplying it before the run is useless and supplying it after is what a
 * configured pod looks like. */
static uint32_t g_setat_pc[TAPS], g_setat_addr[TAPS], g_setat_val[TAPS];
static uint8_t g_setat_done[TAPS];
static int g_setats;

static uint32_t g_tap[TAPS];
static uint32_t g_taphit[TAPS];
static int g_taps;
static uint32_t g_tapdump;		/* bytes to dump at (A6 + g_tapoff) */
static int32_t  g_tapoff;

static void tap_check(uint32_t pc)
{
	int i;

	for (i = 0; i < g_setats; i++) {
		if (pc != g_setat_pc[i] || g_setat_done[i]) continue;
		m68k_write_memory_32(g_setat_addr[i], g_setat_val[i]);
		g_setat_done[i] = 1;
		printf("set %08X = %08X at pc %08X\n",
		       g_setat_addr[i], g_setat_val[i], pc);
	}

	for (i = 0; i < g_taps; i++) {
		if (pc != g_tap[i]) continue;
		g_taphit[i]++;
		if (g_taphit[i] > 16) return;		/* enough to read */
		printf("tap %08X hit %u\n", pc, g_taphit[i]);
		printf("   d0 %08X d1 %08X d2 %08X d3 %08X\n",
		       m68k_get_reg(NULL, M68K_REG_D0), m68k_get_reg(NULL, M68K_REG_D1),
		       m68k_get_reg(NULL, M68K_REG_D2), m68k_get_reg(NULL, M68K_REG_D3));
		printf("   a0 %08X a1 %08X a6 %08X a7 %08X\n",
		       m68k_get_reg(NULL, M68K_REG_A0), m68k_get_reg(NULL, M68K_REG_A1),
		       m68k_get_reg(NULL, M68K_REG_A6), m68k_get_reg(NULL, M68K_REG_A7));
		if (g_tapdump) {
			uint32_t base = m68k_get_reg(NULL, M68K_REG_A6) + (uint32_t)g_tapoff;
			uint32_t j;
			printf("   at a6%+d (%08X):", (int)g_tapoff, base);
			for (j = 0; j < g_tapdump; j++) {
				if (j % 16 == 0) printf("\n     %04X ", j);
				printf(" %02X", (unsigned)m68k_read_memory_8(base + j));
			}
			printf("\n");
		}
	}
}

/* ------------------------------------------------------------- geometry */

/* The model archive is already in the emulator's memory - the load script puts
 * BattleTech_TI_Res there - so the geometry needs no file of its own. This
 * walks it in place with the parser resmap.py established: sixteen bytes of
 * header, then the body unless the flag byte says it lives elsewhere. */

static uint32_t mesh_be32(uint32_t a)
{
	return ((uint32_t)m68k_read_memory_8(a) << 24) |
	       ((uint32_t)m68k_read_memory_8(a + 1) << 16) |
	       ((uint32_t)m68k_read_memory_8(a + 2) << 8) |
	       m68k_read_memory_8(a + 3);
}

/* Find a type 1 resource by id, copying its body out. Returns its length. */
static uint32_t mesh_find(uint32_t base, uint32_t limit, uint32_t want,
			  uint8_t *out, uint32_t cap)
{
	uint32_t at = base;

	while (at + 16 <= base + limit) {
		uint32_t rid = mesh_be32(at), rtype = mesh_be32(at + 4);
		uint32_t flags = mesh_be32(at + 8), count = mesh_be32(at + 12);
		uint32_t inline_len = ((flags & 0xFF) & 0x10) ? 0 : count * 4;
		uint32_t i;

		if (rid == 0xFFFFFFFFu) return 0;
		if (rid == want && rtype == 1 && inline_len && inline_len <= cap) {
			for (i = 0; i < inline_len; i++)
				out[i] = (uint8_t)m68k_read_memory_8(at + 16 + i);
			return inline_len;
		}
		at += 16 + inline_len;
	}
	return 0;
}

static uint8_t g_meshbuf[1 << 20];
static struct mesh g_mesh;
static uint32_t g_mesh_id;
static int g_mesh_all;
static uint32_t g_rig_id;
static int g_rig_all;		/* which model to decode, 0 for none */
static uint32_t g_mesh_base = 0x02B00000u;

/* Decode one model and say what came out, in the same terms tools/model.py
 * reports so the two can be compared straight across. */
/* Every type 1 model, decoded, in the same terms tools/model.py reports for
 * its "fall" walk. The two are separate ports of one interpreter and have to
 * come out with the same totals; the harness checks both against the same
 * floor, so a port that quietly drops an opcode fails here rather than looking
 * like a rendering bug much later. */
static void mesh_all(void)
{
	uint32_t at = g_mesh_base, limit = g_mesh_base + 0x200000u;
	int models = 0;
	long verts = 0, polys = 0, mats = 0;

	while (at + 16 <= limit) {
		uint32_t rid = mesh_be32(at), rtype = mesh_be32(at + 4);
		uint32_t flags = mesh_be32(at + 8), count = mesh_be32(at + 12);
		uint32_t inline_len = ((flags & 0xFF) & 0x10) ? 0 : count * 4;

		if (rid == 0xFFFFFFFFu) break;
		if (rtype == 1 && inline_len && inline_len <= sizeof g_meshbuf) {
			uint32_t i;
			for (i = 0; i < inline_len; i++)
				g_meshbuf[i] = (uint8_t)m68k_read_memory_8(at + 16 + i);
			mesh_run(&g_mesh, g_meshbuf, inline_len);
			models++;
			verts += g_mesh.nvert;
			polys += g_mesh.npoly;
			mats += g_mesh.nmat;
		}
		at += 16 + inline_len;
	}
	printf("\nmodels decoded in C : %d\n", models);
	printf("vertices decoded in C: %ld\n", verts);
	printf("polygons decoded in C: %ld\n", polys);
	printf("materials decoded in C: %ld\n", mats);
}

static void mesh_report(void)
{
	uint32_t len = mesh_find(g_mesh_base, 0x200000u, g_mesh_id, g_meshbuf, sizeof g_meshbuf);

	if (!len) {
		printf("\nmodel %u: not found in the archive at %08X\n", g_mesh_id, g_mesh_base);
		return;
	}
	mesh_run(&g_mesh, g_meshbuf, len);
	printf("\nmodel %u: %d vertices, %d polygons, %d materials%s\n",
	       g_mesh_id, g_mesh.nvert, g_mesh.npoly, g_mesh.nmat,
	       g_mesh.stopped ? "" : "");
	if (g_mesh.stopped)
		printf("  the walk stopped: %s\n", g_mesh.stopped);
	{
		int k;
		printf("  opcodes:");
		for (k = 0; k < 0x600 / 0x20; k++)
			if (g_mesh.seen_op[k]) printf(" $%03X x%u", k * 0x20, g_mesh.seen_op[k]);
		printf("\n");
	}
}

/* ------------------------------------------------------- whole mechs in C */

static struct rig_part g_pool[RIG_PARTS];
static struct mesh g_rig, g_part;
static struct rig_place g_placed[16];
static int g_nplaced;
static float g_pbox[MESH_NODES][6];	/* where the part on each node ended up */
static uint8_t g_pboxset[MESH_NODES];

/* Decode one part into g_part. Returns zero if it is not there or draws
 * nothing, which is how the pool skips the skeletons themselves. */
static int rig_load(uint32_t id)
{
	uint32_t len = mesh_find(g_mesh_base, 0x200000u, id, g_meshbuf, sizeof g_meshbuf);

	if (!len) return 0;
	mesh_best(&g_part, g_meshbuf, len);
	return g_part.npoly > 0;
}

static void rig_summarise(void)
{
	uint32_t id;

	memset(g_pool, 0, sizeof g_pool);
	for (id = RIG_LO; id <= RIG_HI; id++) {
		struct rig_part *p = &g_pool[id - RIG_LO];
		int i, a, any = 0;

		if (!rig_load(id)) continue;
		for (a = 0; a < 3; a++) { p->lo[a] = 1e30f; p->hi[a] = -1e30f; }
		for (i = 0; i < g_part.top; i++) {
			float v[3];
			if (!g_part.vset[i]) continue;
			v[0] = g_part.vx[i]; v[1] = g_part.vy[i]; v[2] = g_part.vz[i];
			for (a = 0; a < 3; a++) {
				if (v[a] < p->lo[a]) p->lo[a] = v[a];
				if (v[a] > p->hi[a]) p->hi[a] = v[a];
			}
			any = 1;
		}
		if (!any) continue;
		memcpy(p->box, g_part.box, sizeof p->box);
		p->have = 1;
		p->nvert = g_part.nvert;
		p->npoly = g_part.npoly;
		p->self = rig_hash(&g_part, 0);
		p->mirror = rig_hash(&g_part, 1);
	}
}

/* The same part for the other side: its vertices reflected in x. */
static int rig_twin(uint32_t id)
{
	const struct rig_part *a = &g_pool[id - RIG_LO];
	uint32_t o;

	if (!a->have) return -1;
	for (o = RIG_LO; o <= RIG_HI; o++) {
		const struct rig_part *b = &g_pool[o - RIG_LO];
		if (o == id || !b->have || b->nvert != a->nvert) continue;
		if (a->mirror == b->self) return (int)o;
	}
	return -1;
}

static void rig_world(uint32_t id, const float *at, float *lo, float *hi)
{
	const struct rig_part *p = &g_pool[id - RIG_LO];
	int a;

	for (a = 0; a < 3; a++) { lo[a] = p->lo[a] + at[a]; hi[a] = p->hi[a] + at[a]; }
}

/* Place a part on a node, choosing between it and its mirror by which way
 * round touches the part already on the parent node. */
static void rig_place_on(uint32_t id, int node, const uint8_t *used_in, uint8_t *used)
{
	int twin = rig_twin(id);
	float at[3], lo[3], hi[3];
	uint32_t pick = id;
	int parent = g_rig.parent[node];

	at[0] = g_rig.nx[node]; at[1] = g_rig.ny[node]; at[2] = g_rig.nz[node];

	if (twin >= 0 && !used[twin - RIG_LO]) {
		if (used[id - RIG_LO]) {
			pick = (uint32_t)twin;
		} else if (parent >= 0 && parent < MESH_NODES && g_pboxset[parent]) {
			float alo[3], ahi[3], g1, o1, g2, o2;
			rig_world(id, at, alo, ahi);
			rig_joins(alo, ahi, &g_pbox[parent][0], &g_pbox[parent][3], &g1, &o1);
			rig_world((uint32_t)twin, at, alo, ahi);
			rig_joins(alo, ahi, &g_pbox[parent][0], &g_pbox[parent][3], &g2, &o2);
			if (g2 < g1 || (g2 == g1 && o2 < o1)) pick = (uint32_t)twin;
		}
	}
	if (!g_pool[pick - RIG_LO].have) return;

	rig_world(pick, at, lo, hi);
	memcpy(&g_pbox[node][0], lo, sizeof lo);
	memcpy(&g_pbox[node][3], hi, sizeof hi);
	g_pboxset[node] = 1;
	used[pick - RIG_LO] = 1;

	if (rig_load(pick)) rig_add(&g_rig, &g_part, at);
	if (g_nplaced < 16) {
		g_placed[g_nplaced].node = node;
		g_placed[g_nplaced].id = pick;
		memcpy(g_placed[g_nplaced].at, at, sizeof at);
		g_nplaced++;
	}
	(void)used_in;
}

/* Build a whole mech on skeleton `skel`. Returns how many parts went on. */
static int rig_assemble(uint32_t skel)
{
	uint8_t used[RIG_PARTS];
	float kid[MESH_NODES][3];
	uint8_t haskid[MESH_NODES];
	uint32_t len;
	int node, legs_lo = 0;

	memset(&g_rig, 0, sizeof g_rig);
	memset(used, 0, sizeof used);
	memset(haskid, 0, sizeof haskid);
	memset(g_pboxset, 0, sizeof g_pboxset);
	g_nplaced = 0;

	len = mesh_find(g_mesh_base, 0x200000u, skel, g_meshbuf, sizeof g_meshbuf);
	if (!len) return 0;
	{
		static struct mesh rig;
		mesh_run(&rig, g_meshbuf, len);
		if (!rig.nnode) return 0;
		/* Keep the skeleton's pose; the assembly's own geometry starts empty. */
		memcpy(g_rig.nx, rig.nx, sizeof rig.nx);
		memcpy(g_rig.ny, rig.ny, sizeof rig.ny);
		memcpy(g_rig.nz, rig.nz, sizeof rig.nz);
		memcpy(g_rig.parent, rig.parent, sizeof rig.parent);
		memcpy(g_rig.ox, rig.ox, sizeof rig.ox);
		memcpy(g_rig.oy, rig.oy, sizeof rig.oy);
		memcpy(g_rig.oz, rig.oz, sizeof rig.oz);
		memcpy(g_rig.slot, rig.slot, sizeof rig.slot);
		memcpy(g_rig.nset, rig.nset, sizeof rig.nset);
		g_rig.nnode = rig.nnode;
		for (node = 0; node < MESH_NODES; node++) {
			int par;
			if (!rig.nset[node]) continue;
			par = rig.parent[node];
			if (par < 0 || par >= MESH_NODES || haskid[par]) continue;
			kid[par][0] = rig.ox[node];
			kid[par][1] = rig.oy[node];
			kid[par][2] = rig.oz[node];
			haskid[par] = 1;
		}
	}

	rig_summarise();

	/* The torso always hangs on node 2: on a chassis with no shoulder nodes
	 * there is no child offset to match against, and where there is one,
	 * several parts contain it and the smallest is not the torso. */
	if (skel + 10 >= RIG_LO && skel + 10 <= RIG_HI && g_pool[skel + 10 - RIG_LO].have)
		rig_place_on(skel + 10, 2, used, used);

	for (node = 0; node < MESH_NODES; node++) {
		uint32_t id, best = 0;
		float bestvol = 1e30f;

		if (node == 2 || !g_rig.nset[node] || !haskid[node]) continue;
		for (id = RIG_LO; id <= RIG_HI; id++) {
			struct rig_part *p = &g_pool[id - RIG_LO];
			float v;
			if (!p->have || used[id - RIG_LO]) continue;
			if (!rig_inside(p, kid[node])) continue;
			v = rig_volume(p);
			if (v < bestvol) { bestvol = v; best = id; }
		}
		if (best) rig_place_on(best, node, used, used);
	}

	/* Feet. The leg parts all came out of one contiguous block of seven ids;
	 * whatever of that block is still unused is the pair of feet. A foot node
	 * has nothing below it, so there is no offset to match. */
	{
		int i;
		for (i = 0; i < g_nplaced; i++)
			if (g_placed[i].node != 2 &&
			    (!legs_lo || (int)g_placed[i].id < legs_lo))
				legs_lo = (int)g_placed[i].id;
	}
	if (legs_lo) {
		for (node = 0; node < MESH_NODES; node++) {
			uint32_t id, best = 0;
			float bestvol = 1e30f;

			if (node == 2 || !g_rig.nset[node] || haskid[node]) continue;
			for (id = (uint32_t)legs_lo; id < (uint32_t)legs_lo + 7 && id <= RIG_HI; id++) {
				struct rig_part *p = &g_pool[id - RIG_LO];
				float v;
				if (!p->have || used[id - RIG_LO]) continue;
				v = rig_volume(p);
				if (v < bestvol) { bestvol = v; best = id; }
			}
			if (best) rig_place_on(best, node, used, used);
		}
	}
	return g_nplaced;
}

/* Every chassis assembled, to sit beside tools/render.py --mechs. The two
 * are separate ports of one set of placement rules and have to agree. */
static void rig_all(void)
{
	uint32_t skel;
	int whole = 0, parts = 0;
	long polys = 0;

	for (skel = 451; skel <= 456; skel++) {
		int n = rig_assemble(skel);
		if (!n) continue;
		parts += n;
		polys += g_rig.npoly;
		whole += n >= 8;
	}
	printf("\nchassis assembled whole in C: %d\n", whole);
	printf("parts placed in C           : %d\n", parts);
	printf("mech polygons in C          : %ld\n", polys);
}


/* ---------------------------------------------------------------- scenes */

static struct scene g_scene;
static const char *g_scenefile;
static const char *g_sceneout;
static float g_sceneturn = 0.7f, g_scenepitch = -0.28f, g_scenezoom = 0.9f;
static int g_scenedrop = -1;
static struct mesh g_kindmesh[SCENE_KINDS];
static uint8_t g_kindok[SCENE_KINDS];

/* Decode each distinct model a map uses, once. A scenario places the same
 * handful of resources hundreds of times, so this is a small cache rather than
 * a mesh per object. */
static int scene_prepare(void)
{
	int i, ok = 0;

	for (i = 0; i < g_scene.nkind; i++) {
		uint32_t len = mesh_find(g_mesh_base, 0x200000u, (uint32_t)g_scene.kind[i],
					 g_meshbuf, sizeof g_meshbuf);
		if (!len) continue;
		mesh_best(&g_kindmesh[i], g_meshbuf, len);
		g_kindok[i] = g_kindmesh[i].npoly > 0;
		ok += g_kindok[i];
	}
	return ok;
}

static int scene_kind(int model)
{
	int i;

	for (i = 0; i < g_scene.nkind; i++)
		if (g_scene.kind[i] == model) return i;
	return -1;
}

static struct raster g_sceneframe;

/* Draw the whole map. Each object carries its own position, heading and scale,
 * so one decoded model is drawn many times - which is what the display list
 * does too, and why the rasteriser takes a placement rather than a merged
 * mesh. */
static int scene_draw_cam(const struct ras_cam *camin, float floor)
{
	int i, drawn = 0;

	ras_background(&g_sceneframe, (int)(RAS_H * 0.52f));
	for (i = 0; i < g_scene.n; i++) {
		int k = scene_kind(g_scene.obj[i].model);
		if (k < 0 || !g_kindok[k]) continue;
		drawn += ras_draw_at(&g_sceneframe, &g_kindmesh[k], camin,
				     &g_scene.obj[i].at, floor, 0);
	}
	return drawn;
}

static int scene_draw(float turn, float pitch, float zoom)
{
	struct ras_cam cam;
	float floor;
	int i, drawn = 0;

	{
		/* Pad the frame by the biggest model the map uses, at its
		 * largest scale, so nothing at the edge is cut and a one-object
		 * scene still has somewhere to stand. */
		float pad = 0.0f;
		int i;
		for (i = 0; i < g_scene.n; i++) {
			int k = scene_kind(g_scene.obj[i].model);
			float r;
			if (k < 0 || !g_kindok[k]) continue;
			r = g_kindmesh[k].box[6] * g_scene.obj[i].at.scale;
			if (r > pad) pad = r;
		}
		scene_frame(&g_scene, &cam, &floor, pad);
	}
	cam.turn = turn;
	cam.pitch = pitch;
	cam.dist *= zoom;
	ras_background(&g_sceneframe, (int)(RAS_H * 0.52f));
	for (i = 0; i < g_scene.n; i++) {
		int k = scene_kind(g_scene.obj[i].model);
		if (k < 0 || !g_kindok[k]) continue;
		drawn += ras_draw_at(&g_sceneframe, &g_kindmesh[k], &cam,
				     &g_scene.obj[i].at, floor, 0);
	}
	return drawn;
}

static void scene_report(void)
{
	int i, drew;

	if (!scene_load(&g_scene, g_scenefile)) {
		printf("\ncannot read scenario %s\n", g_scenefile);
		return;
	}
	drew = scene_prepare();
	printf("\nscenario %s\n", g_scenefile);
	printf("scenario objects placed  : %d\n", g_scene.n);
	printf("scenario models used     : %d\n", g_scene.nkind);
	printf("scenario models decoded  : %d\n", drew);
	printf("  models used:");
	for (i = 0; i < g_scene.nkind; i++)
		printf(" %d%s", g_scene.kind[i], g_kindok[i] ? "" : "(no geometry)");
	printf("\n");

	printf("scenario drop points     : %d\n", g_scene.ndrop);

	if (g_sceneout) {
		int poly;
		if (g_scenedrop >= 0) {
			struct ras_cam cam;
			float floor;
			scene_stand(&g_scene, g_scenedrop, &cam, &floor);
			poly = scene_draw_cam(&cam, floor);
		} else {
			poly = scene_draw(g_sceneturn, g_scenepitch, g_scenezoom);
		}
		FILE *f = fopen(g_sceneout, "wb");
		if (f) {
			fwrite(g_sceneframe.px, 1, sizeof g_sceneframe.px, f);
			fclose(f);
			printf("  %s: %dx%d, %d polygons drawn\n",
			       g_sceneout, RAS_W, RAS_H, poly);
		}
	}
}

/* What the pod put in a frame, kept so it can be drawn afterwards: the draw
 * object's camera and every type 3 record. A type 3 is a whole model placed
 * in the world - the viewer's own, and each Mech the world pass lets through
 * the culler - so a frame is fully described, for our purposes, by these. */
#define FRAME_OBJS 1024
#define FRAME_POSES 64
#define MECH_SLOTS 15
#define MECH_POSE 94			/* record word of slot 1's transform */
struct pod_frame {
	int have_cam, seq;
	float cam[12];			/* 3x3 rotation, then the eye, display-list axes */
	int n;
	struct { uint32_t entity, model, arms; int pose; float rot[9], at[3]; } obj[FRAME_OBJS];
	/* A Mech's record carries fifteen instance transforms from word 94, a
	 * 3x3 and a translation each, one per skeleton slot: the pose. */
	int npose;
	float pose[FRAME_POSES][MECH_SLOTS][12];
};
static struct pod_frame g_frame_cur, g_frame_last;
static struct pod_frame g_frame_latest;	/* the last complete list, placed or not */
static int g_capture;		/* walk every list, for the live view */
static int g_frames_walked;
static int g_frame_at;		/* --frame-at: the list to draw, not the last */
static const char *g_frameout;

/* Every model a frame names, decoded once. A skeleton goes through the rig
 * assembler and comes out a whole mech; anything else is one model; a model
 * with no geometry is remembered as such so it is not decoded again. */
#define MCACHE 128
static struct { uint32_t id; struct mesh *m; } g_mcache[MCACHE];
static int g_mcache_n;

/* The arms. A Mech's own record in the display list carries, from word 31,
 * the variables its models' predicates test, and two models read them: 516
 * draws the right arm, 501 + (var 4 - 1), unless var 44 - the Right Arm's
 * sub-part, its intact value - is zero, and 517 the left, 511 + (var 6 - 1)
 * on var 46. Vars 4 and 6 are the vehicle record's +0x2C and +0x2E, one to
 * five; five decodes to nothing, which is a chassis with no arm. Each hangs
 * where 516/517's own $040 puts it, (+-1.38, 1.80, -1.50) from the Mech's
 * root, through an instance transform that is identity at rest.
 * RENDERING.md, *The arms*. */
#define MECH_VARS 31			/* record word of var 0 */

static uint32_t dl_word(uint32_t ti_byte_addr, uint32_t i);

/* --mech-dump FILE: every Mech's record in every list, one line each - the
 * list number, then the record's words in hex - for finding what moves when
 * a Mech turns, walks or aims. A %d in FILE becomes the pod's node. */
static const char *g_mechdump_path;
static int g_netnode;			/* defined with --net's state below */
static FILE *g_mechdump;

static void mech_dump(uint32_t ti_byte_addr, uint32_t at, uint32_t len)
{
	uint32_t k;

	if (!g_mechdump) {
		char path[512];
		snprintf(path, sizeof path, g_mechdump_path, g_netnode);
		if (!(g_mechdump = fopen(path, "w"))) { g_mechdump_path = NULL; return; }
	}
	fprintf(g_mechdump, "%d", g_frames_walked);
	for (k = 2; k < len; k++) fprintf(g_mechdump, " %X", dl_word(ti_byte_addr, at + k));
	fputc('\n', g_mechdump);
}

static uint32_t mech_arms(uint32_t ti_byte_addr, uint32_t at, uint32_t len)
{
	uint32_t r, l;

	if (len <= MECH_VARS + 46) return 0;
	r = dl_word(ti_byte_addr, at + MECH_VARS + 4);
	l = dl_word(ti_byte_addr, at + MECH_VARS + 6);
	if (!dl_word(ti_byte_addr, at + MECH_VARS + 44) || r < 1 || r > 5) r = 0;
	if (!dl_word(ti_byte_addr, at + MECH_VARS + 46) || l < 1 || l > 5) l = 0;
	return r | l << 4;
}

/* One model, seen close and whole (MESH_NEAR), added at `at`. */
static void rig_near(uint32_t id, const float *at)
{
	uint32_t len = mesh_find(g_mesh_base, 0x200000u, id, g_meshbuf, sizeof g_meshbuf);

	if (!len) return;
	mesh_run_mode(&g_part, g_meshbuf, len, MESH_NEAR);
	rig_add(&g_rig, &g_part, at);
}

static void rig_arms(uint32_t arms)
{
	static const float root[3] = { 0, 0, 0 };
	static const float hang[2][3] = { { 1.38f, 1.80f, -1.50f }, { -1.38f, 1.80f, -1.50f } };
	int side;

	for (side = 0; side < 2; side++) {
		uint32_t v = (arms >> (side * 4)) & 15;
		if (!v) continue;
		rig_near(516 + side, root);		/* the shoulder: its own polygons */
		rig_near(500 + side * 10 + v, hang[side]);	/* the arm it chose */
	}
}

/* A Mech posed by its frame. Its parts are kept apart rather than welded
 * into one mesh, each with the node it hangs on, and every frame each node
 * is composed as its parent, then its offset, then its instance transform
 * from the record - the order $040 names them in. At rest the transforms
 * are identity and this is the same Mech model_mesh assembles. The arms
 * hang on two extra nodes off the root, through instances 5 and 3, which is
 * what 516 and 517 say. RENDERING.md, *The pose*. */
#define POSE_NODES (MESH_NODES + 2)
#define POSE_PARTS 24
#define POSE_RIGS 16
static struct pose_rig {
	uint32_t key;
	int n;
	int node[POSE_PARTS];
	struct mesh *m[POSE_PARTS];
	int16_t parent[POSE_NODES];
	float o[POSE_NODES][3];
	uint8_t slot[POSE_NODES], set[POSE_NODES];
} g_pose_rig[POSE_RIGS];
static int g_pose_rigs;

static void pose_keep(struct pose_rig *pr, int node, const struct mesh *m)
{
	struct mesh *c;

	if (pr->n >= POSE_PARTS || !(c = malloc(sizeof *c))) return;
	memcpy(c, m, sizeof *c);
	pr->node[pr->n] = node;
	pr->m[pr->n++] = c;
}

static struct pose_rig *pose_rig(uint32_t id, uint32_t arms)
{
	static const float hang[2][3] = { { 1.38f, 1.80f, -1.50f }, { -1.38f, 1.80f, -1.50f } };
	uint32_t key = id | arms << 16;
	struct pose_rig *pr;
	int i, side;

	for (i = 0; i < g_pose_rigs; i++)
		if (g_pose_rig[i].key == key) return &g_pose_rig[i];
	if (g_pose_rigs >= POSE_RIGS) return NULL;
	pr = &g_pose_rig[g_pose_rigs++];
	memset(pr, 0, sizeof *pr);
	pr->key = key;
	rig_assemble(id);
	for (i = 0; i < MESH_NODES; i++) {
		pr->set[i] = g_rig.nset[i];
		pr->parent[i] = g_rig.parent[i];
		pr->o[i][0] = g_rig.ox[i]; pr->o[i][1] = g_rig.oy[i]; pr->o[i][2] = g_rig.oz[i];
		pr->slot[i] = g_rig.slot[i];
	}
	pr->set[0] = 1;
	for (i = 0; i < g_nplaced; i++)
		if (rig_load(g_placed[i].id)) pose_keep(pr, g_placed[i].node, &g_part);
	for (side = 0; side < 2; side++) {
		uint32_t v = (arms >> (side * 4)) & 15, len;
		int nd = MESH_NODES + side;
		if (!v) continue;
		pr->set[nd] = 1;
		pr->parent[nd] = 0;
		memcpy(pr->o[nd], hang[side], sizeof hang[side]);
		pr->slot[nd] = side ? 3 : 5;
		if ((len = mesh_find(g_mesh_base, 0x200000u, 516 + side, g_meshbuf, sizeof g_meshbuf))) {
			mesh_run_mode(&g_part, g_meshbuf, len, MESH_NEAR);
			pose_keep(pr, 0, &g_part);
		}
		if ((len = mesh_find(g_mesh_base, 0x200000u, 500 + side * 10 + v, g_meshbuf, sizeof g_meshbuf))) {
			mesh_run_mode(&g_part, g_meshbuf, len, MESH_NEAR);
			pose_keep(pr, nd, &g_part);
		}
	}
	return pr;
}

/* Node `nd`'s rotation r (3x3, rows) and position t, in model space. */
static void pose_node(const struct pose_rig *pr, const float (*inst)[12], int nd,
		      float *r, float *t, int depth)
{
	static const float id3[9] = { 1, 0, 0, 0, 1, 0, 0, 0, 1 };
	float pr_r[9], pr_t[3], o[3];
	const float *k = NULL;
	int a, b;

	if (nd <= 0 || nd >= POSE_NODES || !pr->set[nd] || depth > 16) {
		memcpy(r, id3, sizeof id3);
		t[0] = t[1] = t[2] = 0;
		return;
	}
	pose_node(pr, inst, pr->parent[nd], pr_r, pr_t, depth + 1);
	if (pr->slot[nd] >= 1 && pr->slot[nd] <= MECH_SLOTS)
		k = inst[pr->slot[nd] - 1];
	for (a = 0; a < 3; a++)
		o[a] = pr->o[nd][a] + (k ? k[9 + a] : 0);
	/* The record stores each transform by columns, so k[b * 3 + a] is row a
	 * column b; transposed, composed onto the parent. RENDERING.md, *The pose*. */
	for (a = 0; a < 3; a++) {
		t[a] = pr_t[a] + pr_r[a * 3] * o[0] + pr_r[a * 3 + 1] * o[1] + pr_r[a * 3 + 2] * o[2];
		for (b = 0; b < 3; b++)
			r[a * 3 + b] = !k ? pr_r[a * 3 + b] :
				pr_r[a * 3] * k[b * 3] + pr_r[a * 3 + 1] * k[b * 3 + 1] + pr_r[a * 3 + 2] * k[b * 3 + 2];
	}
}

static const struct mesh *mech_posed(uint32_t id, uint32_t arms, const float (*inst)[12])
{
	static struct mesh out;
	struct pose_rig *pr = pose_rig(id, arms);
	int i;

	if (!pr) return NULL;
	memset(&out, 0, sizeof out);
	for (i = 0; i < pr->n; i++) {
		float r[9], t[3];
		pose_node(pr, inst, pr->node[i], r, t, 0);
		rig_add_xf(&out, pr->m[i], r, t);
	}
	return &out;
}

static const struct mesh *model_mesh(uint32_t id, uint32_t arms)
{
	const struct mesh *src = NULL;
	struct mesh *m = NULL;
	uint32_t key = id | arms << 16;
	int i;

	for (i = 0; i < g_mcache_n; i++)
		if (g_mcache[i].id == key) return g_mcache[i].m;
	if (id >= 451 && id <= 456) {
		rig_assemble(id);
		rig_arms(arms);
		src = &g_rig;
	} else if (rig_load(id)) {
		src = &g_part;
	}
	if (src && (m = malloc(sizeof *m)) != NULL) memcpy(m, src, sizeof *m);
	if (g_mcache_n < MCACHE) {
		g_mcache[g_mcache_n].id = key;
		g_mcache[g_mcache_n].m = m;
		g_mcache_n++;
	}
	return m;
}

/* Draw a captured frame from the pod's own camera. The display list's axes
 * are (X, height, -Y); the rasteriser's world is (X, height, Y), so the third
 * axis flips on the way in. The camera looks along the third row of the draw
 * object's matrix - measured, not assumed: that row is (0, 0, -1) for the
 * heading at which the culler lets the Mech through, and the Mech lies in
 * that direction. The viewer's own record, which sits at the eye, is skipped.
 * Joint angles are not applied: the stance is the rig's rest pose. Says what
 * it drew when `log` is set; returns the polygons drawn. */
static int frame_draw(struct raster *r, const struct pod_frame *fr, int *models, int log)
{
	struct ras_cam cam;
	float fx, fy, fz, eye[3];
	int i, poly = 0;

	*models = 0;
	eye[0] = fr->cam[9]; eye[1] = fr->cam[10]; eye[2] = -fr->cam[11];
	fx = fr->cam[6]; fy = fr->cam[7]; fz = -fr->cam[8];
	memset(&cam, 0, sizeof cam);
	memcpy(cam.centre, eye, sizeof eye);
	cam.turn = atan2f(-fx, fz);
	cam.pitch = atan2f(fy, sqrtf(fx * fx + fz * fz));
	cam.dist = 0;
	if (log) {
		printf("list %d of %d walked; ", fr->seq, g_frames_walked);
		printf("eye (%.1f, %.1f, %.1f) height %.2f, turn %.1f deg, %d models\n",
		       eye[0], eye[2], 0.0f, eye[1], cam.turn * 57.29578f, fr->n);
	}

	ras_background(r, RAS_H / 2);
	for (i = 0; i < fr->n; i++) {
		struct ras_place at;
		const struct mesh *m;
		uint32_t id = fr->obj[i].model;
		float dx = fr->obj[i].at[0] - eye[0], dz = -fr->obj[i].at[2] - eye[2];
		int n;

		if (dx * dx + dz * dz < 1.0f) {
			if (log) printf("  entity %u model %u: at the eye, not drawn\n",
					fr->obj[i].entity, id);
			continue;
		}
		if (id >= 451 && id <= 456 && fr->obj[i].pose >= 0)
			m = mech_posed(id, fr->obj[i].arms, fr->pose[fr->obj[i].pose]);
		else
			m = model_mesh(id, fr->obj[i].arms);
		if (!m) {
			if (log) printf("  entity %u model %u: no geometry\n", fr->obj[i].entity, id);
			continue;
		}
		at.x = fr->obj[i].at[0];
		at.y = -fr->obj[i].at[2];
		at.z = fr->obj[i].at[1];
		at.heading = atan2f(fr->obj[i].rot[2], fr->obj[i].rot[0]);
		at.scale = 1.0f;
		n = ras_draw_at(r, m, &cam, &at, 0.0f, 1);
		if (log) printf("  entity %u model %u at (%.1f, %.1f, %.1f): %d polygons\n",
				fr->obj[i].entity, id, at.x, at.y, at.z, n);
		poly += n;
		(*models)++;
	}
	return poly;
}

/* ------------------------------------------------------------ live windows */

/* The cockpit with its panel lit, in one process, while the firmware runs.
 *
 * Built only into `cockpit.exe`; `battlepod.exe` is the same source without
 * SDL, so the batch tool and the harness stay free of it. The windows draw the
 * same `struct rio_panel` the batch decoder fills, from the same byte stream
 * the firmware puts on DUART channel A - the emulator does not know it is
 * being watched, and the drawing does not know where the bytes came from.
 */
#ifdef BATTLEPOD_SDL

#include "paneldraw.h"

#define LIVE_EVERY 200000		/* instructions between pumps */

static int g_live;
static int g_mesh_ready;
static struct mesh *g_draw;
static SDL_Window *g_lw[NPANELS];
static SDL_Renderer *g_lr[NPANELS];
static SDL_Window *g_vw;
static SDL_Renderer *g_vr;
static SDL_Texture *g_vt;
static uint8_t *g_frames_buf;
static long g_frames_n;
static int g_view_w = 480, g_view_h = 360;
static uint32_t g_live_at;		/* how far the panel has been walked */
static int g_quit;

static int live_open(const char *frames)
{
	int i;

	if (SDL_Init(SDL_INIT_VIDEO) != 0) {
		fprintf(stderr, "SDL_Init: %s\n", SDL_GetError());
		return 0;
	}
	for (i = 0; i < NPANELS; i++) {
		g_lw[i] = SDL_CreateWindow(PANELS[i].title, SDL_WINDOWPOS_UNDEFINED,
					   SDL_WINDOWPOS_UNDEFINED, PANELS[i].w,
					   PANELS[i].h, SDL_WINDOW_RESIZABLE);
		if (!g_lw[i]) { fprintf(stderr, "SDL_CreateWindow: %s\n", SDL_GetError()); return 0; }
		g_lr[i] = SDL_CreateRenderer(g_lw[i], -1, SDL_RENDERER_ACCELERATED);
		if (!g_lr[i]) g_lr[i] = SDL_CreateRenderer(g_lw[i], -1, 0);
		SDL_RenderSetLogicalSize(g_lr[i], PANELS[i].w, PANELS[i].h);
	}

	/* The main view is fed from a file of raw frames for now, because the
	 * rasteriser is still tools/render.py. When it is C in this process the
	 * texture stays and only the source changes. */
	if (frames) {
		FILE *f = fopen(frames, "rb");
		long n, one = (long)g_view_w * g_view_h * 3;
		if (!f) { fprintf(stderr, "cannot open %s\n", frames); return 1; }
		fseek(f, 0, SEEK_END); n = ftell(f); fseek(f, 0, SEEK_SET);
		g_frames_n = one > 0 ? n / one : 0;
		if (g_frames_n > 0) {
			g_frames_buf = malloc((size_t)n);
			if (!g_frames_buf || fread(g_frames_buf, 1, (size_t)n, f) != (size_t)n) {
				free(g_frames_buf);
				g_frames_buf = NULL;
				g_frames_n = 0;
			}
		}
		fclose(f);
	}
	if (g_frames_n > 0 || g_mesh_id || g_rig_id || g_capture) {
		g_vw = SDL_CreateWindow("battlepod - main view", SDL_WINDOWPOS_UNDEFINED,
					SDL_WINDOWPOS_UNDEFINED, g_view_w * 2, g_view_h * 2,
					SDL_WINDOW_RESIZABLE);
		g_vr = SDL_CreateRenderer(g_vw, -1, SDL_RENDERER_ACCELERATED);
		if (!g_vr) g_vr = SDL_CreateRenderer(g_vw, -1, 0);
		SDL_RenderSetLogicalSize(g_vr, g_view_w, g_view_h);
		g_vt = SDL_CreateTexture(g_vr, SDL_PIXELFORMAT_RGB24,
					 SDL_TEXTUREACCESS_STREAMING, g_view_w, g_view_h);
	}
	if (g_rig_id) {
		rig_assemble(g_rig_id);
		g_draw = &g_rig;
		g_mesh_ready = g_rig.npoly > 0;
	} else if (g_mesh_id) {
		uint32_t len = mesh_find(g_mesh_base, 0x200000u, g_mesh_id,
					 g_meshbuf, sizeof g_meshbuf);
		if (len) {
			mesh_run(&g_mesh, g_meshbuf, len);
			g_draw = &g_mesh;
			g_mesh_ready = g_mesh.npoly > 0;
		}
		if (!g_mesh_ready)
			fprintf(stderr, "model %u has nothing to draw\n", g_mesh_id);
	}
	return 1;
}

/* --live-pod: the keyboard is the cockpit. Keys become the panel's own input
 * reports - C0 id value for an analog, B1/B0 id for a button - framed as the
 * Remote I/O board frames them and appended to what DUART channel A has left
 * to deliver.
 *
 *   W / S      throttle up / down, in eighths (analog A0, 0 to 0x340)
 *   A / D      stick left / right (A1 / A2); the first key also selects
 *              advanced mode and "stick turns" (buttons 33 and 31), in which
 *              the stick steers
 *   space      trigger (button A5)
 *   T          target select (button 40)
 *   L          searchlight (button 20)
 */

static int  g_live_throttle, g_live_moded;


static void live_report(const uint8_t *d, int n)
{
	uint8_t f[4 + 16 + 1], sum = 0;
	int i;

	if (n > 16) return;
	f[0] = 0x01; f[1] = 0x00; f[2] = (uint8_t)n; f[3] = (uint8_t)n;
	for (i = 0; i < n; i++) {
		f[4 + i] = d[i];
		sum += d[i];
	}
	f[4 + n] = sum;
	rx_append(f, (size_t)n + 5);
}

static void live_analog(uint8_t id, int v)
{
	uint8_t d[4] = { 0xC0, id, (uint8_t)(v >> 8), (uint8_t)v };
	live_report(d, 4);
}

static void live_button(uint8_t id, int down)
{
	uint8_t d[2] = { (uint8_t)(down ? 0xB1 : 0xB0), id };
	live_report(d, 2);
}

static void live_key(SDL_Keycode k, int down, int repeat)
{
	if (down && !repeat && !g_live_moded &&
	    (k == SDLK_a || k == SDLK_d)) {
		live_button(0x33, 1); live_button(0x33, 0);
		live_button(0x31, 1); live_button(0x31, 0);
		g_live_moded = 1;
	}
	switch (k) {
	case SDLK_w: case SDLK_s:
		if (!down) break;
		g_live_throttle += (k == SDLK_w ? 0x68 : -0x68);
		if (g_live_throttle < 0) g_live_throttle = 0;
		if (g_live_throttle > 0x340) g_live_throttle = 0x340;
		live_analog(0xA0, g_live_throttle);
		break;
	case SDLK_a: if (!repeat) live_analog(0xA1, down ? 0x80 : 0); break;
	case SDLK_d: if (!repeat) live_analog(0xA2, down ? 0x80 : 0); break;
	case SDLK_SPACE: if (!repeat) live_button(0xA5, down); break;
	case SDLK_t: if (!repeat) live_button(0x40, down); break;
	case SDLK_l: if (!repeat) live_button(0x20, down); break;
	default: break;
	}
}

/* Called from the run loop. Walks whatever new Remote I/O bytes the firmware
 * has put on the wire since last time, redraws, and pumps events. */
static void live_pump(uint64_t step)
{
	uint32_t have = g_rio_tx < RIOCAP ? g_rio_tx : RIOCAP;
	SDL_Event e;
	int i;

	if (have > g_live_at)
		g_live_at += rio_walk(&g_panel, g_riobuf + g_live_at, have - g_live_at);

	while (SDL_PollEvent(&e)) {
		if (e.type == SDL_QUIT) g_quit = 1;
		if (e.type == SDL_KEYDOWN && e.key.keysym.sym == SDLK_ESCAPE) g_quit = 1;
		if (g_capture && (e.type == SDL_KEYDOWN || e.type == SDL_KEYUP))
			live_key(e.key.keysym.sym, e.type == SDL_KEYDOWN, e.key.repeat);
	}
	if (g_vt && g_capture) {
		/* The pod's own latest frame, drawn from its own camera. */
		static struct raster f;
		static int drawn_seq = -1;
		int models;
		if (g_frame_latest.have_cam && g_frame_latest.seq != drawn_seq) {
			frame_draw(&f, &g_frame_latest, &models, 0);
			drawn_seq = g_frame_latest.seq;
			SDL_UpdateTexture(g_vt, NULL, f.px, RAS_W * 3);
			SDL_RenderClear(g_vr);
			SDL_RenderCopy(g_vr, g_vt, NULL, NULL);
			SDL_RenderPresent(g_vr);
		}
	}

	for (i = 0; i < NPANELS; i++) {
		PANELS[i].draw(g_lr[i], &g_panel);
		SDL_RenderPresent(g_lr[i]);
	}
	if (g_vt && g_mesh_ready) {
		/* Drawn here and now, by src/raster.h, from geometry src/mesh.h took
		 * out of the archive sitting in the emulator's own memory. Nothing
		 * on disk, nothing from Python. */
		static struct raster f;
		struct ras_cam cam;
		float floor;

		ras_frame_on(g_draw, &cam, 3.4f, &floor);
		cam.turn = (float)((step / (double)LIVE_EVERY) * 0.04);
		cam.pitch = 0.10f;
		ras_draw(&f, g_draw, &cam, floor, 1);
		SDL_UpdateTexture(g_vt, NULL, f.px, RAS_W * 3);
		SDL_RenderClear(g_vr);
		SDL_RenderCopy(g_vr, g_vt, NULL, NULL);
		SDL_RenderPresent(g_vr);
	} else if (g_vt && g_frames_n > 0) {
		long at = (long)((step / LIVE_EVERY) % (uint64_t)g_frames_n);
		SDL_UpdateTexture(g_vt, NULL,
				  g_frames_buf + at * (long)g_view_w * g_view_h * 3,
				  g_view_w * 3);
		SDL_RenderClear(g_vr);
		SDL_RenderCopy(g_vr, g_vt, NULL, NULL);
		SDL_RenderPresent(g_vr);
	}
	{
		char t[96];
		snprintf(t, sizeof t, "%s  -  %u frames, %llu instructions",
			 PANELS[0].title, g_panel.frames, (unsigned long long)step);
		SDL_SetWindowTitle(g_lw[0], t);
	}
}

/* The emulator outruns the cockpit by a wide margin - a budget that would be
 * minutes of pod time goes by in seconds - so when the run ends the windows
 * stay up with the panel in its final state until they are closed. */
static void live_hold(uint64_t step)
{
	uint64_t spin = step;

	if (g_clock_rt)
		printf("\nlive clock: timebase %u, wall %u (hundredths)\n",
		       g_clock_val, g_clock_wall);
	if (getenv("BATTLEPOD_NO_HOLD")) return;	/* headless: nobody to close it */
	while (!g_quit) {
		live_pump(spin);
		spin += LIVE_EVERY;
		SDL_Delay(33);
	}
}

static void live_close(void)
{
	int i;

	for (i = 0; i < NPANELS; i++) {
		if (g_lr[i]) SDL_DestroyRenderer(g_lr[i]);
		if (g_lw[i]) SDL_DestroyWindow(g_lw[i]);
	}
	if (g_vt) SDL_DestroyTexture(g_vt);
	if (g_vr) SDL_DestroyRenderer(g_vr);
	if (g_vw) SDL_DestroyWindow(g_vw);
	free(g_frames_buf);
	SDL_Quit();
}

#endif /* BATTLEPOD_SDL */

/* ---------------------------------------------------- boot monitor stub */

/* The pod's boot ROM is not in the release, but the firmware calls it. Six
 * thunks at 0x0212C72C dispatch through [[0x0216FADE] + n], and that pointer
 * is statically 0x02000400 - immediately after the vector table at VBR, with
 * a globals block at 0x02000800 passed in A6. So the monitor exports a service
 * table right above its vectors.
 *
 * This installs a table of stubs that return "nothing, no error", which is a
 * safe answer for a poll, and counts which slots the firmware actually calls -
 * that enumeration is the monitor's API surface. */

#define MON_SLOTS    32
#define MON_STUB_OFF  0x200
#define MON_STUB_SZ   16
/* The received-packet buffer sits past the stubs. It used to be at +0x400,
 * which put the packet body at 0x02000804 with the default monitor base - and
 * the firmware's timebase is at 0x02000808, four bytes into it. So
 * `--clock` overwrote bytes 4 through 7 of every injected packet with a
 * counter, and any handler reading a field there saw the clock. `0xF8`'s
 * create selector is at +0x02 and spans into that hole, which is why it could
 * never be set from the wire. Moved clear; `mon_install` now refuses to let
 * the two overlap silently. */
#define MON_PKT_OFF   0x600		/* received-packet buffer, past the stubs */
#define MON_SLOT_RECV 6			/* +0x18: poll for a received packet */
#define MON_SLOT_SEND 9			/* +0x24: transmit, D0 node, D1 length, A0 buffer */

/* --send-log: every packet the pod transmits, one per line - the timebase,
 * the node it went to, then the bytes from the opcode on - in the form
 * --packet-file reads, so one pod's traffic can be fed to another. The
 * sender at 0x021468A4 reaches the monitor's +0x24 through 0x0212C78E; a
 * zero back is success, which the stub already returns. */
static FILE *g_sendlog;
static uint32_t g_sent;

static void mon_send_called(void)
{
	uint32_t node = m68k_get_reg(NULL, M68K_REG_D0) & 0xFFFF;
	uint32_t len = m68k_get_reg(NULL, M68K_REG_D1) & 0xFFFF;
	uint32_t buf = m68k_get_reg(NULL, M68K_REG_A0), i;
	uint32_t now = m68k_read_memory_32(0x02000808);

	g_sent++;
	if (len > 512) len = 512;
	if (g_net) {
		uint8_t pkt[512];
		for (i = 0; i < len; i++) pkt[i] = (uint8_t)m68k_read_memory_8(buf + i);
		net_send_packet(node, pkt, len);
	}
	if (!g_sendlog) return;
	fprintf(g_sendlog, "# t %u node %u\n", now, node);
	for (i = 0; i < len; i++)
		fprintf(g_sendlog, "%02X%s", m68k_read_memory_8(buf + i), i + 1 < len ? " " : "\n");
}

static uint32_t g_mon, g_monstub;
static uint32_t g_clock_addr;	/* defined with --clock below; checked here */
static uint32_t g_moncall[MON_SLOTS];
/* The mission interpreter's fetch-decode loop dispatches on D0. Logging that
 * register at one address gives the exact opcode stream a mission executes,
 * which is the only ground truth there is for a bytecode disassembler working
 * from operand lengths it inferred. */
#define VMTRACE_PC  0x021198A6u
#define VMTRACE_MAX 8192
static uint32_t g_vmtrace;
static unsigned g_vmtrace_n;
static uint8_t  g_vmops[VMTRACE_MAX];
/* The interpreter's bytecode program counter is a pointer in its own frame at
 * `(-$10e,A6)` - that is the cell every operand-taking arm steps with
 * `addq.l #1`. Logging it alongside the opcode turns the opcode stream into
 * something a disassembly can be lined up against, which is what it takes to
 * find the loop in a trace of eight thousand instructions. */
#define VMTRACE_FRAME_PC (-0x10e)
static uint32_t g_vmpcs[VMTRACE_MAX];

#define MAX_PKTS 8192			/* a whole map, or a recorded pod's traffic */
static uint8_t  g_pkt[MAX_PKTS][512];
static uint32_t g_pktlen[MAX_PKTS];

/* Queue one packet written as hex bytes. */
static int pkt_add(const char *h)
{
	if (g_npkts >= MAX_PKTS) {
		fprintf(stderr, "too many packets: %d is the limit\n", MAX_PKTS);
		return 0;
	}
	g_pktlen[g_npkts] = 0;
	while (*h && g_pktlen[g_npkts] < sizeof g_pkt[0]) {
		char *e;
		long b;
		while (*h == ' ' || *h == ',' || *h == '\t' || *h == '\r' || *h == '\n') h++;
		if (!*h) break;
		b = strtol(h, &e, 16);
		if (e == h) { fprintf(stderr, "a packet wants hex bytes\n"); return 0; }
		g_pkt[g_npkts][g_pktlen[g_npkts]++] = (uint8_t)b;
		h = e;
	}
	g_npkts++;
	g_pkt_queued++;
	return 1;
}

/* Queue one packet as bytes. Used for what arrives from a hub. */
static int pkt_add_raw(const uint8_t *d, uint32_t n)
{
	if (g_npkts >= MAX_PKTS) return 0;
	if (n > sizeof g_pkt[0]) n = sizeof g_pkt[0];
	memcpy(g_pkt[g_npkts], d, n);
	g_pktlen[g_npkts] = n;
	g_npkts++;
	g_pkt_queued++;
	return 1;
}

/* DUART channel A's receive data, grown at run time: what --rio-in gave,
 * then whatever a keyboard or a hub adds. Bytes already delivered are
 * compacted away so a long session does not run out of room. */
static char g_rxbuf[1 << 20];

static void rx_append(const uint8_t *d, size_t n)
{
	if (g_in[0] != g_rxbuf) {
		size_t left = g_inlen[0] - g_inpos[0];
		if (left > sizeof g_rxbuf) left = sizeof g_rxbuf;
		if (left) memcpy(g_rxbuf, g_in[0] + g_inpos[0], left);
		g_in[0] = g_rxbuf;
		g_inpos[0] = 0;
		g_inlen[0] = left;
	}
	if (g_inpos[0] > sizeof g_rxbuf / 2) {
		memmove(g_rxbuf, g_rxbuf + g_inpos[0], g_inlen[0] - g_inpos[0]);
		g_inlen[0] -= g_inpos[0];
		g_inpos[0] = 0;
	}
	if (g_inlen[0] + n > sizeof g_rxbuf) return;
	memcpy(g_rxbuf + g_inlen[0], d, n);
	g_inlen[0] += n;
}

/* --net HOST:PORT: the pod on a network of pods, through a hub.
 *
 * One UDP datagram per message, first byte its kind:
 *   pod -> hub  'H' node          hello, sent until the hub answers
 *               'P' node bytes    a packet the pod transmitted, and to where
 *   hub -> pod  'P' bytes         a packet for the pod to receive
 *               'R' bytes         Remote I/O input: the panel, from afar
 * The hub is the segment: it relays what each pod sends to the others, and it
 * is where the console's messages come from. */
#ifdef _WIN32
#include <winsock2.h>
typedef SOCKET net_sock;
#define NET_BAD INVALID_SOCKET
#else
#include <sys/socket.h>
#include <netinet/in.h>
#include <arpa/inet.h>
#include <fcntl.h>
#include <unistd.h>
typedef int net_sock;
#define NET_BAD (-1)
#endif

static net_sock g_netsock = NET_BAD;
static struct sockaddr_in g_hub;
static int g_netnode = 1, g_net_heard, g_net_quit;
static uint32_t g_net_hello_at, g_net_in, g_net_out;

static void net_send(const uint8_t *d, int n)
{
	if (g_netsock == NET_BAD) return;
	sendto(g_netsock, (const char *)d, n, 0, (struct sockaddr *)&g_hub, sizeof g_hub);
}

static int net_open(const char *spec)
{
	char host[256];
	const char *colon = strrchr(spec, ':');
	size_t hl;

	if (!colon || (hl = (size_t)(colon - spec)) >= sizeof host) return 0;
	memcpy(host, spec, hl);
	host[hl] = 0;
#ifdef _WIN32
	{
		WSADATA w;
		u_long on = 1;
		if (WSAStartup(MAKEWORD(2, 2), &w)) return 0;
		g_netsock = socket(AF_INET, SOCK_DGRAM, IPPROTO_UDP);
		if (g_netsock == NET_BAD) return 0;
		ioctlsocket(g_netsock, FIONBIO, &on);
	}
#else
	g_netsock = socket(AF_INET, SOCK_DGRAM, 0);
	if (g_netsock == NET_BAD) return 0;
	fcntl(g_netsock, F_SETFL, fcntl(g_netsock, F_GETFL) | O_NONBLOCK);
#endif
	memset(&g_hub, 0, sizeof g_hub);
	g_hub.sin_family = AF_INET;
	g_hub.sin_port = htons((unsigned short)atoi(colon + 1));
	g_hub.sin_addr.s_addr = inet_addr(host);
	return 1;
}

/* Called every few thousand instructions: say hello until the hub answers,
 * and take whatever it has sent. The datagrams are docs/api.md. */
static void net_poll(uint32_t now)
{
	uint8_t buf[2048];
	int n;

	if (g_netsock == NET_BAD) return;
	if (!g_net_heard && now - g_net_hello_at >= 50) {
		uint8_t h[2] = { 'H', (uint8_t)g_netnode };
		net_send(h, 2);
		g_net_hello_at = now;
	}
	while ((n = recvfrom(g_netsock, (char *)buf, sizeof buf, 0, NULL, NULL)) > 0) {
		g_net_heard = 1;
		g_net_in++;
		if (buf[0] == 'P' && n > 1) pkt_add_raw(buf + 1, (uint32_t)(n - 1));
		else if (buf[0] == 'R' && n > 1) rx_append(buf + 1, (size_t)(n - 1));
		else if (buf[0] == 'Q') g_net_quit = 1;
	}
}

/* --realtime: pace the timebase to the wall clock, in hundredths. A bot pod
 * with no window needs it as much as the one a person is flying, or it lives
 * its game many times faster than the pods around it. */
static int g_realtime;

static uint32_t wall_hundredths(void)
{
#ifdef _WIN32
	return (uint32_t)(GetTickCount64() / 10);
#else
	struct timespec t;
	clock_gettime(CLOCK_MONOTONIC, &t);
	return (uint32_t)(t.tv_sec * 100 + t.tv_nsec / 10000000);
#endif
}

static void realtime_pace(void)
{
	static int ready;
	static uint32_t base;
	uint32_t w = wall_hundredths();

	if (!ready) {
		base = g_clock_val - w;
		g_clock_rt = 1;
		ready = 1;
	}
	g_clock_wall = base + w;
}

static void net_send_packet(uint32_t node, const uint8_t *d, uint32_t n)
{
	uint8_t buf[2 + 512];
	if (n > 512) n = 512;
	buf[0] = 'P';
	buf[1] = (uint8_t)node;
	memcpy(buf + 2, d, n);
	net_send(buf, (int)n + 2);
	g_net_out++;
}

static uint32_t g_monbase;
static void mon_pkt_arm(uint32_t base, unsigned n);

/* moveq #0,D0 ; suba.l A0,A0 ; rts - returns NULL with Z set, which the
 * firmware's thunks read as "nothing available, no error". */
static const uint8_t MON_STUB_NULL[6] = { 0x70,0x00, 0x91,0xC8, 0x4E,0x75 };

static void mon_slot(uint32_t slot, const uint8_t *code, uint32_t n)
{
	uint32_t at = g_monstub + slot * MON_STUB_SZ, i;
	for (i = 0; i < n; i++) m68k_write_memory_8(at + i, code[i]);
}

static void mon_install(uint32_t base)
{
	uint32_t i;

	ram_add(base, 0x1000);
	g_mon = base;
	g_monstub = base + MON_STUB_OFF;
	g_monbase = base;

	for (i = 0; i < MON_SLOTS; i++) {
		mon_slot(i, MON_STUB_NULL, sizeof MON_STUB_NULL);
		m68k_write_memory_32(base + i * 4, g_monstub + i * MON_STUB_SZ);
	}

	if (!g_npkts) return;
	if (g_clock_addr && g_clock_addr >= base + MON_PKT_OFF &&
	    g_clock_addr < base + MON_PKT_OFF + 4 + sizeof g_pkt[0])
		printf("warning: the clock at %08X is inside the packet buffer "
		       "at %08X and will overwrite packet bytes\n",
		       g_clock_addr, base + MON_PKT_OFF);
	mon_pkt_arm(base, 0);
	g_pkt_next = 1;
	g_pkt_skip = 1;
}

/* Put packet `n` where the firmware will read it. Its header is a word it does
 * not read here, then the body length, then the body - the receive path takes
 * the length from [pkt+2] and the opcode from [pkt+4]. */
static void mon_pkt_arm(uint32_t base, unsigned n)
{
	uint32_t buf = base + MON_PKT_OFF, i;
	uint8_t  ret[10] = { 0x20,0x7C, 0,0,0,0, 0x4A,0x88, 0x4E,0x75 };

	m68k_write_memory_32(buf, g_pktlen[n]);
	for (i = 0; i < g_pktlen[n]; i++)
		m68k_write_memory_8(buf + 4 + i, g_pkt[n][i]);
	ret[2] = (uint8_t)(buf >> 24); ret[3] = (uint8_t)(buf >> 16);
	ret[4] = (uint8_t)(buf >> 8);  ret[5] = (uint8_t)buf;
	mon_slot(MON_SLOT_RECV, ret, sizeof ret);	/* movea.l #buf,A0; tst.l A0; rts */
}

/* One packet per poll, in the order they were given. A mission needs a
 * sequence - a game length, then a mission, then a start - and one packet
 * could never express that. When they run out the NULL stub goes back, which
 * is what tells the firmware the wire is quiet. */
static void mon_recv_polled(void)
{
	/* This runs as the stub is entered, before it executes, so the packet
	 * armed now is the one this poll reads. Arming the next one on the same
	 * poll would overwrite a packet the firmware has not looked at yet -
	 * hence the first poll, which reads what mon_install armed, arms
	 * nothing. The queue can grow while the pod runs (--net), so the next
	 * packet is an index, and a drained queue starts again at zero. */
	g_pkt_delivered++;
	if (g_pkt_skip) { g_pkt_skip = 0; return; }
	if (g_pkt_next < g_npkts) {
		mon_pkt_arm(g_monbase, g_pkt_next++);
		g_pkt_null = 0;
	} else {
		if (!g_pkt_null) mon_slot(MON_SLOT_RECV, MON_STUB_NULL, sizeof MON_STUB_NULL);
		g_pkt_null = 1;
		if (g_net) g_pkt_next = g_npkts = 0;
	}
}

/* --clock: a free-running counter in RAM. The firmware reads 0x02000808 in 336
 * places and writes it nowhere, so the pod's boot monitor maintained it as a
 * timebase. It counts hundredths of a second: a Mech at full throttle moves
 * its chassis' top speed in metres per hundredth per tick, 0.26944 for 97 kph.
 * Without one, every timeout in the game waits forever. */
static uint32_t g_clock_div = 4096, g_clock_val;
/* Live play paces the timebase to the wall clock: the emulator runs far
 * faster than a 68020, and a clock that ticked on instructions alone would
 * run the game many times real speed. The live loop keeps this at the wall
 * clock in hundredths; the timebase may catch up to it and no further. */
static int      g_clock_rt;
static uint32_t g_clock_wall;

static void clock_tick(void)
{
	uint8_t *p;
	uint32_t o;
	if (!g_clock_addr) return;
	p = g_page[g_clock_addr >> PAGE_BITS];
	if (!p) return;
	o = g_clock_addr & (PAGE_SIZE - 1);
	if (g_clock_rt && g_clock_val >= g_clock_wall) return;
	g_clock_val++;
	p[o] = (uint8_t)(g_clock_val >> 24); p[o+1] = (uint8_t)(g_clock_val >> 16);
	p[o+2] = (uint8_t)(g_clock_val >> 8); p[o+3] = (uint8_t)g_clock_val;
}

/* --tick: return a counter that advances on every read. Enough to satisfy a
 * "poll this until it changes" handshake with a device we do not emulate yet,
 * which is how you walk past one blocker to find the next. */
#define MAXTICK 8
static uint32_t g_tick_addr[MAXTICK], g_tick_val[MAXTICK];
static int      g_ntick;

/* --poke: unmapped reads at ADDR return a fixed value. Enough to stand in for
 * a device that only has to answer one question, such as the renderer's
 * "I am up" word. */
#define MAXPOKE 16
static uint32_t g_poke_addr[MAXPOKE], g_poke_val[MAXPOKE];
static int      g_npoke;

static int poke_take(uint32_t addr, unsigned *out)
{
	int i;
	for (i = 0; i < g_npoke; i++)
		if (g_poke_addr[i] == addr) { *out = g_poke_val[i]; return 1; }
	return 0;
}

static int tick_take(uint32_t addr, unsigned *out)
{
	int i;
	for (i = 0; i < g_ntick; i++)
		if (g_tick_addr[i] == addr) { *out = ++g_tick_val[i]; return 1; }
	return 0;
}

static void note(uint32_t addr, int size, int is_write, uint32_t val)
{
	uint32_t h = (addr * 2654435761u) & (HITCAP - 1);
	uint8_t  sz = (size == 1) ? 1 : (size == 2) ? 2 : 4;

	if (is_write) g_writes_total++; else g_reads_total++;
	g_note_flag = 1;
	g_note_addr = addr;
	if (!is_write && size == 4 && (addr & 3) == 0 &&
	    addr >= g_vbr && addr < g_vbr + 0x400) g_vector_hit = addr;

	for (;;) {
		Hit *e = &g_hit[h];
		if (!e->used) {
			if (g_nhit >= HITCAP / 2) { g_hit_dropped++; return; }
			e->used = 1;
			e->addr = addr;
			e->first_pc = m68k_get_reg(NULL, M68K_REG_PPC);
			g_nhit++;
		} else if (e->addr != addr) {
			h = (h + 1) & (HITCAP - 1);
			continue;
		}
		e->sizes |= sz;
		if (is_write) { e->writes++; e->last_write = val; e->wrote = 1; }
		else          { e->reads++; }
		return;
	}
}


/* ------------------------------------------------------------ renderer stub */

/* The TMS340 renderer publishes a comm block: the 68020 reads its address from
 * 0x3FFFFFB8 (a TI byte address, +0x20000000 to reach it), posts a command by
 * writing the queue then setting [block+4], and waits for 0x3FFFFFBC to read
 * back 0x31415926. This stands in for the renderer: it acknowledges every
 * command immediately and records what was written, which is how the command
 * protocol gets documented without emulating the TMS340 first. */

#define RSTUB_WINDOW  0x10000
#define RSTUB_MAGIC   0x31415926u
#define RSTUB_PTR     0x3FFFFFB8u	/* comm block pointer, TI byte address */
#define RSTUB_FLAG    0x3FFFFFBCu	/* renderer-ready / command-done word   */
#define TI_TO_68K     0x20000000u

/* Renderer heap. Commands ask the renderer to allocate; a bump allocator over
 * a mapped slice of the TI window is enough to let the resource loader run.
 * ponytail: never freed - the boot path only allocates. */
#define RSTUB_HEAP_68K 0x30000000u
#define RSTUB_HEAP_LEN 0x01000000u

/* The renderer's own memory has to be real: R.BIN is uploaded into it, and the
 * firmware reads a fixed error block out of the top of it. Left unmapped, that
 * block reads as open bus and the firmware reports "TI ERROR!". */
#define RSTUB_TI_BASE  0x3FC00000u
#define RSTUB_TI_LEN   0x00400000u

#define RS_OP_RESET  1
#define RS_OP_ALLOC  2
#define RS_OP_RENDER 6

/* The audio board is a ring the 68020 fills and the DSP drains. The producer
 * at 0x02149190 computes next = (head + 4) & 0x7C and spins while the tail
 * equals it - the FIFO-full test. With no board on the other side the tail
 * never moves, so the download of btAudio.dld's quarter-million longwords
 * never finishes and the boot hangs there.
 *
 * A board that drains as fast as it is filled is one line: whatever the 68020
 * writes to the head, write to the tail as well. That is not a cheat about
 * timing - it is the fastest a real board could be - but it does mean nothing
 * here plays a sound. */
#define ASTUB_SIG   0x55000000u		/* +0x00, the top byte the ROM checks */
#define ASTUB_LEN   0x100u

static uint32_t g_astub;		/* 68k base of the audio board, 0 = off */

static uint32_t g_rstub;		/* 68k address of the comm block, 0 = off */
static uint32_t g_rsheap = RSTUB_HEAP_68K - TI_TO_68K;	/* next free, TI byte address */
static uint32_t g_rshandle;
static int      g_rscmd;
static char     g_rslog[262144];
static size_t   g_rsloglen;

static int g_rsquiet;		/* walking a list only to capture it */

static void rslog(const char *fmt, ...)
{
	va_list ap;
	int n;
	if (g_rsquiet) return;
	if (g_rsloglen + 256 >= sizeof g_rslog) return;
	va_start(ap, fmt);
	n = vsnprintf(g_rslog + g_rsloglen, sizeof g_rslog - g_rsloglen, fmt, ap);
	va_end(ap);
	if (n > 0) g_rsloglen += (size_t)n;
}

static uint32_t rs_get(uint32_t off)
{
	uint8_t *p = g_page[(g_rstub + off) >> PAGE_BITS];
	uint32_t o = (g_rstub + off) & (PAGE_SIZE - 1);
	return ((uint32_t)p[o] << 24) | ((uint32_t)p[o+1] << 16) |
	       ((uint32_t)p[o+2] << 8) | p[o+3];
}

static void rs_put(uint32_t off, uint32_t v)
{
	uint8_t *p = g_page[(g_rstub + off) >> PAGE_BITS];
	uint32_t o = (g_rstub + off) & (PAGE_SIZE - 1);
	p[o] = (uint8_t)(v >> 24); p[o+1] = (uint8_t)(v >> 16);
	p[o+2] = (uint8_t)(v >> 8); p[o+3] = (uint8_t)v;
}

/* A display list is a flat array of big-endian longwords with a leading count,
 * copied verbatim into the renderer's memory, and opcode 6 hands over where it
 * landed. The record shapes come from the two emitters in the ROM that build
 * them - 0x0214465C and 0x02144724 - not from watching the wire, because a
 * cockpit that has not started a game never sends one.
 *
 * Record 8 is a viewport; its width, height and centre are derived from its
 * corners by the emitter, which is what identifies it. Record 1 draws an
 * object and carries twelve IEEE singles - four rows of three, a rotation and
 * a translation - so the transform is the renderer's coprocessor's job, not the
 * 68020's. */
static float as_float(uint32_t v)
{
	float f;
	memcpy(&f, &v, sizeof f);
	return f;
}

static uint32_t (*g_dl_read)(uint32_t) = m68k_read_memory_32;

static uint32_t dl_word(uint32_t ti_byte_addr, uint32_t i)
{
	return g_dl_read(ti_byte_addr + TI_TO_68K + i * 4);
}

/* Inside an object record, after its 35-longword header, comes a stream of
 * items. Their opcodes step by 0x20 because the renderer uses the opcode
 * *directly* as a bit offset into its dispatch table at 0xFE0229E0 - one
 * longword every 32 bits - and then JUMPs. Twenty-five entries there; the
 * 68020 has an emitter for each. These lengths are the emitters' own, in
 * longwords including the opcode. Zero means the item carries a string and
 * runs until its terminator. */
static const uint8_t g_item_len[25] = {
	1, 1, 8, 2, 1, 1, 1, 1,		/* 0x000 .. 0x0E0 */
	3, 3, 3, 4, 2, 3, 2, 0,		/* 0x100 .. 0x1E0 */
	0, 2, 2, 6, 1, 1, 11, 1,	/* 0x200 .. 0x2E0 */
	1				/* 0x300          */
};

/* Strings are copied into the list a longword at a time with the bytes
 * reversed, which is what makes them read correctly on a little-endian TI. */
static uint32_t dl_string(uint32_t ti_byte_addr, uint32_t at, uint32_t room,
			  char *out, size_t cap)
{
	uint32_t n = 0, i;
	size_t o = 0;
	while (n < room) {
		uint32_t v = dl_word(ti_byte_addr, at + n++);
		for (i = 0; i < 4; i++) {
			char c = (char)(v >> (i * 8));
			if (!c) { out[o < cap ? o : cap - 1] = 0; return n; }
			if (o + 1 < cap) out[o++] = c;
		}
	}
	out[o < cap ? o : cap - 1] = 0;
	return n;
}

static void dl_items(uint32_t ti_byte_addr, uint32_t at, uint32_t room)
{
	int guard = 0;
	while (room && guard++ < 128) {
		uint32_t op = dl_word(ti_byte_addr, at), len;
		if (op & 0x1F || op > 0x300) {
			rslog("        item $%X unknown; stopping\n", op);
			return;
		}
		len = g_item_len[op / 0x20];
		if (len == 0) {
			char text[128];
			uint32_t used = dl_string(ti_byte_addr, at + 1, room - 1,
						  text, sizeof text);
			rslog("        item $%03X \"%s\"\n", op, text);
			len = 1 + used;
		} else {
			uint32_t k;
			rslog("        item $%03X", op);
			/* The lengths are known and the meanings are not, so
			 * print the payload: a shape id or a small integer is
			 * recognisable where a bare length is not. */
			for (k = 1; k < len && k < room; k++) {
				uint32_t v = dl_word(ti_byte_addr, at + k);
				if (v > 0x30000000u && v < 0x50000000u)
					rslog("  %.4f", as_float(v));
				else
					rslog("  %u", v);
			}
			rslog("\n");
		}
		if (op == 0 || len > room) return;
		at += len;
		room -= len;
	}
}


static void rstub_dlist(uint32_t ti_byte_addr)
{
	uint32_t count = dl_word(ti_byte_addr, 0), at = 1;
	int records = 0;

	rslog("  display list at TI %08X: %u longwords\n", ti_byte_addr, count);
	if (g_frame_cur.have_cam) g_frame_latest = g_frame_cur;
	memset(&g_frame_cur, 0, sizeof g_frame_cur);
	g_frame_cur.seq = ++g_frames_walked;
	if (count == 0 || count > 0x40000) {
		rslog("    implausible length, not walked\n");
		return;
	}
	while (at < count + 1 && records < 4096) {
		uint32_t type = dl_word(ti_byte_addr, at);
		/* 0xFFFFFFFF is a separator, not the end: a real frame has one
		 * after the leading record and carries on with the viewport.
		 * Reading it as a record type was what made every list here
		 * look like it held nothing. */
		if (type == 0xFFFFFFFFu) {
			rslog("    ----\n");
			at++;
			continue;
		}
		/* The renderer's walker skips the type and length, then takes the
		 * length in longwords as what follows - so a record is 2 + len. */
		uint32_t len = 2 + dl_word(ti_byte_addr, at + 1);
		records++;
		if (type == 8) {
			rslog("    viewport  (%d,%d)-(%d,%d)  %dx%d  centre (%d,%d)\n",
			      (int)dl_word(ti_byte_addr, at + 2), (int)dl_word(ti_byte_addr, at + 3),
			      (int)dl_word(ti_byte_addr, at + 4), (int)dl_word(ti_byte_addr, at + 5),
			      (int)dl_word(ti_byte_addr, at + 6), (int)dl_word(ti_byte_addr, at + 7),
			      (int)dl_word(ti_byte_addr, at + 8), (int)dl_word(ti_byte_addr, at + 9));
		} else if (type == 1) {
			int r, c;
			for (r = 0; r < 12; r++)
				g_frame_cur.cam[r] = as_float(dl_word(ti_byte_addr, at + 2 + r));
			g_frame_cur.have_cam = 1;
			rslog("    object    %u picks, %u longwords, viewport %u, "
			      "items from record %u, screen %dx%d\n",
			      dl_word(ti_byte_addr, at + 34), len,
			      dl_word(ti_byte_addr, at + 16),
			      dl_word(ti_byte_addr, at + 22),
			      (int)dl_word(ti_byte_addr, at + 19) + 1,
			      (int)dl_word(ti_byte_addr, at + 20) + 1);
			/* Twelve floats as four rows of three: a 3x3 rotation
			 * and a translation row. Written as the identity, which
			 * only reads as one at this shape. */
			for (r = 0; r < 4; r++) {
				rslog("      ");
				for (c = 0; c < 3; c++)
					rslog("%9.4f ", as_float(dl_word(ti_byte_addr, at + 2 + r * 3 + c)));
				rslog("\n");
			}
			/* What follows the header is neither the item stream nor
			 * geometry: it is a list of **pick queries**, n of them
			 * at seven longwords each, capped at 32. The 68020 puts
			 * a screen X and Y in the first two; the renderer fills
			 * the rest in as it draws, with whatever it painted over
			 * that pixel.
			 *
			 * 0xFE019BE0 packs lw0 and lw1 into an XY address with
			 * MOVY and files it; 0xFE01A280 reads the frame buffer
			 * there while drawing and records the entity, the
			 * sub-part tag and its position; 0xFE019D50 copies the
			 * answers back out. lw2 == 0 means nothing was hit.
			 *
			 * The item stream lives in a type 7 record instead,
			 * named by +0x58. */
			for (r = 0; r < (int)dl_word(ti_byte_addr, at + 34) && r < 32; r++) {
				uint32_t q = at + 35 + r * 7;
				if (q + 6 >= at + len)
					break;
				rslog("        pick (%d,%d) -> entity %u part %u\n",
				      (int)dl_word(ti_byte_addr, q),
				      (int)dl_word(ti_byte_addr, q + 1),
				      dl_word(ti_byte_addr, q + 2),
				      dl_word(ti_byte_addr, q + 3));
			}
		} else if (type == 7) {
			rslog("    items     %u longwords\n", len - 2);
			dl_items(ti_byte_addr, at + 2, len - 2);
		} else {
			uint32_t k;
			rslog("    type %u, %u longwords\n", type, len);
			/* A type 3 is an entity, a model id, a 3x3 and a
			 * position; the rest is its joints. */
			if (type == 3 && len >= 18 && g_frame_cur.n < FRAME_OBJS) {
				int f = g_frame_cur.n++;
				g_frame_cur.obj[f].entity = dl_word(ti_byte_addr, at + 2);
				g_frame_cur.obj[f].model = dl_word(ti_byte_addr, at + 5);
				g_frame_cur.obj[f].arms = mech_arms(ti_byte_addr, at, len);
				g_frame_cur.obj[f].pose = -1;
				if (len >= MECH_POSE + MECH_SLOTS * 12 && g_frame_cur.npose < FRAME_POSES) {
					int q = g_frame_cur.npose++, sl;
					for (sl = 0; sl < MECH_SLOTS; sl++)
						for (k = 0; k < 12; k++)
							g_frame_cur.pose[q][sl][k] = as_float(
								dl_word(ti_byte_addr, at + MECH_POSE + sl * 12 + k));
					g_frame_cur.obj[f].pose = q;
				}
				if (g_mechdump_path && len > MECH_VARS + 46)
					mech_dump(ti_byte_addr, at, len);
				for (k = 0; k < 9; k++)
					g_frame_cur.obj[f].rot[k] = as_float(dl_word(ti_byte_addr, at + 6 + k));
				for (k = 0; k < 3; k++)
					g_frame_cur.obj[f].at[k] = as_float(dl_word(ti_byte_addr, at + 15 + k));
				if (g_frame_cur.have_cam && (!g_frame_at || g_frame_cur.seq <= g_frame_at))
					g_frame_last = g_frame_cur;
			}
			/* Types nobody has named yet are printed raw, eight to
			 * a line, floats where they look like floats - the Mech
			 * arrives as a type 3 and was invisible for as long as
			 * this branch printed only a length. */
			for (k = 2; k < len && k < 402 && at + k < count + 1; k++) {
				uint32_t v = dl_word(ti_byte_addr, at + k);
				if ((k - 2) % 8 == 0) rslog("      %4u ", k - 2);
				if ((v > 0x30000000u && v < 0x50000000u) ||
				    (v > 0xB0000000u && v < 0xD0000000u))
					rslog(" %10.4f", as_float(v));
				else
					rslog(" %10X", v);
				if ((k - 2) % 8 == 7) rslog("\n");
			}
			if ((k - 2) % 8) rslog("\n");
		}
		if (len == 0 || len > count + 1 - at) {
			rslog("    record length %u does not fit; stopping\n", len);
			return;
		}
		at += len;
	}
}

/* --frame-out: the last list that placed a model (or --frame-at's), drawn
 * and written as raw 480x360 RGB. */
static void frame_report(void)
{
	struct pod_frame *fr = &g_frame_last;
	int poly, drawn;
	FILE *f;

	printf("\npod frame: ");
	if (!fr->have_cam || fr->n == 0) {
		printf("no frame placed a model\n");
		return;
	}
	poly = frame_draw(&g_sceneframe, fr, &drawn, 1);
	f = fopen(g_frameout, "wb");
	if (f) {
		fwrite(g_sceneframe.px, 1, sizeof g_sceneframe.px, f);
		fclose(f);
		printf("  %s: %dx%d, %d models, %d polygons\n",
		       g_frameout, RAS_W, RAS_H, drawn, poly);
	}
}

/* --record: the pod's own frames, drawn as --frame-out draws one, piped to
 * ffmpeg at 25 a second of the pod's clock (g_clock_val, in hundredths), so
 * the video keeps the game's time however fast or slow the emulator ran. No
 * window and no display, which is what makes it work over RDP and in CI. */
#define REC_EVERY 4			/* hundredths per video frame: 25 fps */
static const char *g_recpath;
static char g_recfile[512];		/* g_recpath with the node in it */
static FILE *g_rec;
static uint32_t g_rec_next;
static int g_rec_frames;

#ifdef _WIN32
#include <io.h>
#include <fcntl.h>
static HANDLE g_rec_proc;
#endif

static void rec_open(void)
{
	char cmd[1024], *path = g_recfile;
#ifdef _WIN32
	/* Not _popen: that goes through cmd.exe, which opens a console window
	 * when cockpit.exe (a GUI program) has none - on someone's screen. */
	SECURITY_ATTRIBUTES sa = { sizeof sa, NULL, TRUE };
	STARTUPINFOA si = { sizeof si };
	PROCESS_INFORMATION pi;
	HANDLE rd, wr;

	snprintf(path, sizeof g_recfile, g_recpath, g_netnode);	/* a %d is the pod's node */
	snprintf(cmd, sizeof cmd, "ffmpeg -loglevel error -y -f rawvideo -pix_fmt rgb24 -s %dx%d "
		 "-r %d -i - -pix_fmt yuv420p \"%s\"", RAS_W, RAS_H, 100 / REC_EVERY, path);
	if (CreatePipe(&rd, &wr, &sa, 0)) {
		SetHandleInformation(wr, HANDLE_FLAG_INHERIT, 0);
		si.dwFlags = STARTF_USESTDHANDLES;
		si.hStdInput = rd;
		si.hStdOutput = GetStdHandle(STD_OUTPUT_HANDLE);
		si.hStdError = GetStdHandle(STD_ERROR_HANDLE);
		if (CreateProcessA(NULL, cmd, NULL, NULL, TRUE, CREATE_NO_WINDOW,
				   NULL, NULL, &si, &pi)) {
			CloseHandle(pi.hThread);
			g_rec_proc = pi.hProcess;
			g_rec = _fdopen(_open_osfhandle((intptr_t)wr, _O_BINARY), "wb");
		} else {
			CloseHandle(wr);
		}
		CloseHandle(rd);
	}
#else
	snprintf(path, sizeof g_recfile, g_recpath, g_netnode);	/* a %d is the pod's node */
	snprintf(cmd, sizeof cmd, "ffmpeg -loglevel error -y -f rawvideo -pix_fmt rgb24 -s %dx%d "
		 "-r %d -i - -pix_fmt yuv420p '%s'", RAS_W, RAS_H, 100 / REC_EVERY, path);
	g_rec = popen(cmd, "w");
#endif
	if (!g_rec) fprintf(stderr, "--record: could not start ffmpeg\n");
}

/* Called every few thousand instructions; writes every video frame the
 * clock has passed since the last call, the latest pod frame in each (black
 * until the first one). */
static void rec_poll(void)
{
	static struct raster r;
	static int drawn_seq = -1;
	int models;

	if (!g_rec_next) g_rec_next = g_clock_val;
	if (g_clock_val < g_rec_next) return;
	if (g_frame_latest.have_cam && g_frame_latest.seq != drawn_seq) {
		frame_draw(&r, &g_frame_latest, &models, 0);
		drawn_seq = g_frame_latest.seq;
	}
	while (g_clock_val >= g_rec_next) {
		fwrite(r.px, 1, sizeof r.px, g_rec);
		g_rec_frames++;
		g_rec_next += REC_EVERY;
	}
}

static void rec_close(void)
{
#ifdef _WIN32
	fclose(g_rec);
	WaitForSingleObject(g_rec_proc, INFINITE);
	CloseHandle(g_rec_proc);
#else
	pclose(g_rec);
#endif
	printf("\nrecorded %d frames (%.1f s of pod time) to %s\n",
	       g_rec_frames, g_rec_frames * REC_EVERY / 100.0, g_recfile);
}

/* The request is staged in 68k RAM, memcpy'd into the queue at block+8, and the
 * same bytes are copied back out as the reply once the command completes. So:
 * read the request here, answer in place, then clear the status word. */
static void rstub_post(void)
{
	uint32_t w[24];
	int n = 0, i;

	g_rscmd++;
	while (n < (int)(sizeof w / sizeof w[0])) {
		w[n] = rs_get(8 + n * 4);
		if (w[n++] == 0xFFFFFFFFu) break;
	}

	if (g_rscmd <= 400) {
		rslog("cmd %-4d op=%08X  ", g_rscmd, w[0]);
		for (i = 1; i < n; i++) rslog("%08X ", w[i]);
	}

	/* Reply fields sit at +8/+0xC/+0x10 of the request: error, handle, addr
	 * (that order, read straight off the ROM's own unpacking of the reply). */
	if (w[0] == RS_OP_ALLOC && n >= 3) {
		uint32_t size = (w[1] + 15) & ~15u;
		uint32_t addr = g_rsheap;
		if (g_rsheap + size <= RSTUB_HEAP_68K - TI_TO_68K + RSTUB_HEAP_LEN) {
			g_rsheap += size;
			rs_put(8 + 2 * 4, 0);			/* error  */
			rs_put(8 + 3 * 4, ++g_rshandle);	/* handle */
			rs_put(8 + 4 * 4, addr);		/* addr   */
			if (g_rscmd <= 400)
				rslog(" -> handle %u addr %08X", g_rshandle, addr);
		} else if (g_rscmd <= 400) {
			rslog(" -> OUT OF HEAP");
		}
	}
	if (g_rscmd <= 400) rslog("\n");
	/* Past the logged window the list is still walked when a frame is
	 * wanted, silently, so --frame-out sees the latest one rather than
	 * the four-hundredth. */
	if (w[0] == RS_OP_RENDER && n >= 2 && (g_rscmd <= 400 || g_frameout || g_capture)) {
		g_rsquiet = g_rscmd > 400;
		rstub_dlist(w[1]);
		g_rsquiet = 0;
	}

	rs_put(4, 0);			/* command complete */
	m68k_write_memory_32(RSTUB_FLAG, RSTUB_MAGIC);	/* renderer ready again */

	/* A real board would take a while and then interrupt. This one takes no
	 * time at all, which is the fastest a board could be and is the same
	 * simplification the audio stub makes. */
	if (g_rirq && w[0] == RS_OP_RENDER) {
		/* The handler reads a *word* at the CSR, so the cause has to be in
		 * the high half of the longword there. */
		g_rirq_pending = g_rirq_delay > 0 ? g_rirq_delay : 1;
	}
}

/* The line stays up until the handler acknowledges by clearing bit 7. */
static int rirq_asserted(void)
{
	uint8_t *p;
	if (g_rirq_pending > 1) return 0;		/* still working */
	/* In real time a frame takes at least 3 hundredths, about the 30 a
	 * second the board managed. Without this an instant renderer lets a pod
	 * post frames - and its position broadcasts with them - thousands of
	 * times a second, and a network of pods drowns in them. */
	if (g_rirq_pending == 1 && g_clock_rt && g_clock_val < g_rirq_next)
		return 0;
	if (g_rirq_pending == 1) {			/* just finished */
		g_rirq_next = g_clock_val + 3;
		m68k_write_memory_32(RIRQ_CSR, (uint32_t)RIRQ_DONE << 16);
		g_rirq_pending = -1;
	}
	if (g_rirq_pending != -1) return 0;
	p = g_page[RIRQ_CSR >> PAGE_BITS];
	if (!p) return 0;
	if (p[(RIRQ_CSR + 1) & (PAGE_SIZE - 1)] & 0x80) return 1;
	g_rirq_pending = 0;				/* acknowledged */
	return 0;
}

static void rstub_write(uint32_t off, uint32_t v)
{
	if (off == 4 && v) rstub_post();
}

static void poke32(uint32_t a, uint32_t v)
{
	uint8_t *p = g_page[a >> PAGE_BITS];
	uint32_t o = a & (PAGE_SIZE - 1);
	if (!p) return;
	p[o] = (uint8_t)(v >> 24); p[o+1] = (uint8_t)(v >> 16);
	p[o+2] = (uint8_t)(v >> 8); p[o+3] = (uint8_t)v;
}

/* The firmware clears the ready word and waits for the renderer to write pi
 * back; it also uploads R.BIN straight over this part of the renderer's memory,
 * which on real hardware the TI then rewrites for itself once it is running.
 * Restoring both words here models a renderer that is always instantly ready. */
static void rstub_flag_write(uint32_t v)
{
	if (v == RSTUB_MAGIC) return;
	poke32(RSTUB_FLAG, RSTUB_MAGIC);
	poke32(RSTUB_PTR, g_rstub - TI_TO_68K);
}

static int rstub_read(uint32_t a, unsigned *out)
{
	if (!g_rstub) return 0;
	if (a == RSTUB_PTR)  { *out = g_rstub - TI_TO_68K; return 1; }
	if (a == RSTUB_FLAG) { *out = RSTUB_MAGIC; return 1; }
	return 0;
}

/* --------------------------------------------------------- m68k callbacks */

unsigned int m68k_read_memory_8(unsigned int a)
{
	uint8_t *p = g_page[a >> PAGE_BITS];
	unsigned t;
	if (g_watch_len && (a - g_watch_base) < g_watch_len) note(a, 1, 0, 0);
	if (p) return p[a & (PAGE_SIZE - 1)];
	note(a, 1, 0, 0);
	if (duart_read(a, &t)) return t;
	return g_openbus & 0xFF;
}

unsigned int m68k_read_memory_16(unsigned int a)
{
	uint8_t *p = g_page[a >> PAGE_BITS];
	uint32_t o = a & (PAGE_SIZE - 1);
	unsigned t;
	if (g_watch_len && (a - g_watch_base) < g_watch_len) note(a, 2, 0, 0);
	if (p && o <= PAGE_SIZE - 2) return ((unsigned)p[o] << 8) | p[o + 1];
	if (!p && o <= PAGE_SIZE - 2) { note(a, 2, 0, 0); return poke_take(a, &t) ? (t & 0xFFFF) : (g_openbus & 0xFFFF); }
	return (m68k_read_memory_8(a) << 8) | m68k_read_memory_8(a + 1);
}

unsigned int m68k_read_memory_32(unsigned int a)
{
	uint8_t *p = g_page[a >> PAGE_BITS];
	uint32_t o = a & (PAGE_SIZE - 1);
	unsigned t;
	if ((a - g_vbr) < 0x400 && !(a & 3)) g_vecfetch = a;
	if (g_watch_len && (a - g_watch_base) < g_watch_len) note(a, 4, 0, 0);
	if (p && o <= PAGE_SIZE - 4)
		return ((unsigned)p[o] << 24) | ((unsigned)p[o+1] << 16) |
		       ((unsigned)p[o+2] << 8) | p[o+3];
	if (!p && o <= PAGE_SIZE - 4) {
		note(a, 4, 0, 0);
		if (rstub_read(a, &t)) return t;
		if (poke_take(a, &t)) return t;
		return tick_take(a, &t) ? t : g_openbus;
	}
	return (m68k_read_memory_16(a) << 16) | m68k_read_memory_16(a + 2);
}

static void wtrap(uint32_t a, int size, uint32_t v)
{
	if (!g_wtrap_len || (a - g_wtrap_base) >= g_wtrap_len) return;
	if (g_wtrap_n++ >= WTRAP_MAX) return;
	printf("wtrap %08X size %d = %08X  from pc %08X\n",
	       a, size, v, m68k_get_reg(NULL, M68K_REG_PPC));
}

void m68k_write_memory_8(unsigned int a, unsigned int v)
{
	uint8_t *p = g_page[a >> PAGE_BITS];
	if (g_wtrap_len) wtrap(a, 1, v & 0xFF);
	if (p) { p[a & (PAGE_SIZE - 1)] = (uint8_t)v; return; }
	duart_write(a, v);
	note(a, 1, 1, v & 0xFF);
}

void m68k_write_memory_16(unsigned int a, unsigned int v)
{
	uint8_t *p = g_page[a >> PAGE_BITS];
	uint32_t o = a & (PAGE_SIZE - 1);
	if (g_wtrap_len) wtrap(a, 2, v & 0xFFFF);
	if (p && o <= PAGE_SIZE - 2) { p[o] = (uint8_t)(v >> 8); p[o+1] = (uint8_t)v; return; }
	if (!p && o <= PAGE_SIZE - 2) { note(a, 2, 1, v & 0xFFFF); return; }
	m68k_write_memory_8(a, v >> 8);
	m68k_write_memory_8(a + 1, v);
}

void m68k_write_memory_32(unsigned int a, unsigned int v)
{
	uint8_t *p = g_page[a >> PAGE_BITS];
	uint32_t o = a & (PAGE_SIZE - 1);
	if (g_wtrap_len) wtrap(a, 4, v);
	if (p && o <= PAGE_SIZE - 4) {
		p[o] = (uint8_t)(v >> 24); p[o+1] = (uint8_t)(v >> 16);
		p[o+2] = (uint8_t)(v >> 8); p[o+3] = (uint8_t)v;
		if (g_rstub) {
			if (a >= g_rstub && a < g_rstub + RSTUB_WINDOW)
				rstub_write(a - g_rstub, v);
			else if (a == RSTUB_FLAG)
				rstub_flag_write(v);
		}
		if (g_astub && a == g_astub + 4) {
			poke32(g_astub + 8, v);		/* drained already */
			poke32(g_astub, ASTUB_SIG | 1);	/* and downloaded */
		}
		return;
	}
	if (!p && o <= PAGE_SIZE - 4) { note(a, 4, 1, v); return; }
	m68k_write_memory_16(a, v >> 16);
	m68k_write_memory_16(a + 2, v);
}

/* The disassembler must not pollute the bus log - it is our reads, not the ROM's. */
static unsigned int peek(uint32_t a, int n)
{
	unsigned int v = 0;
	uint8_t *p;
	while (n--) {
		p = g_page[a >> PAGE_BITS];
		v = (v << 8) | (p ? p[a & (PAGE_SIZE - 1)] : (g_openbus & 0xFF));
		a++;
	}
	return v;
}

unsigned int m68k_read_disassembler_8 (unsigned int a) { return peek(a, 1); }
unsigned int m68k_read_disassembler_16(unsigned int a) { return peek(a, 2); }
unsigned int m68k_read_disassembler_32(unsigned int a) { return peek(a, 4); }

/* ------------------------------------------------------------- load script */

/* Each image carries a 28-byte header: 0x601A (a BRA.S to the entry stub at
 * +0x1C), then text/data/bss sizes. text+data always equals filesize-28 in the
 * 13.1.8 release, which is how the field layout below was confirmed. */
typedef struct {
	char     name[64];
	char     path[1024];
	uint32_t addr;
	long     size;
	int      has_hdr;
	uint32_t text, data, bss;
} Image;

#define MAXIMG 32
static Image   g_img[MAXIMG];
static int     g_nimg;
static uint32_t g_entry;
static int     g_have_entry;

static void dirname_of(const char *path, char *out, size_t n)
{
	const char *s = path, *cut = NULL;
	for (; *s; s++) if (*s == '/' || *s == '\\') cut = s;
	if (!cut) { snprintf(out, n, "."); return; }
	snprintf(out, n, "%.*s", (int)(cut - path), path);
}

static int ieq(const char *a, const char *b)
{
	for (; *a && *b; a++, b++) if (tolower((unsigned char)*a) != tolower((unsigned char)*b)) return 0;
	return *a == *b;
}

/* VWE scripts name files in whatever case the author felt like that day. */
static int find_in(const char *dir, const char *name, char *out, size_t n)
{
	DIR *d = opendir(dir);
	struct dirent *e;
	if (!d) return 0;
	while ((e = readdir(d))) {
		if (ieq(e->d_name, name)) {
			snprintf(out, n, "%s/%s", dir, e->d_name);
			closedir(d);
			return 1;
		}
	}
	closedir(d);
	return 0;
}

/* The Load scripts sit in "Game Files" but name images that live one level
 * down in "Cockpit Software", so search the script's directory and its
 * immediate subdirectories. */
static int find_file(const char *dir, const char *name, char *out, size_t n)
{
	DIR *d;
	struct dirent *e;

	if (find_in(dir, name, out, n)) return 1;

	d = opendir(dir);
	if (!d) return 0;
	while ((e = readdir(d))) {
		char sub[1024];
		if (e->d_name[0] == '.') continue;
		snprintf(sub, sizeof sub, "%s/%s", dir, e->d_name);
		if (find_in(sub, name, out, n)) { closedir(d); return 1; }
	}
	closedir(d);
	return 0;
}

static uint32_t rd32(const uint8_t *p) {
	return ((uint32_t)p[0] << 24) | ((uint32_t)p[1] << 16) | ((uint32_t)p[2] << 8) | p[3];
}

/* ------------------------------------------------- the secondary display */

/* The pod's second screen is an Amiga board, and its program is a plain 601A
 * image: text 56,704, data 4,720, bss 692. Its header says `ABSFLAG = 1` -
 * **no relocations** - and its first instruction is `jmp $0000E112`, an
 * absolute address inside its own data. So it is linked to run at zero, which
 * is what a bare-metal display board with no operating system looks like.
 *
 * The load script puts it at 0x400003E4 for the 68020 to copy across. To run
 * it we put it where it expects to be instead: text and data at 0, bss zeroed
 * behind them, and start at 0. */
static const char *g_amiga;

static int amiga_load(const char *path)
{
	uint8_t hdr[28];
	uint32_t text, data, bss, a;
	long n;
	FILE *f = fopen(path, "rb");

	if (!f) { fprintf(stderr, "cannot open %s\n", path); return 0; }
	if (fread(hdr, 1, 28, f) != 28 || hdr[0] != 0x60 || hdr[1] != 0x1A) {
		fprintf(stderr, "%s is not a 601A image\n", path);
		fclose(f);
		return 0;
	}
	text = rd32(hdr + 2);
	data = rd32(hdr + 6);
	bss  = rd32(hdr + 10);
	n = (long)text + data;

	ram_add(0, (uint32_t)n + bss + 0x100);
	for (a = 0; a < (uint32_t)n; a++) {
		int c = fgetc(f);
		if (c == EOF) break;
		g_page[a >> PAGE_BITS][a & (PAGE_SIZE - 1)] = (uint8_t)c;
	}
	fclose(f);

	printf("secondary display %s: text %u, data %u, bss %u, linked at 0\n",
	       path, text, data, bss);
	printf("  absflag %u (%s)\n", (unsigned)((hdr[26] << 8) | hdr[27]),
	       ((hdr[26] << 8) | hdr[27]) ? "no relocations" : "relocatable");
	return 1;
}

static int load_script(const char *script)
{
	char dir[1024], *buf, *p;
	long len;
	FILE *f = fopen(script, "rb");

	if (!f) { fprintf(stderr, "cannot open load script: %s\n", script); return 0; }
	fseek(f, 0, SEEK_END); len = ftell(f); fseek(f, 0, SEEK_SET);
	buf = malloc(len + 1);
	if (fread(buf, 1, len, f) != (size_t)len) { fclose(f); free(buf); return 0; }
	buf[len] = 0;
	fclose(f);

	dirname_of(script, dir, sizeof dir);

	/* Classic Mac text: CR line endings. Normalise both, then walk lines. */
	for (p = buf; *p; p++) if (*p == '\r') *p = '\n';

	for (p = strtok(buf, "\n"); p; p = strtok(NULL, "\n")) {
		char name[64];
		uint32_t addr;
		char *q, *e;
		size_t nl;

		while (*p == ' ' || *p == '\t') p++;
		if (*p != '"') continue;
		q = strchr(p + 1, '"');
		if (!q) continue;
		nl = (size_t)(q - (p + 1));
		if (nl >= sizeof name) nl = sizeof name - 1;
		memcpy(name, p + 1, nl);
		name[nl] = 0;

		addr = (uint32_t)strtoul(q + 1, &e, 16);
		if (e == q + 1) continue;

		if (ieq(name, "Go_Address")) { g_entry = addr; g_have_entry = 1; continue; }
		if (g_nimg >= MAXIMG) { fprintf(stderr, "too many images\n"); break; }

		{
			Image *im = &g_img[g_nimg];
			snprintf(im->name, sizeof im->name, "%s", name);
			im->addr = addr;
			if (!find_file(dir, name, im->path, sizeof im->path) &&
			    !find_file(dir, name, im->path, sizeof im->path)) {
				fprintf(stderr, "MISSING image file: %s (looked in %s)\n", name, dir);
				free(buf);
				return 0;
			}
			g_nimg++;
		}
	}
	free(buf);
	return 1;
}

static int load_images(void)
{
	int i;
	printf("images\n");
	printf("  %-24s %10s  %-8s  %-8s %-8s %-8s  %s\n",
	       "name", "bytes", "load", "text", "data", "bss", "bss ends");
	for (i = 0; i < g_nimg; i++) {
		Image *im = &g_img[i];
		FILE *f = fopen(im->path, "rb");
		uint8_t *d;
		long n;
		uint32_t a;

		if (!f) { fprintf(stderr, "cannot open %s\n", im->path); return 0; }
		fseek(f, 0, SEEK_END); n = ftell(f); fseek(f, 0, SEEK_SET);
		d = malloc(n);
		if (fread(d, 1, n, f) != (size_t)n) { fclose(f); free(d); return 0; }
		fclose(f);
		im->size = n;

		if (n >= 28 && d[0] == 0x60 && d[1] == 0x1A) {
			im->has_hdr = 1;
			im->text = rd32(d + 2);
			im->data = rd32(d + 6);
			im->bss  = rd32(d + 10);
		}

		ram_add(im->addr, (uint32_t)n);
		for (a = 0; a < (uint32_t)n; a++)
			g_page[(im->addr + a) >> PAGE_BITS][(im->addr + a) & (PAGE_SIZE - 1)] = d[a];
		free(d);

		printf("  %-24s %10ld  %08X", im->name, n, im->addr);
		if (im->has_hdr) {
			uint32_t bss_end = im->addr + 28 + im->text + im->data + im->bss;
			printf("  %08X %08X %08X  %08X%s\n",
			       im->text, im->data, im->bss, bss_end,
			       (im->text + im->data + 28 == (uint32_t)n) ? "" : "  <- text+data != size");
			/* bss is left as-is: fresh pages are already zero. */
			ram_add(im->addr, 28 + im->text + im->data + im->bss);
		} else {
			printf("  %-8s %-8s %-8s  %-8s  (raw, no 601A header)\n", "-", "-", "-", "-");
		}
	}
	return 1;
}

/* --------------------------------------------------------------- reporting */

static int hit_cmp(const void *a, const void *b)
{
	const Hit *x = a, *y = b;
	uint32_t xt = x->reads + x->writes, yt = y->reads + y->writes;
	if (xt != yt) return xt < yt ? 1 : -1;
	return x->addr < y->addr ? -1 : 1;
}

static void sizes_str(uint8_t s, char *out)
{
	int n = 0;
	if (s & 1) out[n++] = 'b';
	if (s & 2) out[n++] = 'w';
	if (s & 4) out[n++] = 'l';
	out[n] = 0;
}

static void report(int top, const char *csv)
{
	Hit *v = malloc(sizeof(Hit) * (g_nhit ? g_nhit : 1));
	uint32_t i, n = 0;
	uint32_t region = 0xFFFFFFFFu, rcount = 0, rlow = 0, rhigh = 0;

	for (i = 0; i < HITCAP; i++) if (g_hit[i].used) v[n++] = g_hit[i];
	qsort(v, n, sizeof(Hit), hit_cmp);

	printf("\nunmapped bus accesses: %u reads, %u writes, %u distinct addresses%s\n",
	       g_reads_total, g_writes_total, n,
	       g_hit_dropped ? " (table full, some dropped)" : "");

	if (!n) { free(v); return; }

	/* Region summary: 64 KB granularity, sorted by address. */
	{
		Hit *byaddr = malloc(sizeof(Hit) * n);
		memcpy(byaddr, v, sizeof(Hit) * n);
		for (i = 0; i + 1 < n; i++) {	/* insertion sort by address */
			uint32_t j = i + 1;
			while (j > 0 && byaddr[j - 1].addr > byaddr[j].addr) {
				Hit t = byaddr[j - 1]; byaddr[j - 1] = byaddr[j]; byaddr[j] = t; j--;
			}
		}
		printf("\nregions touched (64K granularity)\n");
		for (i = 0; i < n; i++) {
			uint32_t r = byaddr[i].addr >> 16;
			if (r != region) {
				if (region != 0xFFFFFFFFu)
					printf("  %08X-%08X  %6u access  %08X..%08X\n",
					       region << 16, (region << 16) + 0xFFFF, rcount, rlow, rhigh);
				region = r; rcount = 0; rlow = byaddr[i].addr; rhigh = byaddr[i].addr;
			}
			rcount += byaddr[i].reads + byaddr[i].writes;
			if (byaddr[i].addr > rhigh) rhigh = byaddr[i].addr;
		}
		printf("  %08X-%08X  %6u access  %08X..%08X\n",
		       region << 16, (region << 16) + 0xFFFF, rcount, rlow, rhigh);
		free(byaddr);
	}

	printf("\ntop %u addresses by traffic\n", n < (uint32_t)top ? n : (uint32_t)top);
	printf("  %-10s %-5s %8s %8s  %-10s %s\n", "address", "size", "reads", "writes", "first pc", "last write");
	for (i = 0; i < n && i < (uint32_t)top; i++) {
		char sz[8];
		sizes_str(v[i].sizes, sz);
		printf("  %08X   %-5s %8u %8u  %08X", v[i].addr, sz, v[i].reads, v[i].writes, v[i].first_pc);
		if (v[i].wrote) printf("   %08X\n", v[i].last_write); else printf("\n");
	}

	if (csv) {
		FILE *f = fopen(csv, "w");
		if (!f) perror(csv);
		if (f) {
			fprintf(f, "address,sizes,reads,writes,first_pc,last_write\n");
			for (i = 0; i < n; i++) {
				char sz[8];
				sizes_str(v[i].sizes, sz);
				fprintf(f, "%08X,%s,%u,%u,%08X,%08X\n",
				        v[i].addr, sz, v[i].reads, v[i].writes, v[i].first_pc, v[i].last_write);
			}
			fclose(f);
			printf("\nwrote %s (%u rows)\n", csv, n);
		}
	}
	free(v);
}

/* An unmapped read from the vector table is the CPU taking an exception with
 * no vectors installed - far more informative than "pc went nowhere". */
static const char *vector_name(uint32_t addr)
{
	static const char *v[] = {
		"reset ssp", "reset pc", "bus error", "address error",
		"illegal instruction", "divide by zero", "chk", "trapv",
		"privilege violation", "trace", "line 1010 (A-line)",
		"line 1111 (F-line / FPU or coprocessor)", "-", "coprocessor protocol",
		"format error", "uninitialised interrupt"
	};
	uint32_t n;
	if (addr >= 0x400 || (addr & 3)) return NULL;
	n = addr >> 2;
	if (n < sizeof v / sizeof v[0]) return v[n];
	if (n >= 24 && n <= 31) return "autovector interrupt";
	if (n >= 32 && n <= 47) return "trap #n";
	if (n >= 48 && n <= 54) return "fpu exception";
	return "vector";
}

static void disasm_at(uint32_t pc, int count)
{
	int i;
	for (i = 0; i < count; i++) {
		char buf[128];
		unsigned n;
		if (!mapped(pc)) { printf("  %08X  <unmapped>\n", pc); return; }
		n = m68k_disassemble(buf, pc, g_dis_cpu);
		printf("  %08X  %s\n", pc, buf);
		pc += n;
	}
}

/* --------------------------------------------------------------- self test */

/* Smallest thing that fails if the harness breaks: a hand-assembled program
 * that pokes a known unmapped address, then halts on an unmapped PC. */
/* A synthetic display list, in the shape the ROM's emitters build: a leading
 * longword count, then a viewport record and an object record. Nothing in the
 * release exercises the decoder yet - a cockpit that has not started a game
 * never sends a render command - so this is what keeps it honest. */
static const uint32_t g_dl_test[] = {
	12 + 49 + 14,				/* longwords that follow        */
	8, 10, 0, 0, 479, 359, 480, 360, 239, 179, 0, 0,
	1, 47,					/* length is what follows these */
	0x3F800000, 0, 0,			/* +0x08: the matrix, identity  */
	0, 0x3F800000, 0,
	0, 0, 0x3F800000,
	0, 0, 0,				/* its translation row          */
	0, 0x3F800000,				/* +0x38, +0x3C                 */
	2,					/* +0x40: the viewport to use   */
	0, 0,
	479, 359,				/* +0x4C, +0x50: screen extent  */
	0,
	3,					/* +0x58: which type 7 record   */
	0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0,
	2,					/* +0x88: how many pick queries */
	120, 200, 0, 0, 0, 0, 0,		/* each seven longwords, the    */
	300, 90, 0, 0, 0, 0, 0,			/* first two a screen X and Y   */
	7, 12,					/* a type 7 record: the items   */
	0x040, 0, 0, 0, 0, 0, 0, 0,		/* an eight-longword item       */
	0x1E0, 0x4C4C4548, 0x0000004F,		/* "HELLO", bytes reversed      */
	0x000					/* end of the item stream       */
};

static uint32_t dl_test_read(uint32_t a)
{
	uint32_t i = (a - TI_TO_68K) / 4;
	return i < sizeof g_dl_test / sizeof g_dl_test[0] ? g_dl_test[i] : 0;
}

static int selftest_dlist(void)
{
	size_t mark = g_rsloglen;
	g_dl_read = dl_test_read;
	rstub_dlist(0);
	g_dl_read = m68k_read_memory_32;
	if (!strstr(g_rslog + mark, "viewport  (0,0)-(479,359)  480x360  centre (239,179)")) {
		printf("FAIL: viewport record not decoded\n%s", g_rslog + mark);
		return 1;
	}
	if (!strstr(g_rslog + mark,
		    "object    2 picks, 49 longwords, viewport 2, "
		    "items from record 3, screen 480x360") ||
	    !strstr(g_rslog + mark, "pick (120,200) -> entity 0 part 0") ||
	    !strstr(g_rslog + mark, "pick (300,90) -> entity 0 part 0")) {
		printf("FAIL: object record not decoded\n%s", g_rslog + mark);
		return 1;
	}
	/* Items now print their payload rather than their length, because the
	 * lengths were known and the meanings were not. */
	if (!strstr(g_rslog + mark, "item $040  0  0  0  0  0  0  0") ||
	    !strstr(g_rslog + mark, "item $1E0 \"HELLO\"") ||
	    !strstr(g_rslog + mark, "item $000\n")) {
		printf("FAIL: item stream not decoded\n%s", g_rslog + mark);
		return 1;
	}
	if (!strstr(g_rslog + mark, "   1.0000    0.0000    0.0000 \n"
				    "         0.0000    1.0000    0.0000 \n"
				    "         0.0000    0.0000    1.0000 \n"
				    "         0.0000    0.0000    0.0000 \n")) {
		printf("FAIL: object matrix not decoded\n%s", g_rslog + mark);
		return 1;
	}
	g_rsloglen = mark;
	g_rslog[mark] = 0;
	return 0;
}

static int selftest(void)
{
	if (selftest_dlist()) return 1;

	static const uint8_t prog[] = {
		0x23, 0xFC, 0xDE, 0xAD, 0xBE, 0xEF, 0x00, 0xFF, 0x00, 0x00,
							/* move.l #$DEADBEEF,$00FF0000 */
		0x4E, 0xF9, 0x7F, 0x00, 0x00, 0x00	/* jmp     $7F000000           */
	};
	uint32_t i, pc;

	ram_add(0x1000, 0x1000);
	for (i = 0; i < sizeof prog; i++)
		g_page[(0x1000 + i) >> PAGE_BITS][(0x1000 + i) & (PAGE_SIZE - 1)] = prog[i];

	m68k_init();
	m68k_set_cpu_type(M68K_CPU_TYPE_68020);
	m68k_pulse_reset();
	m68k_execute(1);		/* drains RESET_CYCLES; executes nothing */
	m68k_set_reg(M68K_REG_PC, 0x1000);
	m68k_set_reg(M68K_REG_SP, 0x2000);
	m68k_execute(1);
	m68k_execute(1);
	pc = m68k_get_reg(NULL, M68K_REG_PC);

	if (g_writes_total != 1)  { printf("FAIL: expected 1 unmapped write, got %u\n", g_writes_total); return 1; }
	if (g_hit[0].used == 0 && g_nhit != 1) { printf("FAIL: hit table empty\n"); return 1; }
	if (pc != 0x7F000000)     { printf("FAIL: pc = %08X, expected 7F000000\n", pc); return 1; }
	for (i = 0; i < HITCAP; i++)
		if (g_hit[i].used && g_hit[i].addr == 0x00FF0000 && g_hit[i].last_write == 0xDEADBEEF) {
			printf("selftest OK (cpu runs, unmapped writes logged, pc tracked)\n");
			return 0;
		}
	printf("FAIL: write to 00004000 not logged correctly\n");
	return 1;
}

/* -------------------------------------------------------------------- main */

static void usage(void)
{
	printf(
	"battlepod - VWE cockpit bring-up harness (phase 0)\n"
	"\n"
	"usage: battlepod <Load_script> [options]\n"
	"       battlepod --selftest\n"
	"\n"
	"memory\n"
	"  --ram BASE:LEN   declare a RAM region (hex, repeatable)\n"
	"                   default: 02000000:1000000 and 40000000:100000\n"
	"  --openbus HEX    value returned by unmapped reads (default FFFFFFFF)\n"
	"\n"
	"devices\n"
	"  --duart BASE     model the MC68681 DUART at BASE. Channel B is the\n"
	"                   console: its output is captured and its receiver fed\n"
	"  --duart-in TEXT  feed TEXT to the console receiver (\\r and \\n work)\n"
	"  --astub [ADDR]   stand in for the audio board (default 50001000):\n"
	"                   answer the signature and drain its download ring\n"
	"                   as fast as the 68020 fills it\n"
	"  --rirq [LEVEL]   let the renderer finish a frame: raise its vector 0x42\n"
	"                   interrupt after every render (default level 5)\n"
	"  --rstub ADDR     stand in for the TMS340 renderer: comm block at ADDR,\n"
	"                   acknowledge every command, log the queue, serve allocations\n"
	"  --poke ADDR=HEX  unmapped reads at ADDR return HEX\n"
	"  --set ADDR=HEX   write a longword into memory after loading, for answers\n"
	"                   a device would have left there - or to patch the firmware\n"
	"  --tick ADDR      unmapped long reads at ADDR return a rising counter,\n"
	"                   which walks past a poll-until-it-changes handshake\n"
	"\n"
	"running\n"
	"  --entry ADDR     override Go_Address\n"
	"  --sp ADDR        initial supervisor stack pointer (default 02FFFF00)\n"
	"  --steps N        instruction budget (default 200000000)\n"
	"  --cpu TYPE       68020 | 68030 | 68040 (default 68040, the only\n"
	"                   Musashi profile with the FPU enabled)\n"
	"  --headless       open no windows (cockpit): over RDP, in CI\n"
	"  --record FILE    the pod's own frames as video, 25 a second of its\n"
	"                   clock, through ffmpeg (on PATH); %d is the pod's node\n"
	"  --mech-dump FILE every Mech record of every display list, a line each\n"
	"\n"
	"reading the firmware\n"
	"  --trace N        disassemble the first N instructions\n"
	"  --trace-from N   start tracing at instruction N\n"
	"  --dis ADDR[:N]   disassemble N instructions at ADDR and exit\n"
	"  --top N          addresses to list in the report (default 40)\n"
	"  --csv FILE       write the full unmapped-access table\n"
	"\n"
	"Point it at a Load script from an extracted VWE release, e.g.\n"
	"  battlepod \"...../Console Files/Game Files/Full_Load_3_0\"\n");
}

int main(int argc, char **argv)
{
	const char *script = NULL, *csv = NULL;
	uint32_t set_addr[16], set_val[16];
	int nset = 0;
	unsigned cpu = M68K_CPU_TYPE_68040;
	uint32_t dis_at = 0;
	int dis_n = 32;
	const char *cpu_name = "68040";
	uint32_t sp = 0x02FFFF00, ramspec = 0;
	/* The firmware installs vector 71 at 0x0200011C, so its monitor left VBR
	 * at the CPU board's RAM base. Nothing in the release sets it itself. */
	uint32_t vbr = 0x02000000, sr = 0x2000, monitor_base = 0;
	int irq_level = 4;
	uint64_t budget = 200000000, trace_n = 0, trace_from = 0;
	int top = 40, i;
	uint64_t step;
	uint32_t pc = 0, blk_lo = 0xFFFFFFFFu, blk_hi = 0;
	uint32_t blk_regs[16] = {0};
	int blk_have = 0;

	/* A crash loses whatever stdout had buffered; this keeps it. */
	if (getenv("BATTLEPOD_UNBUFFERED")) setvbuf(stdout, NULL, _IONBF, 0);
	const char *stop = "instruction budget exhausted";

	for (i = 1; i < argc; i++) {
		const char *a = argv[i];
		if (!strcmp(a, "--selftest")) return selftest();
		else if (!strcmp(a, "-h") || !strcmp(a, "--help")) { usage(); return 0; }
		else if (!strcmp(a, "--ram") && i + 1 < argc) {
			char *c;
			uint32_t base = (uint32_t)strtoul(argv[++i], &c, 16);
			uint32_t len  = (*c == ':') ? (uint32_t)strtoul(c + 1, NULL, 16) : 0;
			if (!len) { fprintf(stderr, "--ram wants BASE:LEN in hex\n"); return 1; }
			ram_add(base, len);
			ramspec = 1;
		}
		else if (!strcmp(a, "--entry") && i + 1 < argc) { g_entry = (uint32_t)strtoul(argv[++i], NULL, 16); g_have_entry = 1; }
		else if (!strcmp(a, "--sp") && i + 1 < argc)      sp = (uint32_t)strtoul(argv[++i], NULL, 16);
		else if (!strcmp(a, "--vbr") && i + 1 < argc)     vbr = (uint32_t)strtoul(argv[++i], NULL, 16);
		else if (!strcmp(a, "--packet") && i + 1 < argc) {
			if (!pkt_add(argv[++i])) return 1;
		}
		else if (!strcmp(a, "--packet-file") && i + 1 < argc) {
			/* One packet per line, hex bytes, '#' starts a comment.
			 * A map is hundreds of packets, which a command line
			 * cannot carry. */
			char line[2048];
			FILE *pf = fopen(argv[++i], "r");
			if (!pf) { fprintf(stderr, "cannot read %s\n", argv[i]); return 1; }
			while (fgets(line, sizeof line, pf)) {
				char *c = strchr(line, '#');
				if (c) *c = 0;
				for (c = line; *c == ' ' || *c == '\t'; c++) ;
				if (*c == '\n' || *c == '\r' || !*c) continue;
				if (!pkt_add(c)) { fclose(pf); return 1; }
			}
			fclose(pf);
		}
		else if (!strcmp(a, "--wtrap") && i + 1 < argc) {
			char *c;
			g_wtrap_base = (uint32_t)strtoul(argv[++i], &c, 16);
			g_wtrap_len = (*c == ':') ? (uint32_t)strtoul(c + 1, NULL, 16) : 4;
		}
		else if (!strcmp(a, "--watch") && i + 1 < argc) {
			char *c;
			g_watch_base = (uint32_t)strtoul(argv[++i], &c, 16);
			g_watch_len = (*c == ':') ? (uint32_t)strtoul(c + 1, NULL, 16) : 0x1000;
		}
		else if (!strcmp(a, "--monitor")) {
			monitor_base = (i + 1 < argc && argv[i+1][0] != '-')
			             ? (uint32_t)strtoul(argv[++i], NULL, 16) : 0x02000400u;
		}
		else if (!strcmp(a, "--clock") && i + 1 < argc) {
			char *c;
			g_clock_addr = (uint32_t)strtoul(argv[++i], &c, 16);
			if (*c == ':') g_clock_div = (uint32_t)strtoul(c + 1, NULL, 0);
			if (!g_clock_div) g_clock_div = 1;
		}
		else if (!strcmp(a, "--sr") && i + 1 < argc)      sr = (uint32_t)strtoul(argv[++i], NULL, 16);
		else if (!strcmp(a, "--irq-level") && i + 1 < argc) irq_level = atoi(argv[++i]);
		else if (!strcmp(a, "--steps") && i + 1 < argc)   budget = strtoull(argv[++i], NULL, 0);
		else if (!strcmp(a, "--openbus") && i + 1 < argc) g_openbus = (uint32_t)strtoul(argv[++i], NULL, 16);
		else if (!strcmp(a, "--trace") && i + 1 < argc)   trace_n = strtoull(argv[++i], NULL, 0);
		else if (!strcmp(a, "--trace-from") && i + 1 < argc) trace_from = strtoull(argv[++i], NULL, 0);
		else if (!strcmp(a, "--top") && i + 1 < argc)     top = atoi(argv[++i]);
		else if (!strcmp(a, "--csv") && i + 1 < argc)     csv = argv[++i];
		else if (!strcmp(a, "--set") && i + 1 < argc) {
			char *c;
			if (nset >= 16) { fprintf(stderr, "too many --set" "\n"); return 1; }
			set_addr[nset] = (uint32_t)strtoul(argv[++i], &c, 16);
			set_val[nset++] = (*c == '=') ? (uint32_t)strtoul(c + 1, NULL, 16) : 0;
		}
		else if (!strcmp(a, "--rio-dump") && i + 1 < argc) g_riodump = argv[++i];
		else if (!strcmp(a, "--mesh") && i + 1 < argc)
			g_mesh_id = (uint32_t)strtoul(argv[++i], NULL, 0);
		else if (!strcmp(a, "--mesh-all")) g_mesh_all = 1;
		else if (!strcmp(a, "--peek") && i + 1 < argc) {
			char *c;
			if (g_peeks >= PEEKS) {
				printf("too many --peek: %d is the limit\n", PEEKS);
				return 2;
			}
			g_peek[g_peeks] = (uint32_t)strtoul(argv[++i], &c, 16);
			g_peekn[g_peeks] = (*c == ':') ? (uint32_t)strtoul(c + 1, NULL, 0) : 16;
			g_peeks++;
		}
		else if (!strcmp(a, "--rig-all")) g_rig_all = 1;
		else if (!strcmp(a, "--scene") && i + 1 < argc) g_scenefile = argv[++i];
		else if (!strcmp(a, "--scene-out") && i + 1 < argc) g_sceneout = argv[++i];
		else if (!strcmp(a, "--frame-out") && i + 1 < argc) g_frameout = argv[++i];
		else if (!strcmp(a, "--mech-dump") && i + 1 < argc) { g_mechdump_path = argv[++i]; g_capture = 1; }
		else if (!strcmp(a, "--record") && i + 1 < argc) { g_recpath = argv[++i]; g_capture = 1; }
		/* SDL's dummy driver: the windows exist, nobody sees them, and
		 * nothing waits for them to be closed. */
		else if (!strcmp(a, "--headless")) { putenv("SDL_VIDEODRIVER=dummy"); putenv("BATTLEPOD_NO_HOLD=1"); }
		else if (!strcmp(a, "--frame-at") && i + 1 < argc) g_frame_at = atoi(argv[++i]);
		else if (!strcmp(a, "--scene-drop") && i + 1 < argc) g_scenedrop = atoi(argv[++i]);
		else if (!strcmp(a, "--amiga") && i + 1 < argc) g_amiga = argv[++i];
		else if (!strcmp(a, "--scene-view") && i + 3 < argc) {
			g_sceneturn = (float)atof(argv[++i]);
			g_scenepitch = (float)atof(argv[++i]);
			g_scenezoom = (float)atof(argv[++i]);
		}
		else if (!strcmp(a, "--rig") && i + 1 < argc)
			g_rig_id = (uint32_t)strtoul(argv[++i], NULL, 0);
#ifdef BATTLEPOD_SDL
		else if (!strcmp(a, "--live")) {
			g_live = 1;
			if (i + 1 < argc && argv[i + 1][0] != '-') g_liveframes = argv[++i];
		}
		else if (!strcmp(a, "--live-pod")) {
			/* The main view shows the pod's own frames and the
			 * keyboard is its panel; see live_key. */
			g_live = 1;
			g_capture = 1;
			g_realtime = 1;
		}
#endif
		else if (!strcmp(a, "--set-at") && i + 2 < argc && g_setats < TAPS) {
			char *c;
			g_setat_pc[g_setats] = (uint32_t)strtoul(argv[++i], NULL, 16);
			g_setat_addr[g_setats] = (uint32_t)strtoul(argv[++i], &c, 16);
			g_setat_val[g_setats] = (*c == '=') ? (uint32_t)strtoul(c + 1, NULL, 16) : 0;
			g_setats++;
		}
		else if (!strcmp(a, "--tap") && i + 1 < argc) {
			/* Silently dropping the ninth tap cost an afternoon: the
			 * run looked like the call sites were never reached when
			 * the taps for them had never been installed. */
			if (g_taps >= TAPS) {
				printf("too many --tap: %d is the limit\n", TAPS);
				return 2;
			}
			g_tap[g_taps++] = (uint32_t)strtoul(argv[++i], NULL, 16);
		}
		else if (!strcmp(a, "--tap-dump") && i + 2 < argc) {
			g_tapoff = (int32_t)strtol(argv[++i], NULL, 0);
			g_tapdump = (uint32_t)strtoul(argv[++i], NULL, 0);
		}
		else if (!strcmp(a, "--rstub") && i + 1 < argc) {
			g_rstub = (uint32_t)strtoul(argv[++i], NULL, 16);
		}
		else if (!strcmp(a, "--vmtrace")) {
			g_vmtrace = (i + 1 < argc && argv[i+1][0] != '-')
			          ? (uint32_t)strtoul(argv[++i], NULL, 16) : VMTRACE_PC;
		}
		else if (!strcmp(a, "--rirq")) {
			g_rirq = 5;
			if (i + 1 < argc && argv[i+1][0] != '-') {
				char *c;
				g_rirq = (int)strtol(argv[++i], &c, 10);
				if (*c == ':') g_rirq_delay = (int)strtol(c + 1, NULL, 10);
			}
		}
		else if (!strcmp(a, "--astub")) {
			g_astub = (i + 1 < argc && argv[i+1][0] != '-')
			        ? (uint32_t)strtoul(argv[++i], NULL, 16) : 0x50001000u;
		}
		else if (!strcmp(a, "--poke") && i + 1 < argc) {
			char *c;
			if (g_npoke >= MAXPOKE) { fprintf(stderr, "too many --poke" "\n"); return 1; }
			g_poke_addr[g_npoke] = (uint32_t)strtoul(argv[++i], &c, 16);
			g_poke_val[g_npoke++] = (*c == '=') ? (uint32_t)strtoul(c + 1, NULL, 16) : 0;
		}
		else if (!strcmp(a, "--tick") && i + 1 < argc) {
			if (g_ntick >= MAXTICK) { fprintf(stderr, "too many --tick" "\n"); return 1; }
			g_tick_addr[g_ntick++] = (uint32_t)strtoul(argv[++i], NULL, 16);
		}
		else if (!strcmp(a, "--duart") && i + 1 < argc) {
			g_duart = (uint32_t)strtoul(argv[++i], NULL, 16);
		}
		else if (!strcmp(a, "--duart-in") && i + 1 < argc) {
			g_in[1] = unescape(argv[++i]);
			g_inlen[1] = strlen(g_in[1]);
		}
		/* The other direction on the Remote I/O link: what the panel board
		 * sends the CPU. The stick, throttle and pedals arrive this way, and
		 * nothing has ever driven this receiver before, so the bytes are
		 * given as hex - a control value is not text. */
		else if (!strcmp(a, "--rio-late") && i + 1 < argc) g_rio_late = atoi(argv[++i]);
		else if (!strcmp(a, "--realtime")) g_realtime = 1;
		else if (!strcmp(a, "--net") && i + 1 < argc) {
			if (!net_open(argv[++i])) { fprintf(stderr, "--net wants HOST:PORT\n"); return 1; }
			g_net = 1;
		}
		else if (!strcmp(a, "--net-node") && i + 1 < argc && g_setats + 2 <= TAPS) {
			/* This pod is node N: its address is net 1, node N, it
			 * sends broadcasts to the hub at node 0xFE, and it plays in
			 * game 1/0, which no pod is. A Mech's owner word is its
			 * pod's address; a hit on a Mech another pod owns goes to
			 * that pod as 0xBA, addressed to its node. A pod also
			 * forwards broadcasts not stamped with the game's address -
			 * and posts them too - so the hub drops what comes back to
			 * it forwarded (the origin at [4..5] is not the sender).
			 * Written once the event pump runs, as the monitor that
			 * read the DIP switch would have. */
			g_netnode = atoi(argv[++i]);
			g_setat_pc[g_setats] = 0x02122154;
			g_setat_addr[g_setats] = 0x0218AEB0;
			g_setat_val[g_setats++] = 0x010001FEu | ((uint32_t)(g_netnode & 0xFF) << 16);
			g_setat_pc[g_setats] = 0x02122154;
			g_setat_addr[g_setats] = 0x02179D30;
			g_setat_val[g_setats++] = 0x00000100u;
		}
		else if (!strcmp(a, "--send-log") && i + 1 < argc) {
			g_sendlog = fopen(argv[++i], "w");
			if (!g_sendlog) { fprintf(stderr, "cannot write %s\n", argv[i]); return 1; }
		}
		else if (!strcmp(a, "--rio-in") && i + 1 < argc) {
			static char buf[8192];
			const char *h = argv[++i];
			size_t n = 0;
			while (*h && n < sizeof buf) {
				char *e;
				long b;
				while (*h == ' ' || *h == ',') h++;
				if (!*h) break;
				b = strtol(h, &e, 16);
				if (e == h) break;
				buf[n++] = (char)b;
				h = e;
			}
			g_in[0] = buf;
			g_inlen[0] = (uint32_t)n;
		}
		else if (!strcmp(a, "--dis") && i + 1 < argc) {
			char *c;
			dis_at = (uint32_t)strtoul(argv[++i], &c, 16);
			if (*c == ':') dis_n = atoi(c + 1);
		}
		else if (!strcmp(a, "--cpu") && i + 1 < argc) {
			cpu_name = argv[++i];
			if      (!strcmp(cpu_name, "68020")) cpu = M68K_CPU_TYPE_68020;
			else if (!strcmp(cpu_name, "68030")) cpu = M68K_CPU_TYPE_68030;
			else if (!strcmp(cpu_name, "68040")) cpu = M68K_CPU_TYPE_68040;
			else { fprintf(stderr, "--cpu wants 68020, 68030 or 68040\n"); return 1; }
		}
		else if (a[0] == '-') { fprintf(stderr, "unknown option %s\n", a); return 1; }
		else script = a;
	}

	if (!script) { usage(); return 1; }

	if (g_astub) ram_add(g_astub, ASTUB_LEN);

	if (g_rirq) ram_add(RIRQ_CSR & ~0xFFu, 0x100);

	if (g_rstub) {
		ram_add(RSTUB_TI_BASE, RSTUB_TI_LEN);
		ram_add(g_rstub, RSTUB_WINDOW);
		ram_add(RSTUB_HEAP_68K, RSTUB_HEAP_LEN);
	}

	if (!ramspec) {
		ram_add(0x02000000, 0x01000000);	/* cockpit CPU board RAM */
		ram_add(0x40000000, 0x00100000);	/* window onto the Amiga board */
	}

	printf("battlepod phase 0 - %s\n\n", script);
	if (!load_script(script)) return 1;
	if (!load_images()) return 1;
	for (i = 0; i < nset; i++) {
		ram_add(set_addr[i], 4);
		m68k_write_memory_32(set_addr[i], set_val[i]);
		printf("  set %08X = %08X\n", set_addr[i], set_val[i]);
	}

	/* The secondary display runs instead of the cockpit firmware, not beside
	 * it: a different program for a different board, and the first time
	 * anything here has run one. */
	if (g_amiga) {
		if (!amiga_load(g_amiga)) return 1;
		g_entry = 0;
		g_have_entry = 1;
	}

	if (!g_have_entry) { fprintf(stderr, "no Go_Address in script and no --entry\n"); return 1; }

	if (dis_at) {
		printf("\ndisassembly at %08X\n", dis_at);
		disasm_at(dis_at, dis_n);
		return 0;
	}

	m68k_init();
	m68k_set_cpu_type(cpu);
	m68k_pulse_reset();		/* reads vectors from 0; logged, then overridden */
	m68k_execute(1);		/* drains RESET_CYCLES; executes nothing */
	m68k_set_reg(M68K_REG_PC, g_entry);
	m68k_set_reg(M68K_REG_SP, sp);
	m68k_set_reg(M68K_REG_SR, sr);
	m68k_set_reg(M68K_REG_VBR, vbr);
	g_vbr = vbr;
	if (monitor_base) mon_install(monitor_base);
	if (g_astub) poke32(g_astub, ASTUB_SIG);

	if (g_rstub) {
		m68k_write_memory_32(RSTUB_PTR, g_rstub - TI_TO_68K);
		m68k_write_memory_32(RSTUB_FLAG, RSTUB_MAGIC);
	}

	/* Reset's vector fetch is not the pod's doing; don't pollute the report. */
	memset(g_hit, 0, sizeof g_hit);
	g_nhit = g_hit_dropped = g_reads_total = g_writes_total = g_vector_hit = 0;

	printf("\ncpu %s%s\n", cpu_name,
	       cpu == M68K_CPU_TYPE_68040
	         ? "  (board is a 68020+68881; Musashi enables its FPU on the 040 profile only)"
	         : "  (no FPU: Musashi enables FPU ops on the 040 profile only)");
	printf("entry %08X, sp %08X, vbr %08X, sr %04X, openbus %08X\n",
	       g_entry, sp, vbr, sr, g_openbus);
	printf("budget %llu instructions, duart irq level %d\n",
	       (unsigned long long)budget, irq_level);
#ifdef BATTLEPOD_SDL
	if (g_live && !live_open(g_liveframes)) return 1;
#endif
	if (g_recpath) rec_open();
	printf("running...\n\n");

	for (step = 0; step < budget; step++) {
		pc = m68k_get_reg(NULL, M68K_REG_PC);

		{
			int lvl = duart_irq() ? irq_level : 0;
			if (g_rirq_pending > 1) g_rirq_pending--;
			if (rirq_asserted() && g_rirq > lvl) lvl = g_rirq;
			m68k_set_irq((unsigned)lvl);
		}
		if ((step % g_clock_div) == 0) clock_tick();
		if (g_net && (step & 0xFFF) == 0) net_poll(g_clock_val);
		if (g_realtime && (step & 0xFFF) == 0) realtime_pace();
		if (g_rec && (step & 0xFFF) == 0) rec_poll();
		if (g_monstub && (pc - g_monstub) < MON_SLOTS * MON_STUB_SZ &&
		    !((pc - g_monstub) % MON_STUB_SZ)) {
			uint32_t slot = (pc - g_monstub) / MON_STUB_SZ;
			g_moncall[slot]++;
			if (slot == MON_SLOT_RECV) mon_recv_polled();
			if (slot == MON_SLOT_SEND) mon_send_called();
		}

		if (g_vmtrace && pc == g_vmtrace && g_vmtrace_n < VMTRACE_MAX) {
			uint32_t a6 = m68k_get_reg(NULL, M68K_REG_A6);
			g_vmpcs[g_vmtrace_n] = m68k_read_memory_32(a6 + VMTRACE_FRAME_PC);
			g_vmops[g_vmtrace_n++] =
				(uint8_t)m68k_get_reg(NULL, M68K_REG_D0);
		}

		if (g_taps || g_setats) tap_check(pc);

#ifdef BATTLEPOD_SDL
		if (g_live && step % LIVE_EVERY == 0) {
			live_pump(step);
			if (g_quit) { stop = "window closed"; break; }
		}
#endif

		if (!mapped(pc)) { stop = "pc left mapped memory"; break; }
		if (g_vector_hit) { stop = "took an exception with no vector table"; break; }
		if (g_net_quit) { stop = "the hub said quit"; break; }

		if (trace_n && step >= trace_from && step < trace_from + trace_n) {
			char buf[128];
			m68k_disassemble(buf, pc, g_dis_cpu);
			printf("%8llu  %08X  %-40s", (unsigned long long)step, pc, buf);
			g_note_flag = 0;
			m68k_execute(1);
			if (g_note_flag) printf("  <- unmapped %08X", g_note_addr);
			printf("\n");
		} else {
			m68k_execute(1);
		}

		/* Spin detector. A narrow PC window alone is not enough - a memset
		 * loop looks identical - so also require the register file to come
		 * back unchanged across the block. A real wait-for-hardware loop
		 * makes no progress; a memset advances its pointer and counter. */
		if (pc < blk_lo) blk_lo = pc;
		if (pc > blk_hi) blk_hi = pc;
		if ((step & 0xFFFF) == 0xFFFF) {
			uint32_t regs[16];
			int r, same = 1;
			for (r = 0; r < 16; r++) regs[r] = m68k_get_reg(NULL, M68K_REG_D0 + r);
			for (r = 0; r < 16; r++) if (regs[r] != blk_regs[r]) { same = 0; break; }
			if (same && blk_have && blk_hi - blk_lo < 256) {
				stop = "spinning: narrow pc window, no register progress";
				break;
			}
			memcpy(blk_regs, regs, sizeof regs);
			blk_have = 1;
			blk_lo = 0xFFFFFFFFu; blk_hi = 0;
		}
	}

#ifdef BATTLEPOD_SDL
	if (g_live) { live_hold(step); live_close(); }
#endif
	if (g_rec) rec_close();
	printf("\nstopped after %llu instructions: %s\n", (unsigned long long)step, stop);
	printf("pc %08X  sp %08X  sr %04X\n",
	       m68k_get_reg(NULL, M68K_REG_PC), m68k_get_reg(NULL, M68K_REG_SP),
	       m68k_get_reg(NULL, M68K_REG_SR));
	printf("\ncode at the stop point\n");
	disasm_at(m68k_get_reg(NULL, M68K_REG_PPC), 8);

	if (g_vmtrace_n) {
		unsigned k;
		printf("\nmission opcodes executed: %u\n", g_vmtrace_n);
		for (k = 0; k < g_vmtrace_n; k++)
			printf("%08X:%02X%s", g_vmpcs[k], g_vmops[k],
			       (k % 8 == 7) ? "\n" : " ");
		if (g_vmtrace_n % 8) printf("\n");
	}

	if (g_rscmd) {
		printf("%srenderer commands: %d posted%s", "\n", g_rscmd, "\n");
		fwrite(g_rslog, 1, g_rsloglen, stdout);
	}

	if (g_mon) {
		int i, any = 0;
		printf("\nboot monitor services called (table at %08X)\n", g_mon);
		for (i = 0; i < MON_SLOTS; i++)
			if (g_moncall[i]) {
				printf("  +%02X  x%u\n", i * 4, g_moncall[i]);
				any = 1;
			}
		if (!any) printf("  none\n");
	}

	if (g_rig_id) {
		int n = rig_assemble(g_rig_id), i;
		printf("\nskeleton %u: %d parts, %d vertices, %d polygons\n",
		       g_rig_id, n, g_rig.nvert, g_rig.npoly);
		for (i = 0; i < n; i++)
			printf("   node %2d  model %3u  at %6.2f %6.2f %6.2f\n",
			       g_placed[i].node, g_placed[i].id, g_placed[i].at[0],
			       g_placed[i].at[1], g_placed[i].at[2]);
	}

	if (g_peeks) peek_report();
	if (g_scenefile) scene_report();
	if (g_frameout) frame_report();
	if (g_pkt_queued)
		printf("\npackets: %u queued, the wire polled %d times\n",
		       g_pkt_queued, g_pkt_delivered);
	if (g_net)
		printf("net: %u datagrams in, %u packets out\n", g_net_in, g_net_out);
	if (g_sent)
		printf("packets: %u transmitted\n", g_sent);
	if (g_sendlog) fclose(g_sendlog);
	if (g_rig_all) rig_all();
	if (g_mesh_all) mesh_all();
	if (g_mesh_id) mesh_report();

	if (g_rio_tx && g_riodump) rio_dump(g_riodump);

	if (g_rio_tx) {
		uint32_t i, n = g_rio_tx < RIOCAP ? g_rio_tx : RIOCAP;
		printf("\nremote i/o: %u bytes sent on duart channel A\n", g_rio_tx);
		for (i = 0; i < n; i++) {
			if (i % 16 == 0) printf("  %04X ", i);
			printf(" %02X", g_riobuf[i]);
			if (i % 16 == 15 || i + 1 == n) printf("\n");
		}
		rio_report();
	}

	if (g_inlen[1])
		printf("\nconsole input: %u of %u bytes consumed\n",
		       (unsigned)g_inpos[1], (unsigned)g_inlen[1]);

	if (g_conlen) {
		printf("\nconsole output (%u bytes)\n", (unsigned)g_conlen);
		printf("----------------------------------------------------------------\n");
		fwrite(g_conbuf, 1, g_conlen, stdout);
		printf("\n----------------------------------------------------------------\n");
	}

	report(top, csv);
	return 0;
}
