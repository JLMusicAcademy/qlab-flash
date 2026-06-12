//  Model.swift
//  QLabFlashCore
//
//  Translation between QLab's cue tree and the mic-mute grid. Ports
//  qlabflash/model.py. This layer is pure (no networking): given the cue-list
//  JSON QLab returns plus a lookup of each cue's value, it mirrors QLab's
//  hierarchy as a tree of rows and decides — dynamically, for any workspace
//  shape — which cues own a set of mics.
//
//  How a mic cue is found (works at any nesting depth): a cue is an *anchor cue*
//  if its subtree contains mic cues with no duplicated channel numbers, and it
//  is the highest such cue. The anchor gets the 32 checkboxes.
//
//  A checked box = unmuted (channel ON); unchecked = muted (OFF).

import Foundation

/// Cue "type" strings that contain other cues rather than carrying a mic value.
let containerTypes: Set<String> = ["Group", "Cue List", "Cart", "cuelist", "group", "cart"]

/// The value a cue carries: structured X32 params, custom-OSC text, or nothing.
public enum CueValue {
    case params([JSONValue])     // parameterValues, e.g. ["ch", 1, "mix", "on", 0]
    case text(String)            // custom-OSC message text
    case none
}

/// One checkbox: mic `channel` backed by a single QLab mic cue. Reference type
/// so an anchor and the individual mic-cue row can share the same cell (edits
/// stay in sync), matching the Python dataclass aliasing.
public final class MicCell {
    public let channel: Int                  // 1-based mic number.
    public let cueUID: String?               // backing QLab cue, if one exists.
    public var originalUnmuted: Bool?        // state read from QLab.
    public var unmuted: Bool                 // current (possibly edited) state.
    /// For structured X32 cues, the original parameterValues so we can write it
    /// back with the on/off value changed. nil for custom-OSC cues.
    public var params: [JSONValue]?

    public init(channel: Int, cueUID: String?, originalUnmuted: Bool?,
                unmuted: Bool, params: [JSONValue]?) {
        self.channel = channel
        self.cueUID = cueUID
        self.originalUnmuted = originalUnmuted
        self.unmuted = unmuted
        self.params = params
    }

    public var exists: Bool { cueUID != nil }
    public var dirty: Bool { exists && unmuted != originalUnmuted }
}

/// Light wrapper around one cue object from QLab's cueLists reply.
public struct Cue {
    public let uid: String
    public let number: String
    public let name: String
    public let type: String
    public let children: [Cue]

    public var isContainer: Bool { containerTypes.contains(type) || !children.isEmpty }

    public init(uid: String, number: String, name: String, type: String, children: [Cue]) {
        self.uid = uid; self.number = number; self.name = name
        self.type = type; self.children = children
    }

    public static func from(json obj: [String: JSONValue]) -> Cue {
        let cues = obj["cues"]?.arrayValue ?? []
        return Cue(
            uid: obj["uniqueID"]?.stringish ?? "",
            number: obj["number"]?.stringish ?? "",
            name: obj["name"]?.stringish.nonEmpty ?? obj["listName"]?.stringish ?? "",
            type: obj["type"]?.stringish ?? "",
            children: cues.compactMap { $0.objectValue }.map { Cue.from(json: $0) }
        )
    }

    public func walk() -> [Cue] {
        var out = [self]
        for c in children { out += c.walk() }
        return out
    }

    /// UIDs of every non-container cue in this subtree (mic-cue candidates).
    public func leafUIDs() -> [String] {
        walk().filter { !$0.isContainer }.map { $0.uid }
    }
}

/// One row in the worksheet, mirroring a QLab cue (at any depth). Reference type
/// so parent/child links and shared cells behave like the Python model.
public final class RowNode {
    public let uid: String
    public let number: String
    public let type: String
    public var name: String
    public var originalName: String
    public weak var parent: RowNode?
    public var children: [RowNode] = []

