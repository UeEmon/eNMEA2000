import SwiftUI
import WebKit
import NMEACore
struct MapView: UIViewRepresentable {
 @ObservedObject var model: AppModel
 func makeCoordinator() -> Coordinator { Coordinator(model:model) }
 func makeUIView(context: Context) -> WKWebView {
  let config = WKWebViewConfiguration()
  config.userContentController.add(context.coordinator,name:"nmea")
  let web = WKWebView(frame:.zero,configuration:config)
  web.navigationDelegate = context.coordinator; web.isOpaque = false
  web.scrollView.isScrollEnabled = false
  if let url = model.mapURL { web.load(URLRequest(url:url)) }
  context.coordinator.web = web
  return web
 }
 func updateUIView(_ web: WKWebView,context: Context) {
  if web.url == nil, let url = model.mapURL { web.load(URLRequest(url:url)) }
  context.coordinator.render()
 }
 static func dismantleUIView(_ web: WKWebView,coordinator: Coordinator) { web.configuration.userContentController.removeScriptMessageHandler(forName:"nmea"); web.stopLoading() }
 @MainActor final class Coordinator: NSObject,WKNavigationDelegate,WKScriptMessageHandler {
  let model: AppModel
  weak var web: WKWebView?
  var ready = false
  var lastFocus = -1
  var lastPayload = ""
  init(model: AppModel) { self.model = model }
  func webView(_ webView: WKWebView,didFinish navigation: WKNavigation!) { ready = true; render() }
  func webView(_ webView: WKWebView,didFail navigation: WKNavigation!,withError error: Error) { model.error = error.localizedDescription }
  func webView(_ webView: WKWebView,decidePolicyFor navigationAction: WKNavigationAction,decisionHandler: @escaping (WKNavigationActionPolicy) -> Void) {
   let url = navigationAction.request.url
   decisionHandler(url?.host == "127.0.0.1" && url?.port == model.mapURL?.port ? .allow : .cancel)
  }
  func userContentController(_ userContentController: WKUserContentController,didReceive message: WKScriptMessage) {
   guard message.frameInfo.isMainFrame, message.frameInfo.request.url?.host == "127.0.0.1", let body = message.body as? [String:String] else { return }
   if let e = body["error"] { model.error = e; return }
   guard let mmsi = body["mmsi"], model.tracks.contains(where: { $0.mmsi == mmsi }) else { return }
   if body["action"] == "select" { model.select(mmsi) }
   if body["action"] == "watch" { model.register(mmsi) }
  }
  func render() {
   guard ready, let web else { return }
   do {
    let data = try JSONEncoder().encode(model.tracks)
    let options: [String:Any] = ["selected":model.selected ?? "", "standard":model.standard]
    var ownOptions = options
    ownOptions["ownPlatform"] = model.ownPlatform
    ownOptions["followOwn"] = model.followOwn
    if let own = model.ownState.position {
     ownOptions["own"] = ["lat":own.lat,"lon":own.lon,"kind":own.kind] as [String:Any]
    }
    let opts = try JSONSerialization.data(withJSONObject:ownOptions)
    let payload = "window.renderTracks(\(String(decoding:data,as:UTF8.self)),\(String(decoding:opts,as:UTF8.self)));"
    if payload != lastPayload { lastPayload = payload; web.evaluateJavaScript(payload) { [weak self] _,error in if let error { self?.model.error = error.localizedDescription } } }
    if lastFocus != model.focusRequest, let mmsi = model.selected, let encoded = try? JSONEncoder().encode(mmsi) {
     lastFocus = model.focusRequest; if !model.followOwn { web.evaluateJavaScript("window.focusMmsi(\(String(decoding:encoded,as:UTF8.self)));"); }
    }
   } catch { model.error = error.localizedDescription }
  }
 }
}
