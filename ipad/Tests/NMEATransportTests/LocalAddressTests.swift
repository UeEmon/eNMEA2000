import XCTest
import Darwin
@testable import NMEATransport
final class LocalAddressTests: XCTestCase {
 func testReceiverDestinationsExcludeNonLANAndInactiveInterfaces() {
  let active = UInt32(IFF_UP | IFF_RUNNING)
  XCTAssertTrue(LocalAddresses.isLAN(name:"en0",flags:active,family:AF_INET))
  XCTAssertTrue(LocalAddresses.isLAN(name:"en5",flags:active,family:AF_INET6))
  for name in ["lo0","utun0","pdp_ip0","awdl0","llw0"] { XCTAssertFalse(LocalAddresses.isLAN(name:name,flags:active,family:AF_INET)) }
  XCTAssertFalse(LocalAddresses.isLAN(name:"en0",flags:UInt32(IFF_UP),family:AF_INET))
  XCTAssertFalse(LocalAddresses.isLAN(name:"en0",flags:active|UInt32(IFF_LOOPBACK),family:AF_INET))
  XCTAssertFalse(LocalAddresses.isLAN(name:"en0",flags:active,family:AF_LINK))
 }
 func testEnumeratedAddressesAreNumericAndUnambiguous() throws {
  // A disconnected runner may have no LAN addresses; never fabricate loopback as a target.
  let addresses = try LocalAddresses.current()
  XCTAssertEqual(Set(addresses.map(\.id)).count,addresses.count)
  for a in addresses {
   XCTAssertTrue(a.interface.hasPrefix("en")); XCTAssertFalse(a.address.isEmpty)
   XCTAssertNotEqual(a.address,"127.0.0.1"); XCTAssertNotEqual(a.address,"::1")
   if a.family == "IPv4" { var parsed=in_addr(); XCTAssertEqual(inet_pton(AF_INET,a.address,&parsed),1) }
   else { var parsed=in6_addr(); XCTAssertEqual(inet_pton(AF_INET6,a.address.components(separatedBy:"%")[0],&parsed),1) }
  }
  let families = addresses.map(\.family)
  if let v6 = families.firstIndex(of:"IPv6") { XCTAssertFalse(families[v6...].contains("IPv4")) }
 }
}
