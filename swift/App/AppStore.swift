//  AppStore.swift
//  QLab Flash
//
//  SKETCH — the observable app state. Bridges the (actor-isolated, async)
//  QLabFlashCore networking + model into SwiftUI's main-actor world. Fill in the
//  load/submit flows against a live QLab; the core methods are already typed.

import Foundation
import SwiftUI
import QLabFlashCore

@MainActor
final class AppStore: ObservableObject {
    // Connection
    @Published var config = Config()
    @Published var workspaces: [WorkspaceInfo] = []
    @Published var selectedWorkspaceID: String?
    @Published var isConnected = false
    @Published var statusLine = "Not connected"

    // Grid
    @Published var rows: [RowNode] = []          // flattened, see GridView
    @Published var demoMode = false

    // Dialogs
    @Published var showHelp = false
    @Published var showContact = false
    @Published var showAbout = false

    private var client: QLabClient?
    private(set) var model: GridModel?

    struct WorkspaceInfo: Identifiable, Hashable {
        let id: String
        let name: String
    }

    // MARK: Connect → list workspaces

    func connect() async {
        do {
            let client = QLabClient(host: config.qlabHost, port: config.qlabPort,
                                    replyTimeout: config.replyTimeout)
            try await client.connect()
            self.client = client
            let raw = try await client.workspaces()
            self.workspaces = raw.compactMap { ws in
                guard let o = ws.objectValue else { return nil }
                return WorkspaceInfo(id: o["uniqueID"]?.stringish ?? "",
                                     name: o["displayName"]?.stringish
                                        ?? o["name"]?.stringish ?? "Workspace")
            }
            isConnected = true
            statusLine = "Connected — pick a workspace"
        } catch {
            statusLine = "Connection failed: \(error)"
        }
    }

    // MARK: Load a workspace's cues into the grid

    func loadGrid() async {
        guard let client, let id = selectedWorkspaceID else { return }
        do {
            _ = try await client.connectWorkspace(id, passcode: config.passcode)
            let lists = try await client.cueLists(workspace: id)
            let topCues = lists.compactMap { $0.objectValue }.map { Cue.from(json: $0) }

            // Fetch each leaf cue's value (parameterValues). A pipelined batch
            // fetch should replace this per-cue loop for real shows.
            let leafUIDs = topCues.flatMap { $0.leafUIDs() }
            var values: [String: CueValue] = [:]
            for uid in leafUIDs {
                if let v = try await client.cueProperty(
                    workspace: id, cueUID: uid, property: config.readProperty),
                   let arr = v.arrayValue {
                    values[uid] = .params(arr)
                }
            }

            let model = GridModel(config: config)
            _ = model.buildTree(topCues) { values[$0] ?? .none }
            self.model = model
            self.rows = model.allRows()
            statusLine = "Loaded \(model.anchors().count) cues"
        } catch {
            statusLine = "Load failed: \(error)"
        }
    }

    // MARK: Submit changes (mic states + cue names + scribble strips)

    func submit(allMics: Bool = false) async {
        guard let client, let model, let id = selectedWorkspaceID else { return }
        let micWrites = allMics ? model.allWrites() : model.dirtyWrites()
        for w in micWrites + model.nameWrites() {
            await client.setCueProperty(workspace: id, cueUID: w.uid,
                                        property: w.property, value: w.value)
        }
        let scribbles = model.scribbleWrites(onlyDirty: !allMics)
        X32.sendScribbleNames(host: config.x32Host, port: config.x32Port,
                              template: config.scribbleTemplate, names: scribbles)
        model.markCommitted()
        statusLine = "Submitted \(micWrites.count) mic + \(model.nameDirtyCount()) name changes"
    }
}