    /// The mic cell this cue carries itself, if it is an individual mic cue.
    public var ownCell: MicCell?
    /// Channel -> MicCell shown on this row (the aggregated set on an anchor, the
    /// single own cell on a mic cue, empty otherwise).
    public var cells: [Int: MicCell] = [:]

    public var isAnchor = false
    var unique = false  // whether the subtree's mic channels are all distinct.

    init(uid: String, number: String, name: String, type: String, parent: RowNode?) {
        self.uid = uid; self.number = number; self.name = name
        self.type = type; self.originalName = name; self.parent = parent
    }

    public var displayName: String {
        if !name.isEmpty { return name }
        if !number.isEmpty { return "(cue \(number))" }
        return uid
    }

    public var nameDirty: Bool { name != originalName }

    public func walk() -> [RowNode] {
        var out = [self]
        for c in children { out += c.walk() }
        return out
    }
}

/// A write to push to QLab: set `property` on cue `uid` to `value`.
public struct CueWrite: Equatable {
    public let uid: String
    public let property: String
    public let value: String
}

public final class GridModel {
    public let config: Config
    public private(set) var roots: [RowNode] = []
    private var placeholderCountValue = 0
    private var labelBaseline: [String: String]

    public init(config: Config) {
        self.config = config
        self.labelBaseline = config.channelLabels
    }

    /// Count of On/Off cues skipped because their channel was a placeholder.
    public var placeholderCount: Int { placeholderCountValue }

    // MARK: Parsing a cue's value

    /// Recognise an X32 channel on/off cue from its parameterValues.
    /// Returns (channel, unmuted, params) or nil. A placeholder channel (null /
    /// non-numeric) is counted and skipped — it can't map to a mic column.
    public func parseParameterValues(_ pv: [JSONValue]) -> (Int, Bool, [JSONValue])? {
        guard pv.count >= 5 else { return nil }
        guard pv[0].stringish.lowercased() == "ch",
              pv[2].stringish.lowercased() == "mix",
              pv[3].stringish.lowercased() == "on" else { return nil }
        guard let chan = pv[1].intValue, chan >= 1, chan <= config.micCount else {
            placeholderCountValue += 1
            return nil
        }
        guard let value = pv[4].intValue else { return nil }
        return (chan, config.isUnmutedValue(value), pv)
    }

    func parseValue(_ value: CueValue) -> (Int, Bool, [JSONValue]?)? {
        switch value {
        case .params(let pv):
            guard let (c, u, p) = parseParameterValues(pv) else { return nil }
            return (c, u, p)
        case .text:
            return nil  // custom-OSC text parsing lives in the Python app; add if needed.
        case .none:
            return nil
        }
    }

    // MARK: Building the tree

    public func buildTree(_ topLevel: [Cue], getValue: (String) -> CueValue) -> [RowNode] {
        placeholderCountValue = 0
        labelBaseline = config.channelLabels
        let built = topLevel.map { makeNode($0, parent: nil, getValue: getValue) }
        for root in built { annotate(root, parentUnique: false) }
        roots = built
        return built
    }

    private func makeNode(_ cue: Cue, parent: RowNode?, getValue: (String) -> CueValue) -> RowNode {
        let node = RowNode(uid: cue.uid, number: cue.number, name: cue.name,
                           type: cue.type, parent: parent)
        if let (chan, unmuted, params) = parseValue(getValue(cue.uid)) {
            node.ownCell = MicCell(channel: chan, cueUID: cue.uid,
                                   originalUnmuted: unmuted, unmuted: unmuted, params: params)
        }
        node.children = cue.children.map { makeNode($0, parent: node, getValue: getValue) }
        return node
    }

    private func subtreeCells(_ node: RowNode) -> [MicCell] {
        var cells: [MicCell] = []
        if let c = node.ownCell { cells.append(c) }
        for child in node.children { cells += subtreeCells(child) }
        return cells
    }

