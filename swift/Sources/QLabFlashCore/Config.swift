//  Config.swift
//  QLabFlashCore
//
//  Application configuration. Ports qlabflash/config.py. Everything that might
//  differ between QLab versions, console models, or studio conventions lives
//  here. Defaults target QLab 5 driving a Behringer X32 using channel-on as the
//  mute control: /ch/NN/mix/on with 1 = ON (unmuted), 0 = OFF (muted).

import Foundation

public struct Config: Codable, Equatable {
    // MARK: Network
    public var qlabHost: String = "127.0.0.1"
    public var qlabPort: Int = 53000          // QLab's fixed OSC receive port.
    /// TCP is required for reading cue lists on real shows: those replies are
    /// bigger than a single UDP datagram can hold. UDP is left as an option.
    public var transport: String = "tcp"
    public var passcode: String = ""          // QLab 5 workspace passcode, if any.

    // MARK: Mic grid
    public var micCount: Int = 32

    // MARK: X32 mixer (for scribble-strip channel names)
    /// The mixer's IP, so renaming a mic can also set the channel name on the
    /// console. Blank disables scribble-strip updates. The X32 listens on 10023.
    public var x32Host: String = ""
    public var x32Port: Int = 10023
    public var scribbleTemplate: String = "/ch/%02d/config/name"

    /// Friendly per-mic names shown in the column headers, keyed by channel
    /// number as a string (e.g. ["1": "Doug"]). Purely a display aid in QLab,
    /// but pushed to the X32 scribble strips on submit.
    public var channelLabels: [String: String] = [:]

    // MARK: How mic state is stored in QLab cues
    /// The QLab cue property the app reads. QLab 5 X32 "network audio" cues
    /// expose their value as a structured list under "parameterValues"
    /// (e.g. ["ch", 1, "mix", "on", 0]). Custom-OSC setups store text under
    /// "customString" instead.
    public var readProperty: String = "parameterValues"
    /// Property used to WRITE back a text OSC message (custom-OSC cues only).
    public var oscMessageProperty: String = "customString"

    public var unmutedValue: Int = 1          // value that means "unmuted".
    public var mutedValue: Int = 0            // value that means "muted".

    public var replyTimeout: Double = 5.0     // seconds to wait for a QLab reply.

    public init() {}

    // MARK: Derived helpers
    public func channelStateValue(unmuted: Bool) -> Int {
        unmuted ? unmutedValue : mutedValue
    }

    public func isUnmutedValue(_ value: Int) -> Bool {
        value == unmutedValue
    }

    // MARK: Mic names
    public func label(forChannel channel: Int) -> String {
        channelLabels[String(channel)] ?? ""
    }

    public mutating func setLabel(_ name: String, forChannel channel: Int) {
        let trimmed = name.trimmingCharacters(in: .whitespacesAndNewlines)
        if trimmed.isEmpty {
            channelLabels.removeValue(forKey: String(channel))
        } else {
            channelLabels[String(channel)] = trimmed
        }
    }

    public func hasLabels() -> Bool {
        channelLabels.values.contains { !$0.trimmingCharacters(in: .whitespaces).isEmpty }
    }

    /// Column header text: the name if set, otherwise the number.
    public func headerText(forChannel channel: Int) -> String {
        let name = label(forChannel: channel)
        return name.isEmpty ? String(channel) : name
    }

    /// The X32 scribble-strip OSC address for a channel.
    public func scribbleAddress(forChannel channel: Int) -> String {
        String(format: scribbleTemplate, channel)
    }
}
