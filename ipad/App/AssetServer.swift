import Foundation
import Network
/// Read-only bundle server. Loopback binding enables Cesium workers without an internet service.
final class AssetServer {
 private let queue = DispatchQueue(label:"nmea.assets")
 private var listener: NWListener?
 private var connections: [UUID:NWConnection] = [:]
 private let root: URL
 init(root: URL) { self.root = root.resolvingSymlinksInPath() }
 func start(completion: @escaping (Result<URL,Error>) -> Void) {
  do {
   let parameters = NWParameters.tcp
   parameters.requiredLocalEndpoint = .hostPort(host:"127.0.0.1",port:.any)
   let l = try NWListener(using:parameters); listener = l
   var reported = false
   l.stateUpdateHandler = { state in
    guard !reported else { return }
    switch state {
    case .ready: if let p = l.port, let url = URL(string:"http://127.0.0.1:\(p.rawValue)/index.html") { reported = true; completion(.success(url)) }
    case .failed(let e): reported = true; completion(.failure(e))
    default: break
    }
   }
   l.newConnectionHandler = { [weak self] c in
    guard let self, self.connections.count < 64 else { c.cancel(); return }
    let id = UUID(); self.connections[id] = c
    c.stateUpdateHandler = { [weak self] state in switch state { case .failed, .cancelled: self?.connections.removeValue(forKey:id); default: break } }
    c.start(queue:self.queue); self.read(c,buffer:Data())
    self.queue.asyncAfter(deadline:.now()+10) { [weak c] in c?.cancel() }
   }
   l.start(queue:queue)
  } catch { completion(.failure(error)) }
 }
 private func read(_ c: NWConnection,buffer: Data) {
  c.receive(minimumIncompleteLength:1,maximumLength:16384) { [weak self] data,_,done,error in
   guard let self else { return }; var b = buffer; b.append(data ?? Data())
   guard b.count <= 16384, error == nil else { c.cancel(); return }
   if b.range(of:Data("\r\n\r\n".utf8)) != nil { self.respond(c,b) }
   else if !done { self.read(c,buffer:b) } else { c.cancel() }
  }
 }
 private func respond(_ c: NWConnection,_ request: Data) {
  let parts = String(decoding:request,as:UTF8.self).components(separatedBy:"\r\n")[0].split(separator:" ")
  var code = "404 Not Found", body = Data(), mime = "text/plain"
  var head = false
  if parts.count == 3, parts[0] == "GET" || parts[0] == "HEAD" {
   head = parts[0] == "HEAD"
   let raw = String(parts[1]).components(separatedBy:"?")[0]
   if let decoded = raw.removingPercentEncoding, decoded.hasPrefix("/"), !decoded.contains("\0") {
    let path = root.appendingPathComponent(String(decoded.dropFirst())).standardizedFileURL.resolvingSymlinksInPath()
    if path.path.hasPrefix(root.path+"/"), let data = try? Data(contentsOf:path,options:.mappedIfSafe) {
     code = "200 OK"; body = data
     mime = ["html":"text/html; charset=utf-8","js":"application/javascript","css":"text/css","json":"application/json","png":"image/png","jpg":"image/jpeg","jpeg":"image/jpeg","gif":"image/gif","svg":"image/svg+xml","wasm":"application/wasm","xml":"application/xml"][path.pathExtension.lowercased()] ?? "application/octet-stream"
    }
   }
  }
  let headers = "HTTP/1.1 \(code)\r\nContent-Type: \(mime)\r\nContent-Length: \(body.count)\r\nConnection: close\r\nX-Content-Type-Options: nosniff\r\nContent-Security-Policy: default-src 'self' blob: data:; script-src 'self' 'unsafe-eval' blob:; style-src 'self' 'unsafe-inline'; img-src 'self' blob: data:; connect-src 'self' blob:; worker-src 'self' blob:; object-src 'none'; frame-src 'none'; base-uri 'self'\r\n\r\n"
  var response = Data(headers.utf8); if !head { response.append(body) }
  c.send(content:response,completion:.contentProcessed { _ in c.cancel() })
 }
 deinit { listener?.cancel(); connections.values.forEach { $0.cancel() } }
}
