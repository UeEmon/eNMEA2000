import Foundation
public struct Event: Codable, Identifiable {
 public var id: String = UUID().uuidString
 public var time: Date = Date()
 public var source: String
 public var raw: String
 public var kind: String = ""
 public var status: String = "ok"
 public var fields: [String: String] = [:]
 public var mmsi: String? { fields["mmsi"] }
 public var latitude: Double? { fields["lat"].flatMap(Double.init) }
 public var longitude: Double? { fields["lon"].flatMap(Double.init) }
 public var aisType: Int? { fields["msg_type"].flatMap(Int.init) }
 public init(source: String, raw: String) { self.source = source; self.raw = raw }
}
public struct Watch: Codable, Identifiable, Equatable {
 public var id: String = UUID().uuidString
 public var name: String = ""
 public var mmsi: String = ""
 public var imo: String = ""
 public var notes: String = ""
 public init() {}
}
public struct WatchAlert: Codable, Identifiable {
 public var id: String = UUID().uuidString
 public var time: Date = Date()
 public var mmsi: String
 public var name: String
 public var eventID: String
}
public struct Track: Codable, Identifiable {
 public var id: String { mmsi }
 public var mmsi: String
 public var lat: Double
 public var lon: Double
 public var fields: [String: String]
 public var watched: Bool
 public var trail: [[Double]]
}
public enum NMEAError: LocalizedError {
 case invalid(String), duplicate(Watch), database(String)
 public var errorDescription: String? {
  switch self { case .invalid(let s), .database(let s): return s
  case .duplicate: return "同じMMSIまたはIMOの監視対象が登録されています。" }
 }
}
/// Bounded line framing shared by TCP and streamed file imports.
public struct LineFramer {
 private var buffer = Data()
 private var dropping = false
 public init() {}
 public mutating func feed(_ data: Data, final: Bool = false) -> [String] {
  var lines: [String] = []
  for byte in data {
   if byte == 10 {
    if !dropping, !buffer.isEmpty { lines.append(String(decoding: buffer, as: UTF8.self).trimmingCharacters(in: .whitespacesAndNewlines)) }
    buffer.removeAll(keepingCapacity: true); dropping = false
   } else if !dropping {
    if buffer.count >= 8192 { buffer.removeAll(keepingCapacity: true); dropping = true }
    else { buffer.append(byte) }
   }
  }
  if final { if !dropping, !buffer.isEmpty { lines.append(String(decoding: buffer, as: UTF8.self).trimmingCharacters(in: .whitespacesAndNewlines)) }; buffer.removeAll(); dropping = false }
  return lines
 }
}

/// Last valid received own position; GPS and AIVDO share one GIS entity.
public struct OwnPosition: Codable {
 public var lat: Double
 public var lon: Double
 public var time: Date
 public var source: String
 public var kind: String
}
public struct OwnState: Codable {
 public var position: OwnPosition?
 public var mmsi: String?
 public init() {}
 public mutating func consume(_ event: Event) {
  guard event.status == "ok", event.kind == "VDO" || ["RMC","GGA","GLL"].contains(event.kind) else { return }
  if let position, event.time < position.time { return }
  if event.kind == "VDO", let id = event.mmsi { mmsi = id }
  guard let lat = event.latitude, let lon = event.longitude, lat.isFinite, lon.isFinite, abs(lat) <= 90, abs(lon) <= 180 else { return }
  position = OwnPosition(lat:lat,lon:lon,time:event.time,source:event.source,kind:event.kind)
 }
}
/// Great-circle range in nautical miles, initial true bearing clockwise from north.
public struct BearingDistance {
 public let distanceNM: Double
 public let bearing: Double?
 public var bearingText: String {
  guard let bearing else { return "—" }
  let rounded = (bearing * 10).rounded().truncatingRemainder(dividingBy:3600) / 10
  return String(format:"%05.1f°", rounded)
 }
 public static func between(lat: Double, lon: Double, targetLat: Double, targetLon: Double) -> BearingDistance? {
  guard [lat,lon,targetLat,targetLon].allSatisfy({ $0.isFinite }), abs(lat) <= 90, abs(targetLat) <= 90, abs(lon) <= 180, abs(targetLon) <= 180 else { return nil }
  let a = lat * .pi / 180, b = targetLat * .pi / 180, d = (targetLon-lon) * .pi / 180
  let h = pow(sin((b-a)/2),2) + cos(a)*cos(b)*pow(sin(d/2),2)
  let angle = 2 * asin(sqrt(max(0,min(1,h))))
  let y = sin(d)*cos(b), x = cos(a)*sin(b)-sin(a)*cos(b)*cos(d)
  let bearing = abs(sin(angle)) < 1e-12 ? nil : (atan2(y,x)*180 / .pi + 360).truncatingRemainder(dividingBy:360)
  return BearingDistance(distanceNM:angle*6371008.8/1852,bearing:bearing)
 }
}
