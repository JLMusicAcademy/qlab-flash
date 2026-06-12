import XCTest
@testable import QLabFlashCore

final class ModelTests: XCTestCase {

    // Build a mic channel cue's parameterValues: ["ch", chan, "mix", "on", value].
    private func params(_ chan: JSONValue, _ value: JSONValue) -> CueValue {
        .params([.string("ch"), chan, .string("mix"), .string("on"), value])
    }

    private func micCue(_ uid: String, _ chan: Int) -> Cue {
        Cue(uid: uid, number: "", name: "Ch \(chan)", type: "Network", children: [])
    }

    private func group(_ uid: String, _ name: String, _ children: [Cue]) -> Cue {
        Cue(uid: uid, number: "", name: name, type: "Group", children: children)
    }

    // MARK: parameterValues parsing

    func testParseParameterValuesUnmuted() {
        let model = GridModel(config: Config())
        let result = model.parseParameterValues([
            .string("ch"), .int(3), .string("mix"), .string("on"), .int(1)])
        XCTAssertEqual(result?.0, 3)
        XCTAssertEqual(result?.1, true)   // 1 = unmuted
    }

    func testParseParameterValuesMutedAsString() {
        // QLab sometimes stores the value as a string "0".
        let model = GridModel(config: Config())
        let result = model.parseParameterValues([
            .string("ch"), .int(5), .string("mix"), .string("on"), .string("0")])
        XCTAssertEqual(result?.0, 5)
        XCTAssertEqual(result?.1, false)  // 0 = muted
    }

    func testPlaceholderChannelIsCountedAndSkipped() {
        let model = GridModel(config: Config())
        let result = model.parseParameterValues([
            .string("ch"), .null, .string("mix"), .string("on"), .int(0)])
        XCTAssertNil(result)
        XCTAssertEqual(model.placeholderCount, 1)
    }

    func testNonMicCueIsNotParsed() {
        let model = GridModel(config: Config())
        XCTAssertNil(model.parseParameterValues([
            .string("ch"), .int(1), .string("eq"), .string("on"), .int(1)]))
    }

    // MARK: anchor detection

    func testAnchorIsGroupContainingDistinctMics() {
        // Cue -> Mics group -> 3 distinct channel cues. The top Cue is the anchor.
        let cue = group("cue", "Opening", [
            group("mics", "Mics", [micCue("m1", 1), micCue("m2", 2), micCue("m3", 3)])
        ])
        let values: [String: CueValue] = [
            "m1": params(.int(1), .int(1)),
            "m2": params(.int(2), .int(0)),
            "m3": params(.int(3), .int(1)),
        ]
        let model = GridModel(config: Config())
        let roots = model.buildTree([cue]) { values[$0] ?? .none }

        let anchors = model.anchors()
        XCTAssertEqual(anchors.count, 1)
        XCTAssertEqual(anchors.first?.uid, "cue")
        XCTAssertEqual(anchors.first?.cells.count, 3)
        XCTAssertEqual(anchors.first?.cells[1]?.unmuted, true)
        XCTAssertEqual(anchors.first?.cells[2]?.unmuted, false)
        XCTAssertEqual(roots.count, 1)
    }

    func testDuplicateChannelsSplitAnchorsToEachCue() {
        // Act -> Cue1(mic1), Cue2(mic1): channel 1 duplicated, so each cue is an
        // anchor, not the Act.
        let act = group("act", "Act I", [
            group("c1", "Cue 1", [micCue("a", 1)]),
            group("c2", "Cue 2", [micCue("b", 1)]),
        ])
        let values: [String: CueValue] = [
            "a": params(.int(1), .int(1)),
            "b": params(.int(1), .int(0)),
        ]
        let model = GridModel(config: Config())
        _ = model.buildTree([act]) { values[$0] ?? .none }

        let anchorUIDs = Set(model.anchors().map { $0.uid })
        XCTAssertEqual(anchorUIDs, ["c1", "c2"])
    }

    // MARK: editing + writes

    func testEditingCellProducesDirtyWrite() {
        let cue = group("cue", "Opening", [micCue("m1", 1)])
        let values: [String: CueValue] = ["m1": params(.int(1), .int(0))]
        let model = GridModel(config: Config())
        _ = model.buildTree([cue]) { values[$0] ?? .none }

        let cell = model.anchors().first!.cells[1]!
        XCTAssertFalse(cell.dirty)
        cell.unmuted = true
        XCTAssertTrue(cell.dirty)

        let writes = model.dirtyWrites()
        XCTAssertEqual(writes.count, 1)
        XCTAssertEqual(writes.first?.uid, "m1")
        XCTAssertEqual(writes.first?.property, "parameterValues")
        // Value type preserved: original was a string "0", so write back a string.
        XCTAssertTrue(writes.first!.value.contains("\"1\""))
    }

    func testWritePreservesIntValueType() {
        let cue = group("cue", "Opening", [micCue("m1", 2)])
        let values: [String: CueValue] = ["m1": params(.int(2), .int(0))]
        let model = GridModel(config: Config())
        _ = model.buildTree([cue]) { values[$0] ?? .none }
        let cell = model.anchors().first!.cells[2]!
        cell.unmuted = true
        // Original value was an int 0, so the write should serialise an int 1.
        XCTAssertTrue(model.dirtyWrites().first!.value.contains("1"))
        XCTAssertFalse(model.dirtyWrites().first!.value.contains("\"1\""))
    }

    func testChannelRenameMarksCuesNameDirty() {
        let cue = group("cue", "Opening", [micCue("m1", 1), micCue("m2", 1)])
        let values: [String: CueValue] = [
            "m1": params(.int(1), .int(1)),
            "m2": params(.int(1), .int(1)),
        ]
        let model = GridModel(config: Config())
        _ = model.buildTree([cue]) { values[$0] ?? .none }

        let changed = model.setChannelName(1, name: "Doug")
        XCTAssertEqual(changed.count, 2)
        XCTAssertEqual(model.nameDirtyCount(), 2)
        XCTAssertTrue(model.nameWrites().allSatisfy { $0.value == "Doug" })
    }

    func testMarkCommittedResetsDirty() {
        let cue = group("cue", "Opening", [micCue("m1", 1)])
        let values: [String: CueValue] = ["m1": params(.int(1), .int(0))]
        let model = GridModel(config: Config())
        _ = model.buildTree([cue]) { values[$0] ?? .none }
        model.anchors().first!.cells[1]!.unmuted = true
        XCTAssertEqual(model.micDirtyCount(), 1)
        model.markCommitted()
        XCTAssertEqual(model.micDirtyCount(), 0)
    }

    // MARK: scribble strip

    func testScribbleWritesOnlyDirtyNames() {
        var config = Config()
        config.setLabel("Doug", forChannel: 1)
        let model = GridModel(config: config)
        _ = model.buildTree([]) { _ in .none }
        // Baseline already has Doug, so nothing dirty yet.
        XCTAssertEqual(model.scribbleDirtyCount(), 0)
    }
}
