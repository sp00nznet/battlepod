/* Musashi configuration for battlepod.
 *
 * Selected with -DMUSASHI_CNF='"battlepod_m68kconf.h"', which is the hook
 * Musashi provides for exactly this. Its own m68kconf.h guards every option
 * with #ifndef, so including it first and overriding after leaves the rest of
 * the defaults alone.
 *
 * The cockpit's MC68681 is configured for vectored interrupts - it programs
 * its interrupt vector register to 0x47 - so autovectoring is not enough.
 */

#include "m68kconf.h"

#undef  M68K_EMULATE_INT_ACK
#define M68K_EMULATE_INT_ACK     M68K_OPT_SPECIFY_HANDLER

#undef  M68K_INT_ACK_CALLBACK
#define M68K_INT_ACK_CALLBACK(A) bp_int_ack(A)

int bp_int_ack(unsigned int level);