    private func annotate(_ node: RowNode, parentUnique: Bool) {
        let cells = subtreeCells(node)
        let channels = cells.map { $0.channel }
        node.unique = !channels.isEmpty && channels.count == Set(channels).count
        // Highest cue whose channels are all distinct = the anchor cue.
        node.isAnchor = node.unique && !parentUnique

        if node.isAnchor {
            node.cells = Dictionary(cells.map { ($0.channel, $0) }, uniquingKeysWith: { a, _ in a })
        } else if let own = node.ownCell {
            node.cells = [own.channel: own]
        } else {
            node.cells = [:]
        }

        for child in node.children { annotate(child, parentUnique: node.unique) }
    }

    // MARK: Iteration
    public func allRows() -> [RowNode] { roots.flatMap { $0.walk() } }
    public func anchors() -> [RowNode] { allRows().filter { $0.isAnchor } }
    private func ownCells() -> [MicCell] { allRows().compactMap { $0.ownCell } }

    // MARK: Producing writes

    func write(for cell: MicCell) -> CueWrite {
        if var pv = cell.params {
            // Structured X32 cue: rewrite parameterValues with the new on/off
            // value, preserving its original type (QLab may store it as "0").
            let newValue = config.channelStateValue(unmuted: cell.unmuted)
            if case .string = pv[pv.count - 1] {
                pv[pv.count - 1] = .string(String(newValue))
            } else {
                pv[pv.count - 1] = .int(newValue)
            }
            return CueWrite(uid: cell.cueUID!, property: "parameterValues",
                            value: JSONValue.array(pv).jsonString)
        }
        // Custom-OSC cue would rewrite the message text; not needed for X32.
        return CueWrite(uid: cell.cueUID!, property: config.oscMessageProperty, value: "")
    }

    public func dirtyWrites() -> [CueWrite] { ownCells().filter { $0.dirty }.map { write(for: $0) } }
    public func allWrites() -> [CueWrite] { ownCells().filter { $0.exists }.map { write(for: $0) } }

    /// (uid, "name", newName) for every cue whose name was edited.
    public func nameWrites() -> [CueWrite] {
        allRows().filter { $0.nameDirty && !$0.uid.isEmpty }
            .map { CueWrite(uid: $0.uid, property: "name", value: $0.name) }
    }

    public func micDirtyCount() -> Int { ownCells().filter { $0.dirty }.count }
    public func nameDirtyCount() -> Int { allRows().filter { $0.nameDirty && !$0.uid.isEmpty }.count }

    /// Every mic cue (across all cues) for a given channel.
    public func nodes(forChannel channel: Int) -> [RowNode] {
        allRows().filter { $0.ownCell?.channel == channel }
    }

    /// Rename every cue for `channel` to `name`. Returns (node, oldName) pairs
    /// that changed, for undo.
    @discardableResult
    public func setChannelName(_ channel: Int, name: String) -> [(RowNode, String)] {
        let trimmed = name.trimmingCharacters(in: .whitespacesAndNewlines)
        var changed: [(RowNode, String)] = []
        for node in nodes(forChannel: channel) where node.name != trimmed {
            changed.append((node, node.name))
            node.name = trimmed
        }
        return changed
    }

    /// (channel, name) mic names to push to the X32 scribble strips. With
    /// `onlyDirty`, just the names changed since load; otherwise every named
    /// channel (a full mixer sync).
    public func scribbleWrites(onlyDirty: Bool = true) -> [(Int, String)] {
        var out: [(Int, String)] = []
        for chan in 1...config.micCount {
            let name = config.label(forChannel: chan)
            let base = labelBaseline[String(chan)] ?? ""
            if onlyDirty {
                if name != base { out.append((chan, name)) }
            } else if !name.isEmpty {
                out.append((chan, name))
            }
        }
        return out
    }

    public func scribbleDirtyCount() -> Int { scribbleWrites(onlyDirty: true).count }

    /// After a successful submit, current state becomes the baseline.
    public func markCommitted() {
        for cell in ownCells() where cell.exists { cell.originalUnmuted = cell.unmuted }
        for node in allRows() { node.originalName = node.name }
        labelBaseline = config.channelLabels
    }
}

private extension String {
    var nonEmpty: String? { isEmpty ? nil : self }
}
