//  ContentView.swift
//  QLab Flash
//
//  SKETCH — top-level layout: a Connect bar, then the mic grid. The grid +
//  drag-to-select is the real net-new work; see MicGridView and the README.

import SwiftUI
import QLabFlashCore

struct ContentView: View {
    @EnvironmentObject var store: AppStore

    var body: some View {
        VStack(spacing: 0) {
            ConnectBar()
            Divider()
            if store.rows.isEmpty {
                ContentUnavailableHint()
            } else {
                MicGridView()
            }
            Divider()
            HStack {
                Text(store.statusLine).font(.caption).foregroundStyle(.secondary)
                Spacer()
                Button("Reload") { Task { await store.loadGrid() } }
                Button("Submit changes") { Task { await store.submit() } }
                    .keyboardShortcut(.return, modifiers: .command)
            }
            .padding(8)
        }
        .sheet(isPresented: $store.showHelp) { HelpView() }
        .sheet(isPresented: $store.showContact) { ContactView() }
        .sheet(isPresented: $store.showAbout) { AboutView() }
    }
}

struct ConnectBar: View {
    @EnvironmentObject var store: AppStore

    var body: some View {
        HStack {
            TextField("QLab host", text: $store.config.qlabHost)
                .frame(width: 160)
            Button(store.isConnected ? "Reconnect" : "Connect") {
                Task { await store.connect() }
            }
            if !store.workspaces.isEmpty {
                Picker("Workspace", selection: $store.selectedWorkspaceID) {
                    ForEach(store.workspaces) { ws in
                        Text(ws.name).tag(Optional(ws.id))
                    }
                }
                .frame(width: 220)
                Button("Load") { Task { await store.loadGrid() } }
                    .disabled(store.selectedWorkspaceID == nil)
            }
            Toggle("Demo", isOn: $store.demoMode)
            Spacer()
        }
        .padding(8)
    }
}

struct ContentUnavailableHint: View {
    var body: some View {
        VStack(spacing: 8) {
            Image(systemName: "slider.horizontal.3").font(.largeTitle)
            Text("Connect to QLab and load a workspace to see the mic grid.")
                .foregroundStyle(.secondary)
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
    }
}
