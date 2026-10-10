import XCTest
@testable import NMEACore
final class OwnPositionTests: XCTestCase {
 private func sentence(_ body: String) -> String { "$" + body + "*" + String(format:"%02X",body.utf8.reduce(UInt8(0),^)) }
 private func event(_ kind: String,_ lat: String? = "35",_ lon: String? = "139",_ time: Double = 100) -> Event {
  var e = Event(source:"UDP",raw:""); e.kind=kind; e.time=Date(timeIntervalSince1970:time)
  e.fields=["mmsi":"123456789"]; e.fields["lat"]=lat; e.fields["lon"]=lon
  return e
 }
 func testOwnPositionGPSAIVDOValidityAndLatestFix() throws {
  let parser=try NMEAParser(); var own=OwnState()
  for body in ["GPRMC,120000,A,3530.000,N,13930.000,E,10,90,010126,,,A", "GNGGA,120001,3530.000,N,13930.000,E,1,08,1,0,M,0,M,,", "GPGLL,3530.000,N,13930.000,E,120002,A,A"] {
   own.consume(parser.parse(sentence(body),source:"GPS"))
   XCTAssertEqual(own.position?.lat,35.5); XCTAssertEqual(own.position?.lon,139.5)
  }
  own.consume(event("VDO","36","140",Date().timeIntervalSince1970+10))
  XCTAssertEqual(own.mmsi,"123456789"); XCTAssertEqual(own.position?.lat,36)
  own.consume(event("VDM","37","141",Date().timeIntervalSince1970+20))
  own.consume(event("RMC","34","138",1))
  var bad=event("GGA","nan","139",Date().timeIntervalSince1970+30); own.consume(bad)
  bad=event("VDO","91","181",Date().timeIntervalSince1970+30); own.consume(bad)
  bad=event("VDO","0","0",Date().timeIntervalSince1970+30); bad.status="pending"; own.consume(bad)
  own.consume(parser.parse(sentence("GPRMC,120000,V,0000.0,N,00000.0,E,0,0,010126,,,N"),source:"GPS"))
  XCTAssertNil(parser.parse(sentence("GPRMC,120000,A,0000.0,N,00000.0,E,0,0,010126,,,N"),source:"GPS").latitude)
  XCTAssertNil(parser.parse(sentence("GPGLL,0000.0,N,00000.0,E,120000,A,N"),source:"GPS").latitude)
  XCTAssertNil(parser.parse(sentence("GPGGA,120000,0000.0,N,00000.0,E,0,00,1,0,M,0,M,,"),source:"GPS").latitude)
  XCTAssertEqual(own.position?.lat,36)
  var staticOnly=event("VDO",nil,nil,Date().timeIntervalSince1970+40); staticOnly.fields["msg_type"]="5"; own.consume(staticOnly)
  XCTAssertEqual(own.position?.lat,36)
  own.consume(event("GLL","0","0",Date().timeIntervalSince1970+50))
  XCTAssertEqual(own.position?.lat,0); XCTAssertEqual(own.mmsi,"123456789")
 }
 func testStoreSeparatesOwnPositionPersistsAndClears() throws {
  let url=FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString+".sqlite")
  defer { for suffix in ["","-wal","-shm"] { try? FileManager.default.removeItem(atPath:url.path+suffix) } }
  do {
   let store=try NMEAStore(path:url.path)
   try store.insert([event("VDM"),event("VDO")])
   XCTAssertTrue(try store.tracks().isEmpty)
   var other=event("VDM","36","140",101); other.fields["mmsi"]="987654321"
   try store.insert([other,event("GGA","37","141",102)])
   XCTAssertEqual(try store.tracks().map(\.mmsi),["987654321"])
   XCTAssertEqual(try store.ownState().position?.lat,37)
   XCTAssertEqual(try store.recentEvents().count,4)
  }
  let reopened=try NMEAStore(path:url.path)
  XCTAssertEqual(try reopened.ownState().position?.lat,37)
  XCTAssertEqual(try reopened.ownState().mmsi,"123456789")
  try reopened.clearReceived()
  XCTAssertNil(try reopened.ownState().position)
  XCTAssertTrue(try reopened.tracks().isEmpty)
 }
 func testActualAIVDOAndVDMFragmentIsolation() throws {
  let lines=try String(contentsOf:Bundle.module.url(forResource:"all-types",withExtension:"log")!).split(separator:"\n").map(String.init)
  let parser=try NMEAParser(); var own=OwnState()
  for line in lines where line.contains(",2,") {
   let body=String(line.split(separator:"*")[0].dropFirst()).replacingOccurrences(of:"AIVDM",with:"AIVDO")
   let e=parser.parse(sentence(body),source:"UDP")
   own.consume(e)
   if e.status == "pending" { XCTAssertNil(own.position) }
  }
  XCTAssertNotNil(own.mmsi); XCTAssertNil(own.position) // Type 5 has identity, no coordinates.
  let line=lines.first { $0.contains("!AIVDM,1,1,") }!
  let body=String(line.split(separator:"*")[0].dropFirst()).replacingOccurrences(of:"AIVDM",with:"AIVDO")
  let e=parser.parse(sentence(body),source:"UDP")
  own.consume(e)
  XCTAssertEqual(e.status,"ok"); XCTAssertEqual(e.fields["own"],"true"); XCTAssertNotNil(own.position)
 }
 func testBearingRangeCardinalsDateLineAndDegenerateCases() {
  for (lat,lon,bearing) in [(1.0,0.0,0.0),(0.0,1.0,90.0),(-1.0,0.0,180.0),(0.0,-1.0,270.0)] {
   let relative=BearingDistance.between(lat:0,lon:0,targetLat:lat,targetLon:lon)!
   XCTAssertEqual(relative.bearing!,bearing,accuracy:1e-8)
   XCTAssertEqual(relative.distanceNM,60.04054,accuracy:0.0001)
  }
  let cross=BearingDistance.between(lat:0,lon:179,targetLat:0,targetLon:-179)!
  XCTAssertEqual(cross.bearing!,90,accuracy:1e-8); XCTAssertEqual(cross.distanceNM,120.08108,accuracy:0.0001)
  let same=BearingDistance.between(lat:35,lon:139,targetLat:35,targetLon:139)!
  XCTAssertEqual(same.distanceNM,0); XCTAssertNil(same.bearing); XCTAssertEqual(same.bearingText,"—")
  XCTAssertNil(BearingDistance.between(lat:0,lon:0,targetLat:0,targetLon:180)!.bearing)
  XCTAssertNil(BearingDistance.between(lat:.nan,lon:0,targetLat:1,targetLon:1))
  XCTAssertNil(BearingDistance.between(lat:91,lon:0,targetLat:1,targetLon:1))
  XCTAssertEqual(BearingDistance(distanceNM:1,bearing:359.999).bearingText,"000.0°")
 }
}
