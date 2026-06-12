//  OSC.swift
//  QLabFlashCore
//
//  Minimal, dependency-free OSC 1.0 encoder/decoder + SLIP framing.
//  Ports qlabflash/osc.py. QLab speaks OSC; over TCP it frames packets with
//  double-END SLIP (RFC 1055). Replies arrive as a single OSC message whose
//  only argument is a JSON string, so robust string decoding is what matters.

import Foundation

/// An OSC argument. We only need the handful of types QLab uses.
public enum OSCArg: Equatable {
    case int32(Int32)
    case float32(Float)
    case string(String)
    case blob(Data)
    case bool(Bool)
    case null
}

public enum OSC {

    static let bundlePrefix = Data("#bundle\0".utf8)

    // MARK: Encoding

    /// Pad `data` with NUL bytes to the next 4-byte boundary.
    static func pad(_ data: Data) -> Data {
        let remainder = data.count % 4
        if remainder == 0 { return data }
        return data + Data(repeating: 0, count: 4 - remainder)
    }

    /// Encode an OSC string: UTF-8 bytes, NUL terminated, 4-byte aligned.
    static func encodeString(_ value: String) -> Data {
        pad(Data(value.utf8) + Data([0]))
    }

    static func bigEndianInt32(_ value: Int32) -> Data {
        var be = value.bigEndian
        return withUnsafeBytes(of: &be) { Data($0) }
    }

    static func bigEndianFloat32(_ value: Float) -> Data {
        var be = value.bitPattern.bigEndian
        return withUnsafeBytes(of: &be) { Data($0) }
    }

    /// Encode an OSC message with the given address and arguments.
    public static func encode(_ address: String, _ args: [OSCArg]) -> Data {
        var out = encodeString(address)
        var typeTags = ","
        var payload = Data()
        for arg in args {
            switch arg {
            case .bool(let b):           // OSC has no bool in QLab's usage; send int32
                typeTags += "i"
                payload += bigEndianInt32(b ? 1 : 0)
            case .int32(let i):
                typeTags += "i"
                payload += bigEndianInt32(i)
            case .float32(let f):
                typeTags += "f"
                payload += bigEndianFloat32(f)
            case .string(let s):
                typeTags += "s"
                payload += encodeString(s)
            case .blob(let data):
                typeTags += "b"
                payload += bigEndianInt32(Int32(data.count)) + pad(data)
            case .null:
                typeTags += "N"
            }
        }
        out += encodeString(typeTags)
        out += payload
        return out
    }

    /// Convenience for a string-argument message (the common QLab write).
    public static func encode(_ address: String, _ args: OSCArg...) -> Data {
        encode(address, args)
    }

    // MARK: Decoding

    static func readString(_ data: Data, _ offset: inout Int) -> String {
        let base = data.startIndex
        var end = offset
        while end < data.count, data[base + end] != 0 { end += 1 }
        let value = String(decoding: data[(base + offset)..<(base + end)], as: UTF8.self)
        let length = end - offset + 1
        let padded = length + ((4 - length % 4) % 4)
        offset += padded
        return value
    }

    static func readInt32(_ data: Data, _ offset: inout Int) -> Int32 {
        let base = data.startIndex
        var value: Int32 = 0
        for i in 0..<4 { value = (value << 8) | Int32(data[base + offset + i]) }
        offset += 4
        return value
    }

    static func readFloat32(_ data: Data, _ offset: inout Int) -> Float {
        let base = data.startIndex
        var bits: UInt32 = 0
        for i in 0..<4 { bits = (bits << 8) | UInt32(data[base + offset + i]) }
        offset += 4
        return Float(bitPattern: bits)
    }

    static func readBlob(_ data: Data, _ offset: inout Int) -> Data {
        let base = data.startIndex
        let size = Int(readInt32(data, &offset))
        let blob = Data(data[(base + offset)..<(base + offset + size)])
        let padded = size + ((4 - size % 4) % 4)
        offset += padded
        return blob
    }

    /// Decode a single OSC *message* (not a bundle): returns (address, args).
    public static func decodeMessage(_ data: Data, offset: Int = 0) -> (String, [OSCArg]) {
        var off = offset
        let address = readString(data, &off)
        if off >= data.count { return (address, []) }
        let typeTags = readString(data, &off)
        guard typeTags.hasPrefix(",") else { return (address, []) }

        var args: [OSCArg] = []
        for tag in typeTags.dropFirst() {
            switch tag {
            case "i": args.append(.int32(readInt32(data, &off)))
            case "f": args.append(.float32(readFloat32(data, &off)))
            case "s": args.append(.string(readString(data, &off)))
            case "b": args.append(.blob(readBlob(data, &off)))
            case "T": args.append(.bool(true))
            case "F": args.append(.bool(false))
            case "N": args.append(.null)
            default:
                // Unknown tag: we can't know its width, so stop parsing safely.
                return (address, args)
            }
        }
        return (address, args)
    }

    /// Decode an OSC packet, which may be a single message or a bundle.
    public static func decodePacket(_ data: Data) -> [(String, [OSCArg])] {
        if data.starts(with: bundlePrefix) { return decodeBundle(data) }
        return [decodeMessage(data)]
    }

    static func decodeBundle(_ data: Data) -> [(String, [OSCArg])] {
        var messages: [(String, [OSCArg])] = []
        let base = data.startIndex
        var offset = 16  // 8 bytes "#bundle\0" + 8 bytes timetag
        while offset < data.count {
            let size = Int(readInt32(data, &offset))
            let element = Data(data[(base + offset)..<(base + offset + size)])
            offset += size
            if element.starts(with: bundlePrefix) {
                messages += decodeBundle(element)
            } else {
                messages.append(decodeMessage(element))
            }
        }
        return messages
    }
}

// MARK: - SLIP framing (RFC 1055)

/// OSC over a TCP stream needs framing so the receiver knows where each packet
/// ends. QLab uses double-END SLIP: each packet is wrapped in END bytes, and any
/// END/ESC bytes inside the packet are escaped.
public enum SLIP {
    static let end: UInt8 = 0xC0
    static let esc: UInt8 = 0xDB
    static let escEnd: UInt8 = 0xDC
    static let escEsc: UInt8 = 0xDD

    public static func encode(_ packet: Data) -> Data {
        var out = Data([end])
        for b in packet {
            switch b {
            case end: out += Data([esc, escEnd])
            case esc: out += Data([esc, escEsc])
            default:  out.append(b)
            }
        }
        out.append(end)
        return out
    }
}

/// Feed raw stream bytes in, get whole de-framed packets out.
public final class SlipDecoder {
    private var buf = Data()
    private var inEsc = false

    public init() {}

    public func feed(_ data: Data) -> [Data] {
        var packets: [Data] = []
        for b in data {
            if inEsc {
                buf.append(b == SLIP.escEnd ? SLIP.end : (b == SLIP.escEsc ? SLIP.esc : b))
                inEsc = false
            } else if b == SLIP.end {
                if !buf.isEmpty {           // ignore empty frames (double-END)
                    packets.append(buf)
                    buf = Data()
                }
            } else if b == SLIP.esc {
                inEsc = true
            } else {
                buf.append(b)
            }
        }
        return packets
    }
}
