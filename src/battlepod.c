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

#include "m68k.h"

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

static int rx_pending(int chan) { return g_inpos[chan] < g_inlen[chan]; }

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

/* Musashi asks what vector to use when it takes the interrupt. The 68681 is
 * programmed for vectored interrupts, so answer with whatever the firmware
 * wrote to the interrupt vector register. */
int bp_int_ack(unsigned int level)
{
	(void)level;
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

/* Turn the captured channel A byte stream back into cockpit panel state.
 * Frames are 01 <node> <len> <node+len> <payload> <sum(payload)>, and the
 * payload opcodes are the ones the firmware's own diagnostic menu exposes.
 * This is what a panel renderer would consume: which lamp is lit and how
 * brightly, where each bar graph stands, what each soft-label display reads. */

#define RIO_LAMP_MAX  0x80
#define RIO_DEV_LO    0x80		/* displays and bar graphs share these ids */
#define RIO_DEV_HI    0x92

static uint8_t g_lamp[RIO_LAMP_MAX];
static int     g_lamp_set[RIO_LAMP_MAX];
static uint8_t g_bar[RIO_DEV_HI];
static int     g_bar_set[RIO_DEV_HI];
static char    g_text[RIO_DEV_HI][9];
static int     g_text_set[RIO_DEV_HI];

static void rio_apply(const uint8_t *p, uint32_t n)
{
	uint32_t i;
	if (n < 1) return;
	switch (p[0]) {
	case 0xD1:				/* display: id, 8 characters */
		if (n >= 2 && p[1] >= RIO_DEV_LO && p[1] < RIO_DEV_HI) {
			for (i = 0; i + 2 < n && i < 8; i++) g_text[p[1]][i] = (char)p[2 + i];
			g_text_set[p[1]] = 1;
		}
		break;
	case 0xD2:				/* bar graph: id, bars lit */
		if (n >= 3 && p[1] >= RIO_DEV_LO && p[1] < RIO_DEV_HI) {
			g_bar[p[1]] = p[2];
			g_bar_set[p[1]] = 1;
		}
		break;
	case 0xD3:				/* lamp: id, brightness */
		if (n >= 3 && p[1] < RIO_LAMP_MAX) {
			g_lamp[p[1]] = p[2];
			g_lamp_set[p[1]] = 1;
		}
		break;
	default:
		break;			/* D5 and anything else: no panel state */
	}
}

static void rio_report(void)
{
	uint32_t at = 0, frames = 0, bad = 0, n = g_rio_tx < RIOCAP ? g_rio_tx : RIOCAP;
	int i, any;

	while (at + 4 <= n) {
		uint32_t len, j;
		uint8_t sum = 0;
		if (g_riobuf[at] != 0x01) { at++; bad++; continue; }
		len = g_riobuf[at + 2];
		if (at + 5 + len > n) break;
		if ((uint8_t)(g_riobuf[at + 1] + g_riobuf[at + 2]) != g_riobuf[at + 3]) bad++;
		for (j = 0; j < len; j++) sum = (uint8_t)(sum + g_riobuf[at + 4 + j]);
		if (sum != g_riobuf[at + 4 + len]) bad++;
		rio_apply(&g_riobuf[at + 4], len);
		frames++;
		at += 5 + len;
	}

	printf("%sremote i/o: %u frames decoded%s%s", "\n", frames,
	       bad ? " (checksum or framing errors)" : "", "\n");

	any = 0;
	for (i = 0; i < RIO_LAMP_MAX; i++)
		if (g_lamp_set[i]) { printf("  lamp %02X brightness %02X%s", i, g_lamp[i], "\n"); any = 1; }
	for (i = RIO_DEV_LO; i < RIO_DEV_HI; i++)
		if (g_bar_set[i]) { printf("  bargraph %02X bars %u%s", i, g_bar[i], "\n"); any = 1; }
	for (i = RIO_DEV_LO; i < RIO_DEV_HI; i++)
		if (g_text_set[i]) { printf("  display %02X \"%.8s\"%s", i, g_text[i], "\n"); any = 1; }
	if (!any) printf("  no panel state changed%s", "\n");
}

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
#define MON_PKT_OFF   0x400		/* received-packet buffer, past the stubs */
#define MON_SLOT_RECV 6			/* +0x18: poll for a received packet */

static uint32_t g_mon, g_monstub;
static uint32_t g_moncall[MON_SLOTS];
static uint8_t  g_pkt[512];
static uint32_t g_pktlen;
static int      g_pkt_delivered;

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

	for (i = 0; i < MON_SLOTS; i++) {
		mon_slot(i, MON_STUB_NULL, sizeof MON_STUB_NULL);
		m68k_write_memory_32(base + i * 4, g_monstub + i * MON_STUB_SZ);
	}

	if (!g_pktlen) return;

	/* Hand the firmware one packet. Its header is a word it does not read
	 * here, then the body length, then the body - the receive path takes the
	 * length from [pkt+2] and the opcode from [pkt+4]. */
	{
		uint32_t buf = base + MON_PKT_OFF;
		uint8_t  ret[10] = { 0x20,0x7C, 0,0,0,0, 0x4A,0x88, 0x4E,0x75 };
		m68k_write_memory_32(buf, g_pktlen);	/* [+0] word, [+2] length */
		for (i = 0; i < g_pktlen; i++) m68k_write_memory_8(buf + 4 + i, g_pkt[i]);
		ret[2] = (uint8_t)(buf >> 24); ret[3] = (uint8_t)(buf >> 16);
		ret[4] = (uint8_t)(buf >> 8);  ret[5] = (uint8_t)buf;
		mon_slot(MON_SLOT_RECV, ret, sizeof ret);	/* movea.l #buf,A0; tst.l A0; rts */
	}
}

