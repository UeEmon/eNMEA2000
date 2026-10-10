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
