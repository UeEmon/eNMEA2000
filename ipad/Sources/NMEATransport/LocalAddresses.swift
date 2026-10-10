import Foundation
import Darwin

public struct LocalAddress: Identifiable, Equatable, Sendable {
 public var id: String { "\(interface):\(address)" }
 public let interface: String
 public let address: String
 public let family: String
 public var label: String { interface == "en0" ? "Wi-Fi / LAN" : "LAN (\(interface))" }
}

/// Enumerates active LAN interfaces without querying an internet service.
/// Loopback, cellular, VPN and peer-to-peer interfaces are not receiver destinations.
public enum LocalAddresses {
 public static func current() throws -> [LocalAddress] {
  var head: UnsafeMutablePointer<ifaddrs>?
  guard getifaddrs(&head) == 0 else { throw POSIXError(POSIXErrorCode(rawValue:errno) ?? .EIO) }
  defer { if let head { freeifaddrs(head) } }
  var cursor = head
  var result: [LocalAddress] = []
  while let item = cursor {
   defer { cursor = item.pointee.ifa_next }
   guard let pointer = item.pointee.ifa_addr else { continue }
   let name = String(cString:item.pointee.ifa_name), family = Int32(pointer.pointee.sa_family)
   guard isLAN(name:name,flags:item.pointee.ifa_flags,family:family) else { continue }
   var buffer = [CChar](repeating:0,count:Int(NI_MAXHOST))
   let code = buffer.withUnsafeMutableBufferPointer { b in
    getnameinfo(pointer,socklen_t(pointer.pointee.sa_len),b.baseAddress,socklen_t(b.count),nil,0,NI_NUMERICHOST)
   }
   guard code == 0 else { continue }
   let address = String(cString:buffer)
   guard address != "0.0.0.0", address != "::" else { continue }
   result.append(LocalAddress(interface:name,address:address,family:family == AF_INET ? "IPv4" : "IPv6"))
  }
  return Array(Set(result.map(\.id))).compactMap { id in result.first { $0.id == id } }.sorted {
   if $0.family != $1.family { return $0.family == "IPv4" }
   if $0.interface != $1.interface { return $0.interface < $1.interface }
   return $0.address < $1.address
  }
 }
 static func isLAN(name: String,flags: UInt32,family: Int32) -> Bool {
  name.hasPrefix("en") && flags & UInt32(IFF_UP) != 0 && flags & UInt32(IFF_RUNNING) != 0 && flags & UInt32(IFF_LOOPBACK) == 0 && (family == AF_INET || family == AF_INET6)
 }
}
