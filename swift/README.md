# QLab Flash — native (Swift / SwiftUI) rewrite

This folder is a **starter scaffold** for a native macOS + iPadOS version of QLab
Flash. It was written without a Mac/Xcode in the loop, so treat it as a running
start to **build and iterate in Xcode / via the local Claude Code CLI** — not as
finished, compiled code.

The working, shipping app today is the Python/PySide6 version in the repo root.
This rewrite exists to enable **iPad** (which Qt/Python can't target) and App
Store distribution.

---

## Architecture

Two pieces:

1. **`QLabFlashCore`** — a SwiftPM library (pure logic + networking, no UI). This
   ports directly from the Python app and is **unit-tested**, so you can validate
   it immediately:
   ```bash
   cd swift
   swift build
   swift test
   ```
   - `OSC.swift` — OSC 1.0 encode/decode + **SLIP** framing for TCP.
   - `QLabClient.swift` — OSC over TCP (SLIP) / UDP via `Network.framework`;
     discover workspaces, connect, read cue lists, read/write cue properties.
   - `X32.swift` — direct UDP sender for scribble-strip channel names.
   - `Model.swift` — the cue tree → mic grid: dynamic "anchor cue" detection,
     `parameterValues` parsing, dirty tracking, channel-rename → cue renames,
     scribble writes.
   - `Config.swift` — settings.

2. **`App/`** — SwiftUI sources for the macOS + iPadOS app. These are **sketches**
   to drop into an Xcode app target (multiplatform). The grid + selection is the
   main net-new work (see below).

> Why split this way: SwiftPM (`Package.swift`) is text-only and builds/tests from
> the command line with no Xcode project file. The **app target** needs an
> `.xcodeproj` (Info.plist, asset catalog, multiplatform settings) that's best
> created in Xcode — have local Claude run "create a multiplatform SwiftUI app
> target that depends on the QLabFlashCore package, and move the files in `App/`
> into it."

---

## What ports cleanly vs. what's net-new

**Ports cleanly (logic is identical to the tested Python app):**
- OSC encode/decode + SLIP.
- QLab flow: `/workspaces`, `/workspace/{id}/connect`, `/workspace/{id}/cueLists`,
  `/workspace/{id}/cue_id/{uid}/{prop}` (read/write), `parameterValues`.
- The data model: a cue becomes an **anchor** (gets the 32 checkboxes) when its
  subtree has mic cues with no duplicate channels; the highest such cue wins.
- Reading state from `parameterValues` like `["ch", 1, "mix", "on", 0]`
  (0 = muted, 1 = unmuted), and writing it back as JSON.
- Renaming a mic → relabel column + rename that channel's cue everywhere + push
  X32 scribble strip (`/ch/NN/config/name`).
- 30-step undo.

**Net-new (the real work, needs Mac iteration):**
- The **spreadsheet grid**: cues as rows (expandable tree), mics 1–32 as columns,
  centered checkboxes, vertical name headers, green/amber tints.
- **Drag-to-select a rectangular block of cells** — free in Qt's table, custom in
  SwiftUI. This is the #1 schedule risk; prototype it first.
- **iPad touch UX** — block selection, bulk edit, and a 32-wide grid on a tablet
  need a touch-first design (not the mouse UI shrunk).
- Native menus (macOS), Connect/Mixer/Diagnose/Help screens, About.

---

## Behaviour reference (match the Python app)

- **Checked = unmuted (ON), unchecked = muted (OFF).**
- Mic cue recognition: a Network cue whose `parameterValues` is
  `["ch", <int channel 1..32>, "mix", "on", <0|1>]`. A `{channel}` placeholder
  (channel = null) can't map to a column — count it and tell the user to set a
  concrete channel number.
- Read `parameterValues` (raw, not stringified). Write it back by replacing the
  last element with 0/1, preserving its type (QLab stores it as a string like
  `"0"` sometimes), sent as a JSON string to `…/cue_id/{uid}/parameterValues`.
- Transport: **TCP is required** for `cueLists` (replies exceed a UDP datagram);
  QLab uses double-END SLIP framing and replies on the same connection.
- Submit pushes: changed mic states + changed cue names (QLab) + changed mic
  names to the X32 scribble strips (direct UDP, port 10023).

See the Python sources for the exact, tested logic:
`qlabflash/osc.py`, `qlab.py`, `model.py`, `session.py`, `mixer.py`, `config.py`.

---

## Suggested build order (for local Claude Code)

1. `swift build && swift test` — get the core green (fix any porting issues the
   compiler finds; the tests mirror the Python tests).
2. Create the multiplatform SwiftUI app target in Xcode, depending on
   `QLabFlashCore`. Wire a basic Connect screen → load a workspace → print the
   model to confirm the core works against real QLab over the network.
3. Build the **grid** (start simple: a scrolling table of rows × 32 toggles).
4. Add **drag-select** (the hard part) — prototype on macOS first, then adapt the
   gesture for iPad touch.
5. Layer in: bulk edit, undo, mic/cue renaming, Mixer settings, submit, reload,
   diagnose, OSC log, About/Help/Contact.
6. Sign + notarize (you already have the Developer ID set up) and/or submit to the
   App Store.
