// swift-tools-version: 5.9
import PackageDescription
let package = Package(name: "NMEACore", platforms: [.iOS(.v17), .macOS(.v13)], products: [.library(name: "NMEACore", targets: ["NMEACore"]), .library(name: "NMEATransport", targets: ["NMEATransport"])], targets: [
 .systemLibrary(name: "CSQLite"),
 .target(name: "NMEACore", dependencies: ["CSQLite"], resources: [.process("Resources")]),
 .target(name: "NMEATransport", dependencies: ["NMEACore"]),
 .testTarget(name: "NMEATransportTests", dependencies: ["NMEATransport"]),
 .testTarget(name: "NMEACoreTests", dependencies: ["NMEACore"], resources: [.process("Resources")])])
