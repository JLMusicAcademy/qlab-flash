//  QLabClient.swift
//  QLabFlashCore
//
//  An async QLab OSC client over TCP (SLIP-framed) using Network.framework.
//  Ports qlabflash/qlab.py. Most QLab queries generate a reply: a single OSC
//  message whose only argument is a JSON string of the form
//
//      {"workspace_id": "...", "address": "/the/method", "status": "ok",
//       "data": <whatever was requested>}
//
//  We send a query, then wait for the reply whose JSON `address` matches the
//  method we asked about (matched on the address *suffix*, so we don't care
//  whether QLab echoes the workspace prefix). TCP is required for `cueLists`
//  (replies exceed a UDP datagram); QLab replies on the same connection.
//
//  NOTE: this is a scaffold to compile against and iterate on with a live QLab.
//  Pipelined property fetches (`getCueProperties` in the Python app) should be
//  added once the basic round-trip is verified on a Mac.

import Foundation
import Network

public struct QLabReply {
    public let address: String
    public let status: String
    public let data: JSONValue?
}

public enum QLabError: Error {
    case timeout(String)
    case connectionFailed(String)
    case notConnected
}

public actor QLabClient {
    private let host: String
    private let port: Int
    private let replyTimeout: Double

    private var connection: NWConnection?
    private let slip = SlipDecoder()

    /// Waiters keyed by the address suffix we expect in the reply.
    private var waiters: [String: CheckedContinuation<QLabReply, Error>] = [:]

    public var onLog: (@Sendable (_ direction: String, _ address: String, _ detail: String) -> Void)?

    public init(host: String, port: Int = 53000, replyTimeout: Double = 5.0) {
        self.host = host
        self.port = port
        self.replyTimeout = replyTimeout
    }

    // MARK: Connection lifecycle

    public func connect() async throws {
        guard let nwPort = NWEndpoint.Port(rawValue: UInt16(port)) else {
            throw QLabError.connectionFailed("bad port \(port)")
        }
        let conn = NWConnection(host: NWEndpoint.Host(host), port: nwPort, using: .tcp)
        self.connection = conn

        try await withCheckedThrowingContinuation { (cont: CheckedContinuation<Void, Error>) in
            conn.stateUpdateHandler = { state in
                switch state {
                case .ready: cont.resume()
                case .failed(let err): cont.resume(throwing: QLabError.connectionFailed("\(err)"))
                default: break
                }
            }
            conn.start(queue: .global(qos: .userInitiated))
        }
        receiveLoop()
    }

    public func close() {
        connection?.cancel()
        connection = nil
    }

    // MARK: Sending

    private func rawSend(_ packet: Data) {
        connection?.send(content: SLIP.encode(packet), completion: .idempotent)
    }

    /// Fire-and-forget OSC message.
    public func send(_ address: String, _ args: [OSCArg] = []) {
        rawSend(OSC.encode(address, args))
        onLog?("send", address, "")
    }

    /// Send `address` and return the `data` field of its reply, paired by
    /// `matchSuffix` (defaults to `address`).
    public func query(_ address: String, _ args: [OSCArg] = [],
                      matchSuffix: String? = nil) async throws -> QLabReply {
        let key = matchSuffix ?? address
        return try await withCheckedThrowingContinuation { cont in
            // Time out the waiter if QLab never answers.
            waiters[key] = cont
            send(address, args)
            Task {
                try? await Task.sleep(nanoseconds: UInt64(replyTimeout * 1_000_000_000))
                if let pending = waiters.removeValue(forKey: key) {
                    pending.resume(throwing: QLabError.timeout(address))
                }
            }
        }
    }

    // MARK: High-level QLab methods

    public func workspaces() async throws -> [JSONValue] {
        try await query("/workspaces").data?.arrayValue ?? []
    }

    public func connectWorkspace(_ id: String, passcode: String = "") async throws -> String {
        let args: [OSCArg] = passcode.isEmpty ? [] : [.string(passcode)]
        let reply = try await query("/workspace/\(id)/connect", args, matchSuffix: "/connect")
        return reply.data?.stringValue ?? reply.status
    }

    public func cueLists(workspace id: String) async throws -> [JSONValue] {
        try await query("/workspace/\(id)/cueLists", matchSuffix: "/cueLists")
            .data?.arrayValue ?? []
    }

    public func cueProperty(workspace id: String, cueUID: String, property: String) async throws -> JSONValue? {
        try await query("/workspace/\(id)/cue_id/\(cueUID)/\(property)",
                        matchSuffix: "/cue_id/\(cueUID)/\(property)").data
    }

    /// Setting a property is fire-and-forget; QLab applies it immediately.
    public func setCueProperty(workspace id: String, cueUID: String,
                               property: String, value: String) {
        send("/workspace/\(id)/cue_id/\(cueUID)/\(property)", [.string(value)])
    }

    // MARK: Receive loop

    private func receiveLoop() {
        connection?.receive(minimumIncompleteLength: 1, maximumLength: 65535) {
            [weak self] data, _, isComplete, error in
            guard let self else { return }
            if let data, !data.isEmpty {
                Task { await self.ingest(data) }
            }
            if error == nil && !isComplete {
                Task { await self.receiveLoop() }
            }
        }
    }

    private func ingest(_ data: Data) {
        for packet in slip.feed(data) {
            for (address, args) in OSC.decodePacket(packet) {
                dispatch(address, args)
            }
        }
    }

    private func dispatch(_ address: String, _ args: [OSCArg]) {
        var reply: JSONValue?
        if case .string(let payload)? = args.first {
            reply = JSONValue.parse(payload)
        }
        let obj = reply?.objectValue
        let replyAddr = obj?["address"]?.stringValue ?? address
        let status = obj?["status"]?.stringish ?? "ok"
        onLog?("recv", replyAddr, status)

        // Match the waiter whose key is a suffix of this reply's address.
        if let key = waiters.keys.first(where: { replyAddr == $0 || replyAddr.hasSuffix($0) }),
           let cont = waiters.removeValue(forKey: key) {
            cont.resume(returning: QLabReply(address: replyAddr, status: status, data: obj?["data"]))
        }
    }
}
