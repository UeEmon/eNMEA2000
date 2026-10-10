import Foundation
private struct AISField: Decodable {
 let name: String, width: Int, kind: String, signed: Bool, variable: Bool, spare: Bool, converter: String, offset: Int
}
public struct AISDecoder {
 private let schemas: [String: [AISField]]
 public init() throws {
  guard let url = Bundle.module.url(forResource: "ais-schema", withExtension: "json") else { throw NMEAError.invalid("AIS schema missing") }
  schemas = try JSONDecoder().decode([String: [AISField]].self, from: Data(contentsOf: url))
 }
 public func decode(payload: String, fill: Int) throws -> [String: String] {
  guard (0...5).contains(fill), !payload.isEmpty else { throw NMEAError.invalid("AIS fill/payload") }
  var bits: [Int] = []
  for c in payload.utf8 {
   let n: Int
   switch c { case 48...87: n = Int(c) - 48; case 96...119: n = Int(c) - 56
   default: throw NMEAError.invalid("AIS six-bit character") }
   bits += (0..<6).reversed().map { (n >> $0) & 1 }
  }
  guard bits.count >= fill + 38 else { throw NMEAError.invalid("AIS header truncated") }
  if fill > 0 {
   guard bits.suffix(fill).allSatisfy({ $0 == 0 }) else { throw NMEAError.invalid("AIS fill bits nonzero") }
   bits.removeLast(fill)
  }
  func unsigned(_ start: Int, _ width: Int) -> Int { bits[start..<start+width].reduce(0) { ($0 << 1) | $1 } }
  func hex(_ start: Int, _ end: Int) -> String {
   guard end > start else { return "" }
   return stride(from: start, to: end, by: 8).map { i in
    let len = min(8, end-i); return String(format: "%02x", unsigned(i, len) << (8-len))
   }.joined()
  }
  let type = unsigned(0,6)
  guard (0...28).contains(type) else { throw NMEAError.invalid("Unsupported AIS type \(type)") }
  if type == 25 || type == 26 {
   guard bits.count >= 40 else { throw NMEAError.invalid("AIS binary header truncated") }
   let addressed = unsigned(38,1) == 1, structured = unsigned(39,1) == 1
   let trailer = type == 26 ? 24 : 0
   var cursor = 40
   let required = 40 + (addressed ? 32 : 0) + (structured ? 16 : 0) + trailer
   guard bits.count >= required, bits.count <= (type == 25 ? 168 : 1064) else { throw NMEAError.invalid("AIS binary length") }
   var values = ["msg_type": String(type), "repeat": String(unsigned(6,2)), "mmsi": String(format:"%09d", unsigned(8,30)), "addressed": String(addressed), "structured": String(structured)]
   if addressed { values["dest_mmsi"] = String(format:"%09d", unsigned(cursor,30)); values["dest_spare"] = String(unsigned(cursor+30,2)); cursor += 32 }
   if structured { let app = unsigned(cursor,16); values["app_id"] = String(app); values["dac"] = String(app >> 6); values["fid"] = String(app & 63); cursor += 16 }
   let end = bits.count-trailer
   values["data"] = hex(cursor,end); values["data_bits"] = String(end-cursor)
   if type == 26 { let radio = unsigned(bits.count-20,20); values["radio"] = String(radio); values["radio_selector"] = String(radio >> 19); values["communication_state"] = String(radio & 0x7ffff) }
   return values
  }
  var name = "MessageType\(type == 0 ? 1 : type)"
  let minimums = [0:168,1:168,2:168,3:168,4:168,5:424,6:88,7:72,8:56,9:168,10:72,11:168,12:72,13:72,14:40,15:88,16:96,17:80,18:168,19:312,20:72,21:272,22:168,23:160,24:160,27:96,28:168]
  guard bits.count >= minimums[type,default:38], bits.count <= 1064 else { throw NMEAError.invalid("AIS type \(type) truncated/oversized") }
  if type == 8 { name = "MessageType8Default" }
  if type == 16 { guard bits.count == 96 || bits.count == 144 else { throw NMEAError.invalid("AIS16 length") }; name = bits.count == 96 ? "MessageType16DestinationA" : "MessageType16DestinationAB" }
  if type == 22 { name = unsigned(139,1) == 1 ? "MessageType22Addressed" : "MessageType22Broadcast" }
  if type == 24 {
   let part = unsigned(38,2)
   guard part < 2, part == 0 || bits.count >= 168 else { throw NMEAError.invalid("AIS24 part/length") }
   name = part == 0 ? "MessageType24PartA" : (String(unsigned(8,30)).hasPrefix("98") ? "MessageType24PartBAuxiliaryCraft" : "MessageType24PartB")
  }
  guard let schema = schemas[name] else { throw NMEAError.invalid("AIS layout unavailable") }
  var values: [String: String] = [:]
  for f in schema where !f.spare {
   let length = min(f.width, bits.count-f.offset)
   if length <= 0 { continue }
   if length < f.width && !f.variable { continue }
   if f.kind == "bytes" { values[f.name] = hex(f.offset,f.offset+length); values[f.name+"_bits"] = String(length); continue }
   if f.kind == "str" {
    let chars = stride(from:f.offset,to:f.offset+length-5,by:6).map { i -> UInt8 in let v = unsigned(i,6); return UInt8(v < 32 ? v+64 : v) }
    values[f.name] = String(decoding:chars,as:UTF8.self).replacingOccurrences(of:"[@ ]+$",with:"",options:.regularExpression); continue
   }
   guard length <= 32 else { throw NMEAError.invalid("AIS numeric width") }
   let raw = unsigned(f.offset,length)
   let number = f.signed && bits[f.offset] == 1 ? raw - (1 << length) : raw
   if f.kind == "bool" { values[f.name] = String(number != 0); continue }
   if f.name.contains("mmsi") { values[f.name] = String(format:"%09d", number); continue }
   var value = Double(number)
   switch f.converter {
   case "to_speed", "to_10th": value /= 10
   case "to_100th": value /= 100
   case "to_lat_lon": value /= 600000
   case "to_lat_lon_600": value /= 600
   case "to_lat_lon_60000": value /= 60000
   case "to_turn": if abs(number) < 127 { value = pow(Double(abs(number))/4.733,2) * (number < 0 ? -1 : 1) }
   default: break
   }
   values[f.name] = f.converter.isEmpty ? String(number) : String(value)
  }
  values["msg_type"] = String(type)
  if let lat = values["lat"].flatMap(Double.init), let lon = values["lon"].flatMap(Double.init), abs(lat) > 90 || abs(lon) > 180 { values.removeValue(forKey:"lat"); values.removeValue(forKey:"lon") }
  return values
 }
}
