# QLab Flash

A Mac GUI app for **bulk-editing mic mute/unmute states across every cue** in a
QLab 5 workspace that drives a Behringer X32.

Instead of clicking mute checkboxes cue-by-cue, channel-by-channel, QLab Flash
shows your whole show as a spreadsheet: **cues down the side, mics 1–32 across
the top, a checkbox at every intersection.** Set them all, then hit **Submit** to
push every change to QLab at once over OSC.

> ☑ checked = mic **unmuted** (channel ON) ☐ unchecked = mic **muted** (channel OFF)

![QLab Flash](screenshot.png)

---

## Download (easiest — no setup)

**Apple Silicon Macs (M1/M2/M3/M4):** download the ready-made app — nothing else
to install:

**➡ https://github.com/JLMusicAcademy/qlab-flash/releases/download/macos-app/QLab-Flash.dmg**

1. Open the downloaded **QLab-Flash.dmg**.
2. In the window that appears, drag **QLab Flash** onto the **Applications** folder.
3. First launch only: **right-click** the app in Applications → **Open** → **Open**
   (it isn't Apple-signed, so this one-time step tells macOS to trust it).

That's the whole install — no Python, Homebrew, Terminal, or git required. A new
`.dmg` is rebuilt automatically whenever the app changes.

---

## Quick start

```bash
# 1. Try the interface immediately with a built-in simulated QLab — no QLab needed:
./run.sh --demo

# 2. When you're ready, connect to your real QLab:
./run.sh
```

The first launch creates a virtual environment and installs the GUI toolkit
(PySide6); after that it starts instantly. Requires **macOS** with Python 3
(the system `python3` on a modern Mac is fine, or install from python.org).

---

## How to use it

1. **Connect.** On launch you'll see open QLab workspaces. Pick one, enter the
   passcode if the workspace has one, and click **Connect**. (Tick *Demo mode*
   to explore against a fake show first.)
2. **Read.** QLab Flash reads the chosen cue list and builds the grid, showing
   the current mute state of every mic in every cue.
3. **Edit.** Click checkboxes, or select a block and set them in bulk (below).
4. **Submit.** Click **Submit changed cues to QLab**. Only the cues you actually
   changed are sent. *Submit ALL* rewrites every mic in every cue.

### Bulk selection (the time-saver)

- **Click-drag a rectangle** across the grid to select a block of cells —
  multiple cues × multiple mics at once.
- Shift-click / ⌘-click extend the selection like any spreadsheet.
- Then set them all in one move:
  - **Unmute selected** / **Mute selected** / **Toggle selected** buttons, or
  - right-click the selection for the same menu, or
  - the keyboard:

    | Key | Action |
    |-----|--------|
    | `Space` or `X` | Toggle selected mics |
    | `Enter` or `1` | Unmute selected (check) |
    | `0` or `Delete` | Mute selected (uncheck) |

- **Select all** selects the entire grid (e.g. mute everything, then open just
  the mics you need).

### Naming mics (Doug, Steve, Mary…)

Numbers are hard to read at a glance, so you can give each mic a name:

- Click **Mic names…** to edit all 32 at once, or
- **double-click a mic's column header** to rename just that one.

Named mics show the name vertically under the number in the header (like a
console channel strip), and the names persist between sessions.

**Renaming a mic does three things on Submit:**

1. Labels that column in QLab Flash.
2. Renames that channel's **cue in every cue** in QLab (e.g. every `Mic 1` cue
   becomes "Annie") — handy since shows usually define all 32 mics in each cue.
3. Sets the **channel name on the X32** (the scribble strip), via
   `/ch/NN/config/name`, if you've entered the mixer's IP under **Mixer…**.

So your cast list flows from one place to the worksheet, the QLab cue names, and
the console. (Set the X32 IP once in **Mixer…**; leave it blank to skip the
scribble-strip part.)

### Undo

**⌘Z** (or the **Undo** button) reverses the last **30** actions — checkbox
changes (single, bulk, or keyboard) and any name edits.

### Renaming cues in QLab (right in the worksheet)

The left column is QLab's full cue hierarchy, expandable like in QLab itself.
**Double-click any cue or group name and type a new one** — cue names, group
names, even individual mic cues. Changed names are tinted amber and pushed to
QLab when you hit **Submit** (alongside any mic changes). Unlike mic names
(which are local to this app), **this changes the actual cue names in your QLab
workspace.** It's usually faster than clicking through cues one-at-a-time in
QLab: double-click, type, Enter, down-arrow, repeat.

Use **Expand all** / **Collapse to cues** to switch between the full hierarchy
and the compact one-row-per-cue view. Edited mic cells are tinted amber; live
(unmuted) mics are tinted green. The footer shows the unsaved-change count.

---

## Make it a real app (custom icon + Dock)

To get a double-clickable app with its own icon instead of launching from
Terminal, run this once (on your Mac, inside the repo):

```bash
./scripts/make_app.command
```

That builds **QLab Flash.app** (custom icon and all). Then:

- **Double-click** it to launch.
- **Drag it onto your Dock** to keep it one click away.
- Or drag it into your **Applications** folder.

It's a thin launcher that runs this repo's code, so keep the repo folder where
it is. After a `git pull` you can re-run the script to rebuild.

### Using your own icon

To use your own logo instead of the built-in one, point this helper at your
image file, then rebuild:

```bash
./scripts/set_icon.command /path/to/your-logo.png   # drag the file onto Terminal to fill the path
./scripts/make_app.command
```

That replaces `assets/icon.png` (squared to 1024×1024). To keep it permanently
in the project, commit it: `git add assets/icon.png && git commit -m "Custom icon" && git push`.

