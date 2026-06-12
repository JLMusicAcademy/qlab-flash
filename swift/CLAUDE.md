# CLAUDE.md — QLab Flash (Swift / SwiftUI rewrite)

Guidance for Claude Code running **locally on the Mac Mini** (with Xcode) when
working in this `swift/` folder.

## What this is

A native macOS + iPadOS rewrite of QLab Flash. The shipping app today is the
Python/PySide6 version in the repo root — it works, is signed + notarized, and
is the **source of truth for behaviour**. This rewrite exists to reach **iPad**
(Qt can't) and the App Store.

## Layout

```
swift/
  Package.swift                 SwiftPM manifest: library QLabFlashCore (no UI)
  Sources/QLabFlashCore/        Pure logic + networking (UNIT-TESTED — port target)
    OSC.swift                   OSC 1.0 encode/decode + SLIP framing
    JSONValue.swift             Dynamic JSON for QLab replies / parameterValues
    Config.swift                Settings (mirrors qlabflash/config.py)
    Model.swift                 Cue tree → mic grid, anchor detection, writes
    QLabClient.swift            Async OSC-over-TCP (Network.framework)
    X32.swift                   UDP scribble-strip sender
  Tests/QLabFlashCoreTests/     Mirror the Python tests
  App/                          SwiftUI SKETCHES to move into an Xcode app target
    QLabFlashApp.swift, AppStore.swift, ContentView.swift,
    MicGridView.swift, Dialogs.swift
```

## First commands

```bash
cd swift
swift build      # get the core compiling
swift test       # the core is verifiable without a Mac UI or live QLab
```

Fix whatever the compiler/tests surface — the logic is ported from the tested
Python app, so the tests are the spec. **Keep `swift test` green** as you go.

## Build order (do them in this order)

1. **Core green**: `swift build && swift test`. Resolve porting nits.
2. **App target**: in Xcode, create a *multiplatform SwiftUI app* target that
   depends on the `QLabFlashCore` package, then move `App/*.swift` into it
   (add an asset catalog + the existing icon from `../assets/`). The package is
   text-only; the app target needs the `.xcodeproj` Xcode generates.
3. **Live round-trip**: Connect → list workspaces → load a workspace → confirm
   `GridModel` builds anchors correctly against real QLab over the network.
4. **The grid** (`MicGridView`): rows × 32 toggles, centered checkboxes,
   vertical headers, green/amber tints.
5. **Drag-to-select** — the #1 risk. A `DragGesture` → row/col rectangle →
   tinted block → Mute/Unmute/Toggle. Prototype on macOS, then adapt for iPad
   touch (bigger targets, touch-drag). See the TODO in `MicGridView.swift`.
6. Layer in: 30-step undo, mic/cue renaming, Mixer settings, Submit/Submit-all,
   Reload, Diagnose, OSC log, About/Help/Contact (sketched in `Dialogs.swift`).
7. Sign + notarize (Developer ID already set up for the Python app) and/or
   submit to the App Store.

## Behaviour rules (match the Python app exactly)

- **Checked = unmuted (ON, value 1). Unchecked = muted (OFF, value 0).**
- A mic cue is a QLab Network cue whose `parameterValues` is
  `["ch", <int 1..32>, "mix", "on", <0|1>]`. A `{channel}` placeholder (channel
  = null) can't map to a column — `GridModel` counts these (`placeholderCount`);
  tell the user to set a concrete channel number.
- **Preserve the value's type on write**: QLab sometimes stores the on/off value
  as a string `"0"`. `GridModel.write(for:)` writes back a string if the
  original was a string, else an int. There are tests for both.
- **Anchor detection**: a cue is the anchor (gets the 32 boxes) when its subtree
  has mic cues with no duplicate channels and it's the highest such cue. If a
  parent spans two cues that both use channel 1, each cue becomes its own anchor.
- **Transport**: TCP is required for `cueLists` (replies exceed a UDP datagram).
  QLab frames with double-END SLIP and replies on the same connection.
- **Submit** pushes: changed mic states + changed cue names (to QLab) + changed
  mic names to the X32 scribble strips (direct UDP, port 10023).

## Known scaffold gaps (fix on the Mac)

- `QLabClient` does one query at a time; the Python app **pipelines** per-cue
  property fetches (`get_cue_properties`) for speed on big shows. Add batched
  fetches once the basic round-trip works (`AppStore.loadGrid` has the naive
  loop to replace).
- `Config` is a value type held by `GridModel`; wire label edits through so the
  model sees them (or rebuild scribble baseline) — see the Python `Config`
  sharing model.
- Custom-OSC (`customString`) cues aren't parsed here (X32 uses
  `parameterValues`); port `parse_channel` from `model.py` if a user needs it.
- Everything in `App/` is a sketch — not yet compiled against Xcode's SwiftUI.

## Cross-reference

When in doubt, read the tested Python sources in the repo root: `qlabflash/`
(`osc.py`, `qlab.py`, `model.py`, `session.py`, `mixer.py`, `config.py`) and
`tests/`. They are the authoritative behaviour.
