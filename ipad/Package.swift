// swift-tools-version: 5.9
import PackageDescription
let package = Package(name: "NMEACore", platforms: [.iOS(.v17), .macOS(.v13)], products: [.library(name: "NMEACore", targets: ["NMEACore"])], targets: [
 .systemLibrary(name: "CSQLite"),
 .target(name: "NMEACore", dependencies: ["CSQLite"], resources: [.process("Resources")]),
 .testTarget(name: "NMEACoreTests", dependencies: ["NMEACore"], resources: [.process("Resources")])])