(Prefer the generated art? Edit `scripts/make_icon.py`, run
`python scripts/make_icon.py`, then rebuild.)

---

## Setting up QLab

QLab Flash talks to QLab over OSC on the standard port **53000**, using a **TCP**
connection (required for reading whole cue lists — those replies are far bigger
than a single UDP packet can carry). In QLab:

1. Open **Workspace Settings → Network**.
2. Under **OSC Access**, allow access (and note the passcode if you set one).
   Make sure the access level permits editing cues, not just triggering them.

That's it — QLab Flash discovers the workspace automatically.

---

## How it maps to your cues (works with any grouping)

The worksheet mirrors QLab's hierarchy exactly: every cue and group is a row in
the tree on the left. The only thing QLab Flash has to figure out is **which row
owns a set of 32 mics** — and it does that dynamically, so you don't have to
arrange your show any particular way.

- **A mic is a Network (OSC) cue** whose message turns an X32 channel on/off,
  e.g. `/ch/03/mix/on 1` — wherever it lives in the tree.
- **A cue carries the 32 checkboxes** when its subtree
  holds mic cues with no duplicate channel numbers. The *highest* such cue wins.
  If a container holds two cues that each have a "Ch 1", it can't carry one set,
  so QLab Flash descends until each cue has a clean set of channels.

That single rule handles every layout, at any depth:

```
Cue 12 → mics                         ✓ Cue 12 gets the checkboxes
Cue 12 → Mics group → mics            ✓ Cue 12 gets the checkboxes
Cue 12 → Group A → Mics → mics        ✓ Cue 12 gets the checkboxes (any depth)
Act 1 → Cue 1, Cue 2 → … → mics       ✓ Cue 1 and Cue 2 each get checkboxes
```

Mic-cue rows show the aggregated 32 checkboxes (this is what you bulk-edit).
Expand one and you'll see its child cues underneath, mirroring QLab. Cues that
aren't mic cues — audio, lights, video, memos, structural groups — are simply
**blank** under the mic columns.

**It updates existing per-channel cues; it does not create new ones.** If a cue
has no sub-cue for, say, mic 7, that column is blank for it and skipped on
submit. (So your show needs one channel-on cue per mic per cue — the normal way
this is built.)

If your wiring is different, **everything fragile is configurable** — see below
— so you can match QLab Flash to your show without touching code.

---

## Configuration

Defaults target QLab 5 + X32 with channel-on as the mute control. To override,
copy `config.example.json` to `~/.qlab-flash.json` (or pass `--config PATH`).
QLab Flash also saves your last host/port/passcode there automatically.

| Key | Default | Meaning |
|-----|---------|---------|
| `qlab_host` | `127.0.0.1` | QLab's IP (use the Mac's own IP if QLab is elsewhere). |
| `qlab_port` | `53000` | QLab's OSC receive port (don't change unless you must). |
| `transport` | `tcp` | `tcp` or `udp`. TCP is required for reading cue lists on real shows (the replies are too big for UDP); leave it on `tcp`. |
| `mic_count` | `32` | Number of mic columns. |
| `channel_labels` | `{}` | Friendly mic names by channel, e.g. `{"1": "Doug", "2": "Steve"}`. Edit these in-app via **Mic names…**. |
| `osc_message_property` | `customString` | The QLab cue property holding a network cue's OSC text. If your QLab build reports it under another name, set it here. |
| `channel_pattern` | see file | Regex with named groups `chan` and `state` used to recognise a mic cue and read its channel + on/off value. |
| `write_template` | `/ch/{chan:02d}/mix/on {state}` | How a mic cue's message is written back. |
| `unmuted_value` / `muted_value` | `1` / `0` | OSC arg values meaning unmuted / muted. |

**Examples of adapting it:**

- Console uses a dedicated mute that's *inverted* (1 = muted): swap
  `unmuted_value` to `0`, `muted_value` to `1`, and point the pattern/template
  at your mute address.
- Your network cues address the X32 differently: edit `channel_pattern` and
  `write_template` to match.

The **Show OSC log** button (bottom bar) reveals exactly what QLab Flash sends
and receives — invaluable for confirming the addresses match your show.

---

## A note on verification

This was built and tested end-to-end against a **simulated QLab** (`--demo`
mode, also driven by the automated tests) because the developer didn't have a
live QLab+X32 rig to point it at. The OSC engine, cue parsing, grid editing, and
submit round-trip are all covered by tests. The one thing to sanity-check on
**your** real rig is that the cue-property name and OSC address patterns above
match your workspace — load a show, open the OSC log, and watch one Submit. If
the addresses look right, you're good. If not, tweak the config keys above.

Start by reading first and submitting a single changed mic on a throwaway cue to
confirm the round-trip before doing a whole show.

---

## Project layout

```
qlabflash/
  osc.py          # dependency-free OSC 1.0 codec + SLIP framing for TCP
  qlab.py         # QLab OSC client over TCP/UDP (discover, connect, read/write)
  model.py        # cue tree <-> worksheet, dynamic anchor-cue detection
  session.py      # connect -> load worksheet -> submit (mics + names)
  config.py       # all tunable settings
  mock_qlab.py    # simulated QLab for demo mode and tests
  gui/            # PySide6 interface: tree worksheet, header, dialogs
main.py           # entry point
assets/icon.png   # app icon (source art)
scripts/          # make_icon.py, set_icon.command (your art), make_app.command
tests/            # OSC/SLIP, model, anchor detection, and round-trip tests
```

## Running the tests

```bash
pip install pytest
python3 -m pytest
```

The suite includes a real-socket round-trip: it spins up the mock QLab, connects,
reads the grid, flips a mic, submits, and re-reads to confirm the change landed.
