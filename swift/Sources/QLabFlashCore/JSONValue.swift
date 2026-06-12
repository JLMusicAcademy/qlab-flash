//  JSONValue.swift
//  QLabFlashCore
//
//  A small dynamic-JSON value, so we can parse QLab replies (whose `data` field
//  is arbitrary JSON) and round-trip parameterValues like ["ch", 1, "mix",
//  "on", 0] while preserving each element's type — QLab sometimes stores the
//  on/off value as a string "0", and we must write it back the same way.

import Foundation

public enum JSONValue: Equatable {
    case string(String)
    case int(Int)
    case double(Double)
    case bool(Bool)
    case array([JSONValue])
    case object([String: JSONValue])
    case null

    // MARK: Convenience accessors

    public var stringValue: String? {
        if case .string(let s) = self { return s }
        return nil
    }

    /// String coercion used when reading QLab fields that may arrive as numbers.
    public var stringish: String {
        switch self {
        case .string(let s): return s
        case .int(let i): return String(i)
        case .double(let d): return String(d)
        case .bool(let b): return b ? "1" : "0"
        case .null: return ""
        default: return ""
        }
    }

    public var intValue: Int? {
        switch self {
        case .int(let i): return i
        case .double(let d): return Int(d)
        case .string(let s): return Int(s)
        case .bool(let b): return b ? 1 : 0
        default: return nil
        }
    }

    public var arrayValue: [JSONValue]? {
        if case .array(let a) = self { return a }
        return nil
    }

    public var objectValue: [String: JSONValue]? {
        if case .object(let o) = self { return o }
        return nil
    }

    // MARK: Parsing / serialising

    public init(_ any: Any) {
        switch any {
        case let s as String: self = .string(s)
        case let b as Bool: self = .bool(b)
        case let i as Int: self = .int(i)
        case let n as NSNumber:
            // Distinguish bool from number via the objCType.
            if CFGetTypeID(n) == CFBooleanGetTypeID() {
                self = .bool(n.boolValue)
            } else if n.stringValue.contains(".") {
                self = .double(n.doubleValue)
            } else {
                self = .int(n.intValue)
            }
        case let d as Double: self = .double(d)
        case let a as [Any]: self = .array(a.map(JSONValue.init))
        case let o as [String: Any]:
            self = .object(o.mapValues(JSONValue.init))
        case is NSNull: self = .null
        default: self = .null
        }
    }

    public static func parse(_ data: Data) -> JSONValue? {
        guard let obj = try? JSONSerialization.jsonObject(
            with: data, options: [.fragmentsAllowed]) else { return nil }
        return JSONValue(obj)
    }

    public static func parse(_ string: String) -> JSONValue? {
        parse(Data(string.utf8))
    }

    public var foundationValue: Any {
        switch self {
        case .string(let s): return s
        case .int(let i): return i
        case .double(let d): return d
        case .bool(let b): return b
        case .array(let a): return a.map { $0.foundationValue }
        case .object(let o): return o.mapValues { $0.foundationValue }
        case .null: return NSNull()
        }
    }

    public var jsonString: String {
        let value = foundationValue
        guard let data = try? JSONSerialization.data(
            withJSONObject: value, options: [.fragmentsAllowed]) else { return "null" }
        return String(decoding: data, as: UTF8.self)
    }
}
