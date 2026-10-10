import Foundation
import SwiftUI
import NMEACore
@MainActor final class AppModel: ObservableObject {
 @Published var tracks: [Track] = []
 @Published var events: [Event] = []
 @Published var watches: [Watch] = []
 @Published var alerts: [WatchAlert] = []
 @Published var selected: String?
 @Published var status = "停止中"
 @Published var running = false
 @Published var importing = false
 @Published var error: String?
 @Published var editing: Watch?
 @Published var duplicate: Watch?
 @Published var pendingWatch: Watch?
 @Published var exportURL: URL?
 @Published var mapURL: URL?
 @Published var standard = UserDefaults.standard.string(forKey:"symbolStandard") ?? "2525"
 @Published var udpPort = UserDefaults.standard.string(forKey:"udpPort") ?? "10110"
 @Published var tcpPort = UserDefaults.standard.string(forKey:"tcpPort") ?? "10111"
 @Published var focusRequest = 0
 private let queue = DispatchQueue(label:"nmea.processing",qos:.userInitiated)
 private var store: NMEAStore?
 private var parser: NMEAParser?
 private var receiver: Receiver?
 private var assets: AssetServer?
 private var scheduled = false
 var selectedTrack: Track? { tracks.first { $0.mmsi == selected } }
 init() {
  do {
   let directory = try FileManager.default.url(for:.applicationSupportDirectory,in:.userDomainMask,appropriateFor:nil,create:true).appendingPathComponent("eNMEA",isDirectory:true)
   try FileManager.default.createDirectory(at:directory,withIntermediateDirectories:true)
   store = try NMEAStore(path:directory.appendingPathComponent("nmea.sqlite").path); parser = try NMEAParser()
   let r = Receiver(queue:queue); receiver = r
   configureWorker()
   r.onState = { [weak self] state in Task { @MainActor in self?.status = state; if !state.contains("受信待機") { self?.running = false } } }
   refresh()
   guard let web = Bundle.main.url(forResource:"Web",withExtension:nil) else { throw NMEAError.invalid("同梱地図がありません。prepare-assets.shを実行して再ビルドしてください。") }
   assets = AssetServer(root:web)
   assets?.start { [weak self] result in Task { @MainActor in switch result { case .success(let url): self?.mapURL = url; case .failure(let e): self?.error = e.localizedDescription } } }
  } catch { self.error = error.localizedDescription }
 }
 private func configureWorker() {
  let store = store, parser = parser
  receiver?.onLines = { [weak self] lines,source in
   guard let store, let parser else { return }
   do { try store.insert(lines.filter { !$0.isEmpty }.map { parser.parse($0,source:source) }) }
   catch { Task { @MainActor in self?.error = error.localizedDescription } }
   Task { @MainActor in self?.scheduleRefresh() }
  }
 }
 private func scheduleRefresh() {
  guard !scheduled else { return }; scheduled = true
  Task { try? await Task.sleep(for:.milliseconds(500)); scheduled = false; refresh() }
 }
 func refresh() {
  let store = store
  queue.async { [weak self] in
   do {
    guard let store else { return }
    let t = try store.tracks(), e = try store.recentEvents(), w = try store.watches(), a = try store.alerts()
    Task { @MainActor in self?.tracks = t; self?.events = e; self?.watches = w; self?.alerts = a }
   } catch { Task { @MainActor in self?.error = error.localizedDescription } }
  }
 }
 func start() {
  guard let udp = UInt16(udpPort), let tcp = UInt16(tcpPort), udp > 0, tcp > 0 else { error = "ポート番号は1〜65535です。"; return }
  UserDefaults.standard.set(udpPort,forKey:"udpPort"); UserDefaults.standard.set(tcpPort,forKey:"tcpPort")
  let receiver = receiver, parser = parser
  guard receiver != nil, parser != nil else { error = "受信処理の初期化に失敗しています。"; return }
  running = true; status = "開始中"
  queue.async { [weak self] in do { parser?.reset(); try receiver?.start(udp:udp,tcp:tcp) } catch { Task { @MainActor in self?.running = false; self?.error = error.localizedDescription } } }
 }
 func stop() { let receiver = receiver; queue.async { receiver?.stop() }; running = false; status = "停止中" }
 func select(_ mmsi: String) { selected = mmsi; focusRequest += 1 }
 func register(_ mmsi: String) {
  var w = Watch(); w.mmsi = mmsi
  if let track = tracks.first(where: { $0.mmsi == mmsi }) { w.name = track.fields["shipname"] ?? ""; if let imo = track.fields["imo"], imo != "0" { w.imo = imo } }
  editing = w
 }
 func saveWatch(_ watch: Watch) {
  let store = store
  queue.async { [weak self] in
   do { try store?.saveWatch(watch); Task { @MainActor in self?.editing = nil; self?.pendingWatch = nil; self?.duplicate = nil; self?.refresh() } }
   catch NMEAError.duplicate(let existing) { Task { @MainActor in self?.pendingWatch = watch; self?.duplicate = existing } }
   catch { Task { @MainActor in self?.error = error.localizedDescription } }
  }
 }
 func updateDuplicate() { guard var w = pendingWatch, let existing = duplicate else { return }; w.id = existing.id; duplicate = nil; saveWatch(w) }
 func deleteWatch(_ id: String) { let store = store; queue.async { [weak self] in do { try store?.deleteWatch(id); Task { @MainActor in self?.refresh() } } catch { Task { @MainActor in self?.error = error.localizedDescription } } } }
 func clear() { let store = store, parser = parser; queue.async { [weak self] in do { parser?.reset(); try store?.clearReceived(); Task { @MainActor in self?.selected = nil; self?.refresh() } } catch { Task { @MainActor in self?.error = error.localizedDescription } } } }
 func importFile(_ url: URL) {
  guard !importing else { return }; stop(); importing = true
  // Import has its own assembler and alerts disabled, so old logs cannot trigger live alerts.
  let store = store
  queue.async { [weak self] in
   let access = url.startAccessingSecurityScopedResource(); defer { if access { url.stopAccessingSecurityScopedResource() } }
   do {
    let parser = try NMEAParser(), file = try FileHandle(forReadingFrom:url); defer { try? file.close() }
    var framer = LineFramer(); var count = 0
    while let data = try file.read(upToCount:65536), !data.isEmpty {
     let lines = framer.feed(data); try store?.insert(lines.map { parser.parse($0,source:"File:\(url.lastPathComponent)") },alerting:false); count += lines.count
    }
    try store?.insert(framer.feed(Data(),final:true).map { parser.parse($0,source:"File:\(url.lastPathComponent)") },alerting:false)
    Task { @MainActor in self?.status = "ファイル読込完了（\(count)行＋末尾）" }
   } catch { Task { @MainActor in self?.error = error.localizedDescription } }
   Task { @MainActor in self?.importing = false; self?.refresh() }
  }
 }
 func export() {
  let store = store, url = FileManager.default.temporaryDirectory.appendingPathComponent("nmea-\(UUID().uuidString).log")
  queue.async { [weak self] in do { try store?.export(to:url); Task { @MainActor in self?.exportURL = url } } catch { Task { @MainActor in self?.error = error.localizedDescription } } }
 }
}
