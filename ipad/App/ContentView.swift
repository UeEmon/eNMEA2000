import SwiftUI
import UIKit
import UniformTypeIdentifiers
import NMEACore
private enum Page: String, CaseIterable, Identifiable {
 case map = "GIS", events = "受信データ", watches = "監視対象", alerts = "アラート", settings = "設定"
 var id: String { rawValue }
 var icon: String { switch self { case .map: "map"; case .events: "list.bullet.rectangle"; case .watches: "binoculars"; case .alerts: "bell"; case .settings: "gearshape" } }
}
struct ContentView: View {
 @ObservedObject var model: AppModel
 @State private var page: Page? = .map
 @State private var filePicker = false
 @State private var clearConfirm = false
 var body: some View {
  NavigationSplitView {
   List(Page.allCases,selection:$page) { p in Label(p.rawValue,systemImage:p.icon).tag(p) }
    .navigationTitle("eNMEA iPad")
    .safeAreaInset(edge:.bottom) {
     VStack(alignment:.leading,spacing:10) {
      Label(model.status,systemImage:model.running ? "antenna.radiowaves.left.and.right" : "stop.circle").font(.caption)
      Button(model.running ? "受信停止" : "受信開始") { model.running ? model.stop() : model.start() }.buttonStyle(.borderedProminent).disabled(model.importing)
      Text("受信はアプリ表示中に動作します").font(.caption2).foregroundStyle(.secondary)
     }.padding()
    }
  } detail: {
   Group {
    switch page ?? .map {
    case .map: mapPage
    case .events: eventPage
    case .watches: watchPage
    case .alerts: alertPage
    case .settings: settingsPage
    }
   }.navigationTitle((page ?? .map).rawValue)
    .toolbar {
     ToolbarItemGroup(placement:.topBarTrailing) {
      if model.importing { ProgressView("読込中") }
      Button { filePicker = true } label: { Label("ファイル読込",systemImage:"folder") }.disabled(model.importing)
      Menu {
       Button("NMEAログを書き出す",systemImage:"square.and.arrow.up") { model.export() }
       Button("受信データを削除",systemImage:"trash",role:.destructive) { clearConfirm = true }
      } label: { Image(systemName:"ellipsis.circle") }
     }
    }
  }
  .fileImporter(isPresented:$filePicker,allowedContentTypes:[.plainText,.data],allowsMultipleSelection:false) { result in
   switch result { case .success(let urls): if let url = urls.first { model.importFile(url) }; case .failure(let e): model.error = e.localizedDescription }
  }
  .sheet(item:$model.editing) { watch in WatchEditor(model:model,initial:watch) }
  .sheet(isPresented:Binding(get:{model.exportURL != nil},set:{if !$0 { model.exportURL = nil }})) {
   if let url = model.exportURL { VStack(spacing:24) { Text("NMEAログを書き出す").font(.title2); ShareLink(item:url) { Label("ファイルに保存・共有",systemImage:"square.and.arrow.up") }; Button("閉じる") { model.exportURL = nil } }.padding() }
  }
  .alert("エラー",isPresented:Binding(get:{model.error != nil},set:{if !$0 {model.error = nil}})) { Button("閉じる") { model.error = nil } } message: { Text(model.error ?? "") }
  .confirmationDialog("受信データ・航跡・アラートを削除します。監視対象リストは保持します。",isPresented:$clearConfirm,titleVisibility:.visible) {
   Button("削除",role:.destructive) { model.clear() }
  }
 }
 private var mapPage: some View {
  HStack(spacing:0) {
   if model.mapURL != nil { MapView(model:model).overlay(alignment:.topLeading) {
    VStack(alignment:.leading,spacing:8) {
     Toggle("自己位置中心",isOn:$model.followOwn).toggleStyle(.switch)
      .onChange(of:model.followOwn) { _,v in UserDefaults.standard.set(v,forKey:"followOwn") }
     if let own = model.ownState.position {
      Text(String(format:"自己位置 %.5f°, %.5f°",own.lat,own.lon)).font(.caption.monospaced())
      Text("\(own.kind) / 最終測位 \(own.time.formatted(date:.omitted,time:.standard))").font(.caption2)
     } else { Text("自己位置の受信待ち").font(.caption) }
    }.padding(10).frame(width:265).background(.regularMaterial,in:RoundedRectangle(cornerRadius:10)).padding(12)
   } } else { ContentUnavailableView("GISを準備中",systemImage:"map") }
   if let track = model.selectedTrack {
    Divider()
    ScrollView {
     VStack(alignment:.leading,spacing:12) {
      HStack { Text(track.fields["shipname"] ?? "船舶詳細").font(.headline); Spacer(); Button { model.selected = nil } label: { Image(systemName:"xmark.circle") } }
      Text("MMSI \(track.mmsi)").font(.system(.body,design:.monospaced))
      Text(String(format:"緯度 %.6f / 経度 %.6f",track.lat,track.lon)).font(.caption)
      if let relative = model.selectedBearingDistance {
       LabeledContent("自己位置からの方位（真方位）",value:relative.bearingText)
       LabeledContent("自己位置からの距離",value:String(format:"%.2f NM",relative.distanceNM))
      } else { Text("自己位置未受信：方位・距離を計算できません").font(.caption).foregroundStyle(.secondary) }
      Button("監視対象に登録",systemImage:"binoculars") { model.register(track.mmsi) }.buttonStyle(.bordered)
      ForEach(track.fields.keys.sorted(),id:\.self) { k in VStack(alignment:.leading) { Text(k).font(.caption).foregroundStyle(.secondary); Text(track.fields[k] ?? "").textSelection(.enabled) } }
      Divider(); Text("航跡（最大100受信分）").font(.headline)
      ForEach(Array(track.trail.enumerated()),id:\.offset) { _,p in Text(String(format:"%.6f, %.6f",p[1],p[0])).font(.caption.monospaced()) }
     }.padding()
    }.frame(width:300)
   }
  }
 }
 private var eventPage: some View {
  List(model.events) { e in DisclosureGroup {
   Text(e.raw).font(.caption.monospaced()).textSelection(.enabled)
   ForEach(e.fields.keys.sorted(),id:\.self) { k in LabeledContent(k,value:e.fields[k] ?? "") }
  } label: { HStack { VStack(alignment:.leading) { Text(e.aisType.map { "AIS Type \($0)" } ?? e.kind); Text(e.mmsi ?? e.source).font(.caption).foregroundStyle(.secondary) }; Spacer(); Text(e.status).foregroundStyle(e.status == "error" ? .red : .secondary); Text(e.time,style:.time).font(.caption) } } }
 }
 private var watchPage: some View {
  List {
   Button("監視対象を追加",systemImage:"plus") { model.editing = Watch() }
   ForEach(model.watches) { w in
    HStack { Button { model.editing = w } label: { VStack(alignment:.leading) { Text(w.name.isEmpty ? "監視対象" : w.name); Text("MMSI: \(w.mmsi)  IMO: \(w.imo)").font(.caption); if !w.notes.isEmpty { Text(w.notes).font(.caption).foregroundStyle(.secondary) } } }; Spacer() }
     .swipeActions { Button("削除",role:.destructive) { model.deleteWatch(w.id) } }
     .contextMenu { Button("編集") { model.editing = w }; Button("削除",role:.destructive) { model.deleteWatch(w.id) } }
   }
  }
 }
 private var alertPage: some View {
  List(model.alerts) { a in Button { model.select(a.mmsi); page = .map } label: { HStack { Image(systemName:"bell.fill").foregroundStyle(.orange); VStack(alignment:.leading) { Text(a.name); Text("MMSI \(a.mmsi)").font(.caption) }; Spacer(); Text(a.time,style:.time) } } }
  .overlay { if model.alerts.isEmpty { ContentUnavailableView("アラートなし",systemImage:"bell") } }
 }
 private var settingsPage: some View {
  Form {
   Section("このiPadのIPアドレス") {
    if model.localAddresses.isEmpty {
     Text(model.addressError ?? "LANのIPアドレスがありません。Wi-Fiまたは有線LANに接続してください。").foregroundStyle(.secondary)
    }
    ForEach(model.localAddresses) { address in
     VStack(alignment:.leading,spacing:6) {
      Text("\(address.label)・\(address.family)").font(.caption).foregroundStyle(.secondary)
      HStack {
       Text(address.address).font(.system(.body,design:.monospaced)).textSelection(.enabled)
       Spacer()
       Button { UIPasteboard.general.string = address.address } label: { Label("コピー",systemImage:"doc.on.doc") }.buttonStyle(.borderless)
      }
     }
    }
    Button("IPアドレスを更新",systemImage:"arrow.clockwise") { model.refreshAddresses() }
    Text("送信機・エミュレータの送信先に、このIPアドレスと下のポート番号を指定してください。IPv4を優先して表示します。").font(.caption)
   }
   Section("受信設定") {
    LabeledContent("UDPポート") { TextField("10110",text:$model.udpPort).keyboardType(.numberPad).frame(width:100) }
    LabeledContent("TCPポート") { TextField("10111",text:$model.tcpPort).keyboardType(.numberPad).frame(width:100) }
    Text("同じLANから上に表示されたiPadのIPアドレスへユニキャストで送信してください。TCPは改行区切りです。設定変更後は受信を再開始します。").font(.caption)
   }
   Section("GISシンボル") {
    Picker("シンボル規格",selection:$model.standard) { Text("MIL-STD-2525D").tag("2525"); Text("APP-6D").tag("APP6") }
     .onChange(of:model.standard) { _,v in UserDefaults.standard.set(v,forKey:"symbolStandard") }
    Picker("自己位置シンボル",selection:$model.ownPlatform) { Text("船舶").tag("ship"); Text("航空機").tag("aircraft") }
     .onChange(of:model.ownPlatform) { _,v in UserDefaults.standard.set(v,forKey:"ownPlatform") }
    Toggle("自己位置をGIS中心に保持",isOn:$model.followOwn)
     .onChange(of:model.followOwn) { _,v in UserDefaults.standard.set(v,forKey:"followOwn") }
    Text("有効なAIVDOまたはGPS（RMC/GGA/GLL）を自己位置として使用します。最後に受信した有効な測位を表示します。方位は真北000°から時計回り、距離はNMです。中心保持中は目標を選択しても自己位置を中心に保ちます。").font(.caption)
    Text("背景地図：Natural Earth II（オフライン）").font(.caption)
   }
   Section("運用") {
    Text("バックグラウンド移行時は受信を停止します。ファイル読込は受信を停止して実行します。再開は受信開始を押してください。")
    Text("ファイル解析ではリアルタイム監視アラートを発生させません。ライブ受信では同じ船舶・監視条件について60秒間隔で記録します。")
    Text("保存先：このiPadのアプリ領域。アプリ削除でデータも消えるため、必要なログは書き出してください。")
   }
   Section("ライセンス") { Text("CesiumJS: Apache-2.0 / milsymbol: MIT / AIS schema: pyais MIT / Natural Earth: Public domain").font(.caption) }
  }.onAppear { model.refreshAddresses() }
 }
}
private struct WatchEditor: View {
 @ObservedObject var model: AppModel
 @State var watch: Watch
 @Environment(\.dismiss) private var dismiss
 init(model: AppModel,initial: Watch) { self.model = model; _watch = State(initialValue:initial) }
 var body: some View {
  NavigationStack {
   Form {
    TextField("船名・名称",text:$watch.name)
    TextField("MMSI（9桁）",text:$watch.mmsi).keyboardType(.numberPad)
    TextField("IMO（7桁）",text:$watch.imo).keyboardType(.numberPad)
    TextField("メモ",text:$watch.notes,axis:.vertical).lineLimit(3...6)
   }.navigationTitle("監視対象の編集")
    .toolbar { ToolbarItem(placement:.cancellationAction) { Button("取消") { dismiss() } }; ToolbarItem(placement:.confirmationAction) { Button("保存") { model.saveWatch(watch) } } }
    .alert("登録済みの船舶です",isPresented:Binding(get:{model.duplicate != nil},set:{if !$0 { model.duplicate = nil }})) {
     Button("既存の登録を更新") { model.updateDuplicate() }
     Button("取りやめ",role:.cancel) { model.pendingWatch = nil; model.duplicate = nil }
    } message: { Text("\(model.duplicate?.name ?? "") のMMSIまたはIMOが重複しています。既存の登録内容を更新しますか？") }
    .alert("保存できません",isPresented:Binding(get:{model.error != nil},set:{if !$0 {model.error = nil}})) { Button("閉じる") { model.error = nil } } message: { Text(model.error ?? "") }
  }.presentationDetents([.medium,.large])
 }
}
