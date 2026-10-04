# The wire between pods and the hub

A pod is `battlepod.exe` or `cockpit.exe` started with `--net HOST:PORT`
(and `--net-node N`); a hub is `tools/hub.py`, which listens on UDP port 5170
by default and launches its pods pointed at itself. This file is every
datagram that crosses between them. The game packets inside are the pod's
own, on the wire exactly as its ARCNET driver would have sent and received
them; what they mean is [DEVICES.md](DEVICES.md), *Two pods*, and
`tools/netmsg.py` lists them from the firmware itself.

One ARCNET frame is one UDP datagram, so frame boundaries survive and a game
across the internet is the same code as one on a LAN
([ARCHITECTURE.md](ARCHITECTURE.md), *Networking*). The hub is the segment
and the operator console, nothing more.

## Datagrams

The first byte says what the rest is.

| from | byte 0 | then | meaning |
|---|---|---|---|
| pod | `H` | node (1 byte) | hello: "I am node N". Sent every 50 hundredths of the pod's clock until anything comes back |
| pod | `P` | node (1 byte), packet | a packet the firmware transmitted, to node N; `0xFE` is a broadcast |
| hub | `A` | - | heard you; any datagram stops the hellos |
| hub | `P` | packet | deliver this packet to the firmware, as if received off the wire |
| hub | `R` | Remote I/O bytes | panel input, appended to DUART channel A: framed reports, `01 00 len len data... sum` |
| hub | `Q` | - | quit: the pod ends its run and prints its report |

Source: `net_poll` and `net_send_packet` in `src/battlepod.c`, `receive` and
`from_pod` in `tools/hub.py`.

## Packets

A packet is the firmware's own message: opcode at `+0x00`, the origin's net
and node at `+0x04`/`+0x05`, the addressee's net and node at `+0x08`/`+0x09`
(`hub.py`'s `addressed()`), then the body. With `--net-node N` a pod is net 1,
node N, playing in game 1/0, which no pod is.

The hub routes by the node byte of `P`: a broadcast goes to every other pod,
any other node to that one pod. It drops a packet whose origin is not its
sender - a pod forwards the broadcasts it receives, as a router would, and
those would otherwise go round for ever - and it never relays the console's
own opcodes (`0xE5`, `0xEE`, `0xC4`, `0xC6`, `0xF6`-`0xFF`) back from pods.

The hub reads some packets going past rather than only relaying them:

| opcode | the hub uses it for |
|---|---|
| `0xEC` | position broadcast: thing at `+0x08`, then x, y, z, heading, speed as big-endian floats from `+0x0C`. The operator's view and the CPU pilots are made of these |
| `0xEA` | a hit reported by the owner: thing, shooter, location at `+0x08`; location `-1` is destroyed |
| `0xED` | a pod relinking its pilot, which it does when its Mech dies |

## Panel input

A CPU pilot flies its pod with the same Remote I/O reports the panel board
sends, in `R` datagrams:

| report | meaning |
|---|---|
| `C0 id hi lo` | analog `id` to a 16-bit value: `A0` throttle (0 to `0x340`), `A1`/`A2` stick left/right |
| `B1 id` / `B0 id` | button `id` down / up: `A5` trigger, `40` target select, `20` searchlight, `33` and `31` the mode buttons |

`cockpit.exe --live-pod` builds the same reports from the keyboard
(`live_key` in `src/battlepod.c`).

## Example

```
python tools/hub.py --bots 2 --arena --console
```

starts two pods on nodes 1 and 2, waits for each `H`, sends each the
start-of-game packets (a welcome with the visibility range, a `MECH_CLASS`
per vehicle, the map as `0xE4`s, `PLAYER_LINK` to its own Mech), then relays
and flies them. Each pod's own output is in `build/pod<N>.log`.
