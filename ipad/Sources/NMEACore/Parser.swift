import Foundation
/// Use on a single serial queue. Assemblies expire and never cross source endpoints.
public final class NMEAParser {
 private struct Assembly { var time: Date; var next: Int; var payload: String; var raw: [String] }
 private var fragments: [String: Assembly] = [:]
 private let decoder: AISDecoder
 public init() throws { decoder = try AISDecoder() }
 public func reset() { fragments.removeAll() }
 public func parse(_ line: String, source: String, now: Date = Date()) -> Event {
  var event = Event(source:source,raw:line); event.time = now
  do {
   fragments = fragments.filter { now.timeIntervalSince($0.value.time) < 30 }
   guard line.utf8.count <= 8192, let start = line.firstIndex(where: { $0 == "$" || $0 == "!" }) else { throw NMEAError.invalid("NMEA sentence missing") }
   let sentence = String(line[start...]).trimmingCharacters(in:.whitespacesAndNewlines)
   let split = sentence.split(separator:"*",omittingEmptySubsequences:false)
   guard split.count == 2, split[1].count == 2, let expected = UInt8(split[1],radix:16) else { throw NMEAError.invalid("NMEA checksum missing") }
   let body = String(split[0].dropFirst())
   guard body.utf8.reduce(UInt8(0),^) == expected else { throw NMEAError.invalid("NMEA checksum mismatch") }
   let f = body.components(separatedBy:",")
   guard let tag = f.first, tag.count >= 5 else { throw NMEAError.invalid("NMEA tag invalid") }
   let kind = String(tag.suffix(3)); event.kind = kind; event.fields["talker"] = String(tag.prefix(2))
   if kind == "VDM" || kind == "VDO" {
    guard f.count == 7, let total = Int(f[1]), (1...9).contains(total), let part = Int(f[2]), (1...total).contains(part), let fill = Int(f[6]), (0...5).contains(fill), part == total || fill == 0, !f[5].isEmpty, f[5].utf8.count <= 178, (f[3].isEmpty || (f[3].utf8.count == 1 && Int(f[3]) != nil)), ["","A","B","1","2"].contains(f[4]) else { throw NMEAError.invalid("AIS fragment header") }
    // Decode armoring early, including incomplete fragments, to reject corrupt assemblies.
    guard f[5].utf8.allSatisfy({ (48...87).contains($0) || (96...119).contains($0) }) else { throw NMEAError.invalid("AIS armoring") }
    var payload = f[5]
    if total > 1 {
     let key = [source,tag,f[3],f[4],String(total)].joined(separator:"|")
     if part == 1 {
      guard fragments[key] == nil else { fragments.removeValue(forKey:key); throw NMEAError.invalid("AIS fragment collision") }
      if fragments.count >= 4096 { fragments.removeAll() }
      fragments[key] = Assembly(time:now,next:2,payload:payload,raw:[sentence]); event.status = "pending"; return event
     }
     guard var a = fragments[key], a.next == part else { fragments.removeValue(forKey:key); throw NMEAError.invalid("AIS orphan/out-of-order fragment") }
     guard a.payload.utf8.count + payload.utf8.count <= 178 else { fragments.removeValue(forKey:key); throw NMEAError.invalid("AIS assembly oversized") }
     a.payload += payload; a.raw.append(sentence); a.next += 1
     if part < total { fragments[key] = a; event.status = "pending"; return event }
     fragments.removeValue(forKey:key); payload = a.payload; event.raw = a.raw.joined(separator:"\n")
    }
    event.fields.merge(try decoder.decode(payload:payload,fill:fill),uniquingKeysWith: { _,new in new }); event.fields["own"] = String(kind == "VDO")
    return event
   }
   event.fields["values"] = f.dropFirst().joined(separator:",")
   func set(_ key: String, _ index: Int) { if f.count > index && !f[index].isEmpty { event.fields[key] = f[index] } }
   func position(_ lat: Int,_ ns: Int,_ lon: Int,_ ew: Int) {
    guard f.count > ew, let a = coordinate(f[lat],f[ns],latitude:true), let b = coordinate(f[lon],f[ew],latitude:false) else { return }
    event.fields["lat"] = String(a); event.fields["lon"] = String(b)
   }
   switch kind {
   case "RMC": if f.count > 2 && f[2] == "A" && (f.count <= 12 || f[12] != "N") { position(3,4,5,6) }; set("speed",7); set("course",8); set("utc",1); set("date",9)
   case "GGA": if f.count > 6 && (Int(f[6]) ?? 0) > 0 { position(2,3,4,5) }; set("quality",6); set("satellites",7); set("altitude",9); set("utc",1)
   case "GLL": if f.count > 6 && f[6] == "A" && (f.count <= 7 || f[7] != "N") { position(1,2,3,4) }; set("utc",5)
   case "VTG": set("course",1); set("speed",5)
   case "HDT", "HDG": set("heading",1)
   case "ZDA": set("utc",1); set("day",2); set("month",3); set("year",4)
   default: event.status = "unsupported"
   }
  } catch { event.status = "error"; event.fields["error"] = error.localizedDescription }
  return event
 }
 private func coordinate(_ value: String,_ hemisphere: String,latitude: Bool) -> Double? {
  guard let n = Double(value), n >= 0, (latitude ? ["N","S"] : ["E","W"]).contains(hemisphere) else { return nil }
  let degrees = floor(n/100), minutes = n-degrees*100, result = degrees+minutes/60
  guard minutes < 60, result <= (latitude ? 90 : 180) else { return nil }
  return result * (["S","W"].contains(hemisphere) ? -1 : 1)
 }
}