/* Deliver the packet exactly once: on the second poll, put the NULL stub back
 * before it executes. */
static void mon_recv_polled(void)
{
	if (!g_pktlen) return;
	if (g_pkt_delivered) mon_slot(MON_SLOT_RECV, MON_STUB_NULL, sizeof MON_STUB_NULL);
	else g_pkt_delivered = 1;
}

/* --clock: a free-running counter in RAM. The firmware reads 0x02000808 in 336
 * places and writes it nowhere, so the pod's boot monitor maintained it as a
 * millisecond timebase. Without one, every timeout in the game waits forever. */
static uint32_t g_clock_addr, g_clock_div = 4096, g_clock_val;

static void clock_tick(void)
{
	uint8_t *p;
	uint32_t o;
	if (!g_clock_addr) return;
	p = g_page[g_clock_addr >> PAGE_BITS];
	if (!p) return;
	o = g_clock_addr & (PAGE_SIZE - 1);
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

#define RS_OP_RESET 1
#define RS_OP_ALLOC 2

static uint32_t g_rstub;		/* 68k address of the comm block, 0 = off */
static uint32_t g_rsheap = RSTUB_HEAP_68K - TI_TO_68K;	/* next free, TI byte address */
static uint32_t g_rshandle;
static int      g_rscmd;
static char     g_rslog[262144];
static size_t   g_rsloglen;

static void rslog(const char *fmt, ...)
{
	va_list ap;
	int n;
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

	rs_put(4, 0);			/* command complete */
	m68k_write_memory_32(RSTUB_FLAG, RSTUB_MAGIC);	/* renderer ready again */
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

void m68k_write_memory_8(unsigned int a, unsigned int v)
{
	uint8_t *p = g_page[a >> PAGE_BITS];
	if (p) { p[a & (PAGE_SIZE - 1)] = (uint8_t)v; return; }
	duart_write(a, v);
	note(a, 1, 1, v & 0xFF);
}

void m68k_write_memory_16(unsigned int a, unsigned int v)
{
	uint8_t *p = g_page[a >> PAGE_BITS];
	uint32_t o = a & (PAGE_SIZE - 1);
	if (p && o <= PAGE_SIZE - 2) { p[o] = (uint8_t)(v >> 8); p[o+1] = (uint8_t)v; return; }
	if (!p && o <= PAGE_SIZE - 2) { note(a, 2, 1, v & 0xFFFF); return; }
	m68k_write_memory_8(a, v >> 8);
	m68k_write_memory_8(a + 1, v);
}

void m68k_write_memory_32(unsigned int a, unsigned int v)
{
	uint8_t *p = g_page[a >> PAGE_BITS];
	uint32_t o = a & (PAGE_SIZE - 1);
	if (p && o <= PAGE_SIZE - 4) {
		p[o] = (uint8_t)(v >> 24); p[o+1] = (uint8_t)(v >> 16);
		p[o+2] = (uint8_t)(v >> 8); p[o+3] = (uint8_t)v;
		if (g_rstub) {
			if (a >= g_rstub && a < g_rstub + RSTUB_WINDOW)
				rstub_write(a - g_rstub, v);
			else if (a == RSTUB_FLAG)
				rstub_flag_write(v);
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
static int selftest(void)
{
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
			const char *h = argv[++i];
			g_pktlen = 0;
			while (*h && g_pktlen < sizeof g_pkt) {
				char *e;
				long b;
				while (*h == ' ' || *h == ',') h++;
				if (!*h) break;
				b = strtol(h, &e, 16);
				if (e == h) { fprintf(stderr, "--packet wants hex bytes\n"); return 1; }
				g_pkt[g_pktlen++] = (uint8_t)b;
				h = e;
			}
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
		else if (!strcmp(a, "--rstub") && i + 1 < argc) {
			g_rstub = (uint32_t)strtoul(argv[++i], NULL, 16);
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
	printf("running...\n\n");

	for (step = 0; step < budget; step++) {
		pc = m68k_get_reg(NULL, M68K_REG_PC);

		m68k_set_irq(duart_irq() ? (unsigned)irq_level : 0);
		if ((step % g_clock_div) == 0) clock_tick();
		if (g_monstub && (pc - g_monstub) < MON_SLOTS * MON_STUB_SZ &&
		    !((pc - g_monstub) % MON_STUB_SZ)) {
			uint32_t slot = (pc - g_monstub) / MON_STUB_SZ;
			g_moncall[slot]++;
			if (slot == MON_SLOT_RECV) mon_recv_polled();
		}

		if (!mapped(pc)) { stop = "pc left mapped memory"; break; }
		if (g_vector_hit) { stop = "took an exception with no vector table"; break; }

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

	printf("\nstopped after %llu instructions: %s\n", (unsigned long long)step, stop);
	printf("pc %08X  sp %08X  sr %04X\n",
	       m68k_get_reg(NULL, M68K_REG_PC), m68k_get_reg(NULL, M68K_REG_SP),
	       m68k_get_reg(NULL, M68K_REG_SR));
	printf("\ncode at the stop point\n");
	disasm_at(m68k_get_reg(NULL, M68K_REG_PPC), 8);

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
