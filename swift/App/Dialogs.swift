//  Dialogs.swift
//  QLab Flash
//
//  SKETCH — About / Help / Contact, mirroring the Python app's About menu.
//  Contact composes an email to doug@fishersmusic.com. Help summarises usage.

import SwiftUI
#if canImport(AppKit)
import AppKit
#endif

private let contactEmail = "doug@fishersmusic.com"
private let developer = "Ji-Eun Lee Music Academy, LLC"

struct AboutView: View {
    @Environment(\.dismiss) private var dismiss
    var body: some View {
        VStack(spacing: 12) {
            Image(systemName: "bolt.fill").font(.system(size: 48))
            Text("QLab Flash").font(.title.bold())
            Text("Bulk mic mute/unmute editor for QLab 5 + Behringer X32")
                .font(.subheadline).foregroundStyle(.secondary)
                .multilineTextAlignment(.center)
            Text("Version 1.0.0").font(.caption)
            Text("© 2026 \(developer). All rights reserved.")
                .font(.caption2).foregroundStyle(.secondary)
            Button("Close") { dismiss() }
        }
        .padding(24)
        .frame(width: 380)
    }
}

struct ContactView: View {
    @Environment(\.dismiss) private var dismiss
    @State private var name = ""
    @State private var email = ""
    @State private var subject = "QLab Flash — Support"
    @State private var message = ""

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text("Contact").font(.headline)
            Text("This opens your email app with a message addressed to \(contactEmail).")
                .font(.caption).foregroundStyle(.secondary)
            TextField("Your name", text: $name)
            TextField("Your email (so we can reply)", text: $email)
            TextField("Subject", text: $subject)
            TextEditor(text: $message).frame(minHeight: 140).border(.gray.opacity(0.3))
            HStack {
                Spacer()
                Button("Cancel") { dismiss() }
                Button("Compose Email") { compose(); dismiss() }
            }
        }
        .padding(16)
        .frame(width: 460)
    }

    private func compose() {
        var body = ""
        let who = [name, email.isEmpty ? "" : "<\(email)>"]
            .filter { !$0.isEmpty }.joined(separator: " ")
        if !who.isEmpty { body += "From: \(who)\n\n" }
        body += message
        var comps = URLComponents()
        comps.scheme = "mailto"
        comps.path = contactEmail
        comps.queryItems = [
            URLQueryItem(name: "subject", value: subject),
            URLQueryItem(name: "body", value: body),
        ]
        if let url = comps.url {
            #if canImport(AppKit)
            NSWorkspace.shared.open(url)
            #endif
        }
    }
}

struct HelpView: View {
    @Environment(\.dismiss) private var dismiss
    var body: some View {
        VStack(alignment: .leading) {
            Text("QLab Flash — Help").font(.title2.bold())
            ScrollView {
                Text(helpText).font(.callout)
                    .frame(maxWidth: .infinity, alignment: .leading)
            }
            Button("Close") { dismiss() }
                .frame(maxWidth: .infinity, alignment: .trailing)
        }
        .padding(16)
        .frame(width: 620, height: 520)
    }

    private let helpText = """
    A checked box = mic UNMUTED (channel ON). Unchecked = MUTED (OFF).

    1. Connecting — In QLab: Workspace Settings → Network → OSC Access. Enable \
    view/control, enter a passcode if used. Pick your workspace and Connect.

    2. The grid — Rows are your cues (the full QLab hierarchy, expandable). \
    Columns 1–32 are mics. Green = currently unmuted; amber = an unsubmitted edit.

    3. Editing — Click a checkbox to toggle one mic. Drag a rectangle to select a \
    block, then Mute/Unmute/Toggle the selection.

    4. Undo — ⌘Z reverses the last 30 actions.

    5. Naming mics — Rename a column to label it, rename that mic's cue \
    everywhere in QLab, and set the X32 scribble strip (if the mixer IP is set).

    6. Submitting — "Submit changes" sends only what you changed. "Submit ALL \
    mics" rewrites every mic. Reload re-reads from QLab.
    """
}
