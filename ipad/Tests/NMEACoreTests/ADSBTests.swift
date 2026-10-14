import XCTest
@testable import NMEACore
/// ADS-B aircraft arrive as eADS-B2000's $PADSB, kept separate from AIS (no Type 9 bridge).
final class ADSBTests: XCTestCase {
 func padsb(_ body: String) -> String { "$" + body + "*" + String(format:"%02X",body.utf8.reduce(UInt8(0),^)) }
 func testParsesAircraft() throws {
  let parser = try NMEAParser()
  let e = parser.parse(padsb("PADSB,86d3a1,JAL123  ,35.549400,139.779800,12500,420.0,287.0,-1472,3"),source:"udp")
  XCTAssertEqual(e.status,"ok"); XCTAssertEqual(e.kind,"ADSB")
  XCTAssertEqual(e.icao,"86D3A1"); XCTAssertEqual(e.trackKey,"86D3A1"); XCTAssertNil(e.mmsi); XCTAssertNil(e.aisType)
  XCTAssertEqual(e.fields["callsign"],"JAL123"); XCTAssertEqual(e.fields["altitude_ft"],"12500"); XCTAssertEqual(e.fields["vertical_rate_fpm"],"-1472")
  XCTAssertEqual(e.latitude,35.5494); XCTAssertEqual(e.longitude,139.7798)
  let unknown = parser.parse(padsb("PADSB,840123,,,,,,,,"),source:"udp")
  XCTAssertEqual(unknown.status,"ok"); XCTAssertNil(unknown.latitude); XCTAssertNil(unknown.fields["callsign"])
 }
 func testRejectsInvalid() throws {
  let parser = try NMEAParser()
  for body in ["PADSB,86D3A1,JAL123,35,139,12500,420,287,-1472", "PADSB,86D3AZ,JAL123,35,139,,,,,", "PADSB,86D3A1,jal123,35,139,,,,,",
               "PADSB,86D3A1,,91,139,,,,,", "PADSB,86D3A1,,35,139,70000,,,,", "PADSB,86D3A1,,35,139,,,,,8", "PADSB,86D3A1,,35,139,nan,,,,"] {
   XCTAssertEqual(parser.parse(padsb(body),source:"udp").status,"error",body)
  }
  XCTAssertEqual(parser.parse("$PADSB,86D3A1,,,,,,,,*00",source:"udp").status,"error")
 }
 func testAircraftTrackSeparateFromShips() throws {
  let url = FileManager.default.temporaryDirectory.appendingPathComponent("adsb-\(UUID().uuidString).sqlite")
  defer { for suffix in ["","-wal","-shm"] { try? FileManager.default.removeItem(atPath:url.path+suffix) } }
  let store = try NMEAStore(path:url.path), parser = try NMEAParser()
  var ship = Event(source:"udp",raw:"ship"); ship.fields = ["msg_type":"1","mmsi":"123456789","lat":"35","lon":"139"]
  let first = parser.parse(padsb("PADSB,86D3A1,JAL123,35.50,139.70,12500,420.0,287.0,0,3"),source:"udp",now:Date(timeIntervalSince1970:1_000_000))
  let second = parser.parse(padsb("PADSB,86D3A1,JAL123,35.51,139.71,12500,420.0,287.0,0,3"),source:"udp",now:Date(timeIntervalSince1970:1_000_001))
  try store.insert([ship,first,second])
  let tracks = try store.tracks(trailFor:"86D3A1").sorted { $0.mmsi < $1.mmsi }
  XCTAssertEqual(tracks.map(\.mmsi),["123456789","86D3A1"]); XCTAssertEqual(tracks.map(\.aircraft),[false,true])
  XCTAssertEqual(tracks[1].fields["callsign"],"JAL123"); XCTAssertEqual(tracks[1].lat,35.51)
  XCTAssertEqual(tracks[1].trail,[[139.70,35.50],[139.71,35.51]])
  XCTAssertNil(tracks[1].fields["msg_type"])
 }
}
