import SwiftUI
@main struct NMEAApp: App {
 @StateObject private var model = AppModel()
 @Environment(\.scenePhase) private var scenePhase
 var body: some Scene {
  WindowGroup { ContentView(model:model).onChange(of:scenePhase) { _,phase in if phase == .background { model.stop() } } }
 }
}
