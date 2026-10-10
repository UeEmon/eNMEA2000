import XCTest
@testable import NMEACore
final class CoreTests: XCTestCase {
 func checksum(_ body: String) -> String { "!" + body + "*" + String(format:"%02X",body.utf8.reduce(UInt8(0),^)) }
 func payload(_ bits: [Int]) -> (String,Int) {
  let fill = (6-bits.count%6)%6, padded = bits+Array(repeating:0,count:fill)
  return (String(decoding:stride(from:0,to:padded.count,by:6).map { i -> UInt8 in
   let v=padded[i..<i+6].reduce(0) { ($0<<1)|$1 }; return UInt8(v < 40 ? v+48 : v+56)
  },as:UTF8.self),fill)
 }
 func put(_ bits: inout [Int],_ start: Int,_ width: Int,_ value: Int) { for i in 0..<width { bits[start+i] = (value >> (width-i-1)) & 1 } }
 func testAllTypesFromExistingSystem() throws {
  let file = Bundle.module.url(forResource:"all-types",withExtension:"log")!
  let lines = try String(contentsOf:file).split(separator:"\n").map(String.init)
  let parser = try NMEAParser(), events = lines.map { parser.parse($0,source:"fixture") }
  XCTAssertEqual(events.filter { $0.status == "error" }.map(\.fields),[])
  XCTAssertEqual(Set(events.compactMap(\.aisType)),Set(0...28))
  XCTAssertEqual(events.filter { $0.status == "pending" }.count,1)
  let p24 = events.filter { $0.aisType == 24 }; XCTAssertGreaterThanOrEqual(p24.count,3)
 }
 func testChecksumAndUnknownSentence() throws {
  let parser = try NMEAParser()
  XCTAssertEqual(parser.parse("$GPRMC,1*00",source:"x").status,"error")
  XCTAssertEqual(parser.parse("$GPRMC,1",source:"x").status,"error")
  XCTAssertEqual(parser.parse(checksum("AIVDM,2,1,0,A,"+String(repeating:"1",count:179)+",0"),source:"x").status,"error")
  XCTAssertEqual(parser.parse(checksum("AIVDM,2,1,0,A,"+String(repeating:"1",count:100)+",0"),source:"x").status,"pending")
  XCTAssertEqual(parser.parse(checksum("AIVDM,2,2,0,A,"+String(repeating:"1",count:100)+",0"),source:"x").status,"error")
  XCTAssertEqual(parser.parse(checksum("GPXXX,1,2"),source:"x").status,"unsupported")
  let r = parser.parse(checksum("GPRMC,120000,A,3530.000,N,13930.000,E,10,90,010126,,,A"),source:"x")
  XCTAssertEqual(r.latitude,35.5); XCTAssertEqual(r.longitude,139.5)
  XCTAssertNil(parser.parse(checksum("GPRMC,120000,V,3530.000,N,13930.000,E,10,90,010126,,,A"),source:"x").latitude)
 }
 func testFragmentIsolationExpiryAndCollision() throws {
  let lines = try String(contentsOf:Bundle.module.url(forResource:"all-types",withExtension:"log")!).split(separator:"\n").map(String.init)
  let first = lines.first { $0.contains(",2,1,") }!, second = lines.first { $0.contains(",2,2,") }!
  let parser = try NMEAParser(), now = Date()
  XCTAssertEqual(parser.parse(first,source:"a",now:now).status,"pending")
  XCTAssertEqual(parser.parse(second,source:"b",now:now).status,"error")
  XCTAssertEqual(parser.parse(second,source:"a",now:now).aisType,5)
  XCTAssertEqual(parser.parse(first,source:"a",now:now).status,"pending")
  XCTAssertEqual(parser.parse(second,source:"a",now:now.addingTimeInterval(31)).status,"error")
  XCTAssertEqual(parser.parse(first,source:"a",now:now).status,"pending")
  XCTAssertEqual(parser.parse(first,source:"a",now:now).status,"error")
 }
 func testBinary25And26EveryVariant() throws {
  let decoder = try AISDecoder()
  for type in [25,26] { for addressed in [false,true] { for structured in [false,true] {
   let header = 40+(addressed ? 32 : 0)+(structured ? 16 : 0), trailer = type == 26 ? 24 : 0
   var bits = [Int](repeating:0,count:header+13+trailer)
   put(&bits,0,6,type); put(&bits,8,30,123456789); put(&bits,38,1,addressed ? 1 : 0); put(&bits,39,1,structured ? 1 : 0)
   var cursor = 40
   if addressed { put(&bits,cursor,30,987654321); put(&bits,cursor+30,2,3); cursor += 32 }
   if structured { put(&bits,cursor,16,65); cursor += 16 }
   put(&bits,cursor,13,0x1555)
   if type == 26 { put(&bits,bits.count-20,20,0xabcde) }
   let (p,f) = payload(bits), d = try decoder.decode(payload:p,fill:f)
   XCTAssertEqual(d["data_bits"],"13"); XCTAssertEqual(d["data"],"aaa8")
   if addressed { XCTAssertEqual(d["dest_mmsi"],"987654321"); XCTAssertEqual(d["dest_spare"],"3") }
   if structured { XCTAssertEqual(d["dac"],"1"); XCTAssertEqual(d["fid"],"1") }
   if type == 26 { XCTAssertEqual(d["radio"],String(0xabcde)) }
  } } }
  for type in [25,26] { for count in [38,39] { var short = [Int](repeating:0,count:count); put(&short,0,6,type); let (p,f)=payload(short); XCTAssertThrowsError(try decoder.decode(payload:p,fill:f)) } }
  var bits = [Int](repeating:0,count:40); put(&bits,0,6,26)
  let (p,f) = payload(bits); XCTAssertThrowsError(try decoder.decode(payload:p,fill:f))
 }
 func testSignedLowResolutionCoordinates() throws {
  let decoder = try AISDecoder()
  for type in [17,22,23] {
   var bits = [Int](repeating:0,count:type == 17 ? 80 : type == 22 ? 168 : 160)
   put(&bits,0,6,type); let offset = type == 22 ? 69 : 40
   put(&bits,offset,18,-60000); put(&bits,offset+18,17,-12000)
   let (p,f) = payload(bits), d = try decoder.decode(payload:p,fill:f)
   XCTAssertEqual(Double(d[type == 17 ? "lon" : "ne_lon"]!),-100)
   XCTAssertEqual(Double(d[type == 17 ? "lat" : "ne_lat"]!),-20)
  }
 }
 func testFramingAndOversizeRecovery() {
  var f = LineFramer()
  XCTAssertEqual(f.feed(Data("one\r".utf8)),[])
  XCTAssertEqual(f.feed(Data("\ntwo\nthree".utf8)),["one","two"])
  XCTAssertEqual(f.feed(Data(),final:true),["three"])
  XCTAssertEqual(f.feed(Data(repeating:65,count:9000)),[])
  XCTAssertEqual(f.feed(Data("\nvalid\n".utf8)),["valid"])
 }
 func testPersistenceWatchConflictIdentityAndAlertCooldown() throws {
  let dir = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
  try FileManager.default.createDirectory(at:dir,withIntermediateDirectories:true); defer { try? FileManager.default.removeItem(at:dir) }
  let path = dir.appendingPathComponent("test.sqlite").path
  var store: NMEAStore? = try NMEAStore(path:path)
  var w = Watch(); w.name = "Watch"; w.imo = "1234567"; try store!.saveWatch(w)
  var conflict = Watch(); conflict.imo = "1234567"
  XCTAssertThrowsError(try store!.saveWatch(conflict)) { e in guard case NMEAError.duplicate = e else { return XCTFail("Expected duplicate") } }
  var position = Event(source:"udp",raw:"position"); position.fields = ["msg_type":"1","mmsi":"123456789","lat":"35","lon":"139"]
  try store!.insert([position]); XCTAssertEqual(try store!.alerts().count,0)
  var identity = Event(source:"udp",raw:"identity"); identity.fields = ["msg_type":"5","mmsi":"123456789","imo":"1234567","shipname":"TEST"]
  try store!.insert([identity]); XCTAssertEqual(try store!.alerts().count,1)
  try store!.insert([EventCopy(position)]); XCTAssertEqual(try store!.alerts().count,1)
  var later = EventCopy(position); later.time = later.time.addingTimeInterval(61); try store!.insert([later]); XCTAssertEqual(try store!.alerts().count,2)
  XCTAssertEqual(try store!.tracks().first?.fields["shipname"],"TEST")
  XCTAssertTrue(try store!.tracks().first!.watched)
  store = nil; store = try NMEAStore(path:path)
  XCTAssertEqual(try store!.watches().count,1); XCTAssertEqual(try store!.tracks().count,1)
  let export = dir.appendingPathComponent("export.log"); try store!.export(to:export); XCTAssertTrue(try String(contentsOf:export).contains("identity"))
  try store!.clearReceived(); XCTAssertEqual(try store!.recentEvents().count,0); XCTAssertEqual(try store!.tracks().count,0); XCTAssertEqual(try store!.alerts().count,0); XCTAssertEqual(try store!.watches().count,1)
  try store!.deleteWatch(w.id); XCTAssertEqual(try store!.watches().count,0)
 }
 private func EventCopy(_ e: Event) -> Event { var copy = e; copy.id = UUID().uuidString; return copy }
}
