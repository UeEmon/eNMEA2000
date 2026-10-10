import Foundation
import Network
import NMEACore
final class Receiver {
 private let queue: DispatchQueue
 private var listeners: [NWListener] = []
 private var connections: [UUID:NWConnection] = [:]
 var onLines: (([String],String) -> Void)?
 var onState: ((String) -> Void)?
 init(queue: DispatchQueue) { self.queue = queue }
 func start(udp: UInt16,tcp: UInt16) throws {
  stop()
  do {
   for (name,number,params) in [("UDP",udp,NWParameters.udp),("TCP",tcp,NWParameters.tcp)] {
    guard number > 0, let port = NWEndpoint.Port(rawValue:number) else { throw NMEAErrorLocal.badPort }
    let listener = try NWListener(using:params,on:port)
    listener.stateUpdateHandler = { [weak self] state in
     switch state { case .ready: self?.onState?("\(name):\(number) 受信待機")
     case .failed(let error): self?.onState?(error.localizedDescription); self?.stop()
     default: break }
    }
    listener.newConnectionHandler = { [weak self] connection in self?.accept(connection,udp:name == "UDP") }
    listeners.append(listener); listener.start(queue:queue)
   }
  } catch { stop(); throw error }
 }
 func stop() { listeners.forEach { $0.cancel() }; listeners.removeAll(); connections.values.forEach { $0.cancel() }; connections.removeAll() }
 private func accept(_ connection: NWConnection,udp: Bool) {
  guard connections.count < 128 else { connection.cancel(); return }
  let id = UUID(); connections[id] = connection
  // Include connection identity for TCP so reconnects cannot complete old fragments.
  let source = "\(udp ? "UDP" : "TCP"):\(connection.endpoint)\(udp ? "" : ":\(id)")"
  connection.stateUpdateHandler = { [weak self] state in
   switch state { case .failed, .cancelled: self?.connections.removeValue(forKey:id); default: break }
  }
  connection.start(queue:queue)
  if udp { receiveUDP(connection,source:source) }
  else { receiveTCP(connection,source:source,framer:LineFramer()) }
 }
 private func receiveUDP(_ c: NWConnection,source: String) {
  c.receiveMessage { [weak self] data,_,_,error in
   guard let self else { return }
   if let data { var f = LineFramer(); self.onLines?(f.feed(data,final:true),source) }
   if error == nil { self.receiveUDP(c,source:source) } else { c.cancel() }
  }
 }
 private func receiveTCP(_ c: NWConnection,source: String,framer: LineFramer) {
  c.receive(minimumIncompleteLength:1,maximumLength:65536) { [weak self] data,_,complete,error in
   guard let self else { return }; var f = framer
   self.onLines?(f.feed(data ?? Data(),final:complete),source)
   if !complete && error == nil { self.receiveTCP(c,source:source,framer:f) } else { c.cancel() }
  }
 }
}
private enum NMEAErrorLocal: LocalizedError { case badPort; var errorDescription: String? { "ポートは1〜65535を指定してください。" } }
