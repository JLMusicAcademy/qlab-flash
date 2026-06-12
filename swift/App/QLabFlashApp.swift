//  QLabFlashApp.swift
//  QLab Flash (native macOS + iPadOS)
//
//  SKETCH — drop into a multiplatform SwiftUI app target created in Xcode that
//  depends on the QLabFlashCore package. This is the app entry point.

import SwiftUI
import QLabFlashCore

@main
struct QLabFlashApp: App {
    @StateObject private var store = AppStore()

    var body: some Scene {
        WindowGroup {
            ContentView()
                .environmentObject(store)
                .frame(minWidth: 900, minHeight: 600)
        }
        #if os(macOS)
        .commands {
            // Native menus: About / Help / Contact, Undo, Reload, Submit.
            CommandGroup(replacing: .help) {
                Button("QLab Flash Help") { store.showHelp = true }
                Button("Contact…") { store.showContact = true }
            }
        }
        #endif
    }
}
