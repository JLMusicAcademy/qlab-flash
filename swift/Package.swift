// swift-tools-version: 5.9
import PackageDescription

let package = Package(
    name: "QLabFlashCore",
    platforms: [.macOS(.v13), .iOS(.v16)],
    products: [
        .library(name: "QLabFlashCore", targets: ["QLabFlashCore"]),
    ],
    targets: [
        .target(name: "QLabFlashCore"),
        .testTarget(name: "QLabFlashCoreTests", dependencies: ["QLabFlashCore"]),
    ]
)
