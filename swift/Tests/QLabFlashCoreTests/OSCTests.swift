import XCTest
@testable import QLabFlashCore

final class OSCTests: XCTestCase {

    func testEncodeStringMessageRoundTrips() {
        let packet = OSC.encode("/workspace/1/connect", .string("pass"))
        let (address, args) = OSC.decodeMessage(packet)
        XCTAssertEqual(address, "/workspace/1/connect")
        XCTAssertEqual(args, [.string("pass")])
    }

    func testEncodeMixedArgsRoundTrip() {
        let packet = OSC.encode("/ch/1/mix/on", .int32(1), .float32(0.5), .string("hi"))
        let (address, args) = OSC.decodeMessage(packet)
        XCTAssertEqual(address, "/ch/1/mix/on")
        XCTAssertEqual(args, [.int32(1), .float32(0.5), .string("hi")])
    }

    func testStringPaddingIsFourByteAligned() {
        // "/a" -> 2 chars + NUL = 3, padded to 4.
        let encoded = OSC.encodeString("/a")
        XCTAssertEqual(encoded.count % 4, 0)
        XCTAssertEqual(encoded.count, 4)
    }

    func testAddressOnlyMessageDecodes() {
        let packet = OSC.encode("/workspaces")
        let (address, args) = OSC.decodeMessage(packet)
        XCTAssertEqual(address, "/workspaces")
        XCTAssertTrue(args.isEmpty)
    }

    func testSlipRoundTripSinglePacket() {
        let packet = OSC.encode("/cueLists")
        let framed = SLIP.encode(packet)
        let decoder = SlipDecoder()
        let out = decoder.feed(framed)
        XCTAssertEqual(out, [packet])
    }

    func testSlipEscapesEndAndEscBytes() {
        let raw = Data([SLIP.end, 0x01, SLIP.esc, 0x02])
        let framed = SLIP.encode(raw)
        let out = SlipDecoder().feed(framed)
        XCTAssertEqual(out, [raw])
    }

    func testSlipDecoderHandlesSplitStreamAndDoubleEnd() {
        let a = OSC.encode("/one")
        let b = OSC.encode("/two")
        let stream = SLIP.encode(a) + SLIP.encode(b)
        let decoder = SlipDecoder()
        // Feed in two arbitrary chunks to prove statefulness.
        let mid = stream.count / 2
        var out = decoder.feed(stream.prefix(mid))
        out += decoder.feed(stream.suffix(from: stream.startIndex + mid))
        XCTAssertEqual(out, [a, b])
    }

    func testDecodeJSONReplyPayload() {
        // QLab replies are a single string arg containing JSON.
        let json = #"{"address":"/cueLists","status":"ok","data":[]}"#
        let packet = OSC.encode("/reply", .string(json))
        let (_, args) = OSC.decodeMessage(packet)
        guard case .string(let payload)? = args.first else {
            return XCTFail("expected string arg")
        }
        let parsed = JSONValue.parse(payload)
        XCTAssertEqual(parsed?.objectValue?["status"]?.stringValue, "ok")
    }
}
