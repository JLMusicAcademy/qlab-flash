//  X32.swift
//  QLabFlashCore
//
//  Send OSC directly to a Behringer X32 mixer (scribble-strip channel names).
//  Ports qlabflash/mixer.py. QLab Flash normally talks to QLab, but the X32's
//  channel *name* (scribble strip) is a live mixer setting, so we send
//  /ch/NN/config/name "Annie" straight to the console over UDP (port 10023).

import Foundation
import Network

public enum X32 {
    /// Set channel names on the X32. `names` is (channel, name) pairs. Returns
    /// how many were sent. Does nothing (returns 0) if no host is configured.
    /// Network errors are swallowed so an off/unreachable mixer never blocks a
    /// submit. Fire-and-forget UDP — we don't await replies.
    @discardableResult
    public static func sendScribbleNames(
        host: String, port: Int, template: String,
        names: [(Int, String)]
    ) -> Int {
        let host = host.trimmingCharacters(in: .whitespaces)
        guard !host.isEmpty, !names.isEmpty else { return 0 }
        guard let nwPort = NWEndpoint.Port(rawValue: UInt16(port)) else { return 0 }

        let conn = NWConnection(
            host: NWEndpoint.Host(host), port: nwPort, using: .udp)
        conn.start(queue: .global(qos: .userInitiated))

        var sent = 0
        for (chan, name) in names {
            let address = String(format: template, chan)
            let packet = OSC.encode(address, .string(name))
            conn.send(content: packet, completion: .idempotent)
            sent += 1
        }
        // Give the datagrams a moment to flush, then tear down.
        DispatchQueue.global().asyncAfter(deadline: .now() + 0.5) { conn.cancel() }
        return sent
    }
}
