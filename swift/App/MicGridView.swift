//  MicGridView.swift
//  QLab Flash
//
//  SKETCH + the #1 net-new problem: a spreadsheet of cues (rows) × mics 1–32
//  (columns) with centered checkboxes, and DRAG-TO-SELECT a rectangular block of
//  cells. Qt gives block selection for free; in SwiftUI it's custom. Prototype
//  this first (macOS pointer, then iPad touch) before building the rest.
//
//  This starter renders the grid and toggles single cells. The drag-select
//  scaffolding (a DragGesture computing a row/col rectangle and tinting the
//  covered cells) is stubbed with TODOs to flesh out on a Mac.

import SwiftUI
import QLabFlashCore

struct MicGridView: View {
    @EnvironmentObject var store: AppStore

    private let cellSize: CGFloat = 28
    private let nameColumnWidth: CGFloat = 260

    var micCount: Int { store.config.micCount }

    // Rows that actually carry checkboxes (anchors). For the full hierarchy
    // view, render every row and only draw boxes where `row.cells[col]` exists.
    var anchorRows: [RowNode] { store.rows.filter { $0.isAnchor } }

    var body: some View {
        ScrollView([.horizontal, .vertical]) {
            VStack(alignment: .leading, spacing: 0) {
                headerRow
                ForEach(Array(anchorRows.enumerated()), id: \.offset) { _, row in
                    gridRow(row)
                }
            }
        }
    }

    private var headerRow: some View {
        HStack(spacing: 0) {
            Text("Cue")
                .frame(width: nameColumnWidth, alignment: .leading)
                .padding(.leading, 8)
            ForEach(1...micCount, id: \.self) { chan in
                Text(store.config.headerText(forChannel: chan))
                    .font(.caption2)
                    .frame(width: cellSize, height: cellSize)
                    // Vertical header text reads better for 32 narrow columns.
                    .rotationEffect(.degrees(-90))
            }
        }
        .frame(height: cellSize * 2)
        .background(.thinMaterial)
    }

    private func gridRow(_ row: RowNode) -> some View {
        HStack(spacing: 0) {
            Text(row.displayName)
                .lineLimit(1)
                .frame(width: nameColumnWidth, alignment: .leading)
                .padding(.leading, 8)
            ForEach(1...micCount, id: \.self) { chan in
                cellView(row: row, channel: chan)
            }
        }
    }

    @ViewBuilder
    private func cellView(row: RowNode, channel: Int) -> some View {
        if let cell = row.cells[channel] {
            Toggle("", isOn: Binding(
                get: { cell.unmuted },
                set: { cell.unmuted = $0; store.objectWillChange.send() }))
                .labelsHidden()
                .toggleStyle(.checkbox)   // macOS; use a custom checkbox on iPad
                .frame(width: cellSize, height: cellSize)
                .background(cell.unmuted ? Color.green.opacity(0.18)
                            : (cell.dirty ? Color.orange.opacity(0.18) : Color.clear))
                .border(Color.gray.opacity(0.15))
        } else {
            // Blank cell: this cue doesn't control this mic.
            Color.clear
                .frame(width: cellSize, height: cellSize)
                .border(Color.gray.opacity(0.08))
        }
    }

    // TODO (net-new): overlay a DragGesture that maps the drag rect to a
    // (rowRange × colRange) block, tints the covered cells, and on release lets
    // the user Mute/Unmute/Toggle the whole block. Then layer 30-step undo.
    // On iPad, replace the pointer drag with a touch-drag + larger hit targets.
}
