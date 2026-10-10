import XCTest
import Network
@testable import NMEATransport
final class TransportTests: XCTestCase {
 func testUDPAndSplitTCPReception() throws {
  let queue=DispatchQueue(label:"test.network")
  let receiver=Receiver(queue:queue)
  let udpReady=expectation(description:"UDP ready"), tcpReady=expectation(description:"TCP ready")
  let udpLine=expectation(description:"UDP line"), tcpLine=expectation(description:"TCP split line")
  receiver.onState = { s in if s == "UDP:20110 受信待機" { udpReady.fulfill() }; if s == "TCP:20111 受信待機" { tcpReady.fulfill() } }
  receiver.onLines = { lines,source in
   if source.hasPrefix("UDP:") && lines == ["$GPRMC,udp"] { udpLine.fulfill() }
   if source.hasPrefix("TCP:") && lines == ["$GPRMC,tcp"] { tcpLine.fulfill() }
  }
  try queue.sync { try receiver.start(udp:20110,tcp:20111) }
  defer { queue.sync { receiver.stop() } }
  wait(for:[udpReady,tcpReady],timeout:10)
  let udp=NWConnection(host:"127.0.0.1",port:20110,using:.udp)
  let tcp=NWConnection(host:"127.0.0.1",port:20111,using:.tcp)
  defer { udp.cancel(); tcp.cancel() }
  udp.stateUpdateHandler = { state in if case .ready = state { udp.send(content:Data("$GPRMC,udp\r\n".utf8),completion:.contentProcessed { error in XCTAssertNil(error) }) } }
  tcp.stateUpdateHandler = { state in if case .ready = state {
   tcp.send(content:Data("$GPRMC,".utf8),completion:.contentProcessed { error in
    XCTAssertNil(error); tcp.send(content:Data("tcp\r\n".utf8),completion:.contentProcessed { error in XCTAssertNil(error) })
   })
  } }
  udp.start(queue:queue); tcp.start(queue:queue)
  wait(for:[udpLine,tcpLine],timeout:10)
 }
 func testLoopbackAssetsAndPathIsolation() throws {
  let root=FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
  try FileManager.default.createDirectory(at:root,withIntermediateDirectories:true)
  defer { try? FileManager.default.removeItem(at:root) }
  try Data("offline GIS".utf8).write(to:root.appendingPathComponent("index.html"))
  let server=AssetServer(root:root), ready=expectation(description:"HTTP ready")
  var base: URL?
  server.start { r in switch r { case .success(let u): base=u; case .failure(let e): XCTFail(e.localizedDescription) }; ready.fulfill() }
  wait(for:[ready],timeout:10)
  XCTAssertEqual(base?.host,"127.0.0.1")
  let found=expectation(description:"bundle asset")
  URLSession.shared.dataTask(with:base!) { data,response,error in
   XCTAssertNil(error); XCTAssertEqual((response as? HTTPURLResponse)?.statusCode,200)
   XCTAssertEqual(String(decoding:data ?? Data(),as:UTF8.self),"offline GIS")
   XCTAssertTrue((response as? HTTPURLResponse)?.value(forHTTPHeaderField:"Content-Security-Policy")?.contains("worker-src") == true)
   found.fulfill()
  }.resume()
  let missing=expectation(description:"path rejected")
  let c=NWConnection(host:"127.0.0.1",port:NWEndpoint.Port(rawValue:UInt16(base!.port!))!,using:.tcp)
  defer { c.cancel() }
  c.stateUpdateHandler = { state in if case .ready = state {
   c.send(content:Data("GET /%2e%2e/secret HTTP/1.1\r\nHost: localhost\r\n\r\n".utf8),completion:.contentProcessed { _ in
    c.receive(minimumIncompleteLength:1,maximumLength:4096) { data,_,_,_ in
     XCTAssertTrue(String(decoding:data ?? Data(),as:UTF8.self).hasPrefix("HTTP/1.1 404")); missing.fulfill()
    }
   })
  } }
  c.start(queue:DispatchQueue(label:"test.http"))
  wait(for:[found,missing],timeout:10)
 }
}
