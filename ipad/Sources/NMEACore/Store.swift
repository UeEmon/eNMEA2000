import Foundation
import CSQLite
/// All calls must use the same serial queue as the parser and network callbacks.
public final class NMEAStore {
 private var db: OpaquePointer?
 private let encoder = JSONEncoder(), decoder = JSONDecoder()
 private let transient = unsafeBitCast(-1, to: sqlite3_destructor_type.self)
 public init(path: String) throws {
  guard sqlite3_open(path,&db) == SQLITE_OK else { throw NMEAError.database("SQLite open failed") }
  do {
   try run("PRAGMA journal_mode=WAL"); try run("PRAGMA foreign_keys=ON")
   try run("CREATE TABLE IF NOT EXISTS events(id TEXT PRIMARY KEY, time REAL NOT NULL, mmsi TEXT, payload TEXT NOT NULL)")
   try run("CREATE INDEX IF NOT EXISTS events_track ON events(mmsi,time DESC)")
   try run("CREATE TABLE IF NOT EXISTS identities(mmsi TEXT PRIMARY KEY,payload TEXT NOT NULL)")
   try run("CREATE TABLE IF NOT EXISTS positions(mmsi TEXT PRIMARY KEY,payload TEXT NOT NULL)")
   try run("CREATE TABLE IF NOT EXISTS watches(id TEXT PRIMARY KEY,mmsi TEXT,imo TEXT,payload TEXT NOT NULL)")
   try run("CREATE UNIQUE INDEX IF NOT EXISTS watch_mmsi ON watches(mmsi) WHERE mmsi != ''")
   try run("CREATE UNIQUE INDEX IF NOT EXISTS watch_imo ON watches(imo) WHERE imo != ''")
   try run("CREATE TABLE IF NOT EXISTS alerts(id TEXT PRIMARY KEY,time REAL NOT NULL,mmsi TEXT,watch_id TEXT,payload TEXT NOT NULL)")
   try run("CREATE INDEX IF NOT EXISTS alerts_cooldown ON alerts(mmsi,watch_id,time DESC)")
  } catch { sqlite3_close(db); db = nil; throw error }
 }
 deinit { sqlite3_close(db) }
 private func statement(_ sql: String,_ values: [String]) throws -> OpaquePointer {
  var s: OpaquePointer?
  guard sqlite3_prepare_v2(db,sql,-1,&s,nil) == SQLITE_OK, let s else { throw NMEAError.database(String(cString:sqlite3_errmsg(db))) }
  for (i,v) in values.enumerated() { guard sqlite3_bind_text(s,Int32(i+1),v,-1,transient) == SQLITE_OK else { sqlite3_finalize(s); throw NMEAError.database("SQLite bind") } }
  return s
 }
 private func run(_ sql: String,_ values: [String] = []) throws {
  let s = try statement(sql,values); defer { sqlite3_finalize(s) }
  guard sqlite3_step(s) == SQLITE_DONE || sql.hasPrefix("PRAGMA") else { throw NMEAError.database(String(cString:sqlite3_errmsg(db))) }
 }
 private func rows(_ sql: String,_ values: [String] = []) throws -> [[String]] {
  let s = try statement(sql,values); defer { sqlite3_finalize(s) }
  var result: [[String]] = []
  while true {
   let code = sqlite3_step(s)
   if code == SQLITE_DONE { return result }
   guard code == SQLITE_ROW else { throw NMEAError.database(String(cString:sqlite3_errmsg(db))) }
   result.append((0..<sqlite3_column_count(s)).map { i in sqlite3_column_text(s,i).map { String(cString:$0) } ?? "" })
  }
 }
 private func json<T: Encodable>(_ value: T) throws -> String { String(decoding:try encoder.encode(value),as:UTF8.self) }
 private func decode<T: Decodable>(_ string: String,as type: T.Type) throws -> T { try decoder.decode(type,from:Data(string.utf8)) }
 private func transaction<T>(_ body: () throws -> T) throws -> T {
  try run("BEGIN IMMEDIATE")
  do { let result = try body(); try run("COMMIT"); return result } catch { try? run("ROLLBACK"); throw error }
 }
 public func insert(_ events: [Event], alerting: Bool = true) throws {
  try transaction {
   let watchList = try watches()
   for e in events {
    try run("INSERT INTO events VALUES(?,?,?,?)",[e.id,String(e.time.timeIntervalSince1970),e.mmsi ?? "",try json(e)])
    guard e.status == "ok", let mmsi = e.mmsi else { continue }
    var identity: [String:String] = [:]
    if let row = try rows("SELECT payload FROM identities WHERE mmsi=?",[mmsi]).first { identity = try decode(row[0],as:[String:String].self) }
    for (k,v) in e.fields where !v.isEmpty && (k == "shipname" || k == "callsign" || k == "imo" || k == "ship_type") {
     if k == "imo" && (Int(v) ?? 0) == 0 { continue }; identity[k] = v
    }
    try run("INSERT OR REPLACE INTO identities VALUES(?,?)",[mmsi,try json(identity)])
    if let lat = e.latitude, let lon = e.longitude, abs(lat) <= 90, abs(lon) <= 180 {
     try run("INSERT OR REPLACE INTO positions VALUES(?,?)",[mmsi,try json(e)])
    }
    if alerting {
     for w in watchList where (!w.mmsi.isEmpty && w.mmsi == mmsi) || (!w.imo.isEmpty && w.imo == identity["imo"]) {
      let last = try rows("SELECT time FROM alerts WHERE mmsi=? AND watch_id=? ORDER BY time DESC LIMIT 1",[mmsi,w.id]).first?.first.flatMap(Double.init) ?? 0
      guard e.time.timeIntervalSince1970-last >= 60 else { continue }
      let a = WatchAlert(mmsi:mmsi,name:w.name.isEmpty ? identity["shipname"] ?? mmsi : w.name,eventID:e.id)
      try run("INSERT INTO alerts VALUES(?,?,?,?,?)",[a.id,String(e.time.timeIntervalSince1970),mmsi,w.id,try json(a)])
     }
    }
   }
  }
 }
 public func recentEvents(limit: Int = 500, mmsi: String? = nil) throws -> [Event] {
  let rows = try mmsi.map { try self.rows("SELECT payload FROM events WHERE mmsi=? ORDER BY time DESC LIMIT ?",[$0,String(max(1,min(limit,1000)))]) } ?? self.rows("SELECT payload FROM events ORDER BY time DESC LIMIT ?",[String(max(1,min(limit,1000)))])
  return try rows.map { try decode($0[0],as:Event.self) }
 }
 public func watches() throws -> [Watch] { try rows("SELECT payload FROM watches ORDER BY id").map { try decode($0[0],as:Watch.self) } }
 public func saveWatch(_ input: Watch) throws {
  var w = input; w.mmsi = w.mmsi.trimmingCharacters(in:.whitespacesAndNewlines); w.imo = w.imo.trimmingCharacters(in:.whitespacesAndNewlines)
  func digits(_ s: String,_ count: Int) -> Bool { s.utf8.count == count && s.utf8.allSatisfy { (48...57).contains($0) } && (Int(s) ?? 0) > 0 }
  guard (!w.mmsi.isEmpty || !w.imo.isEmpty), (w.mmsi.isEmpty || digits(w.mmsi,9)), (w.imo.isEmpty || digits(w.imo,7)) else { throw NMEAError.invalid("MMSIは9桁、IMOは7桁の数字です。いずれかを入力してください。") }
  try transaction {
   if let existing = try watches().first(where: { $0.id != w.id && ((!w.mmsi.isEmpty && $0.mmsi == w.mmsi) || (!w.imo.isEmpty && $0.imo == w.imo)) }) { throw NMEAError.duplicate(existing) }
   try run("INSERT OR REPLACE INTO watches VALUES(?,?,?,?)",[w.id,w.mmsi,w.imo,try json(w)])
  }
 }
 public func deleteWatch(_ id: String) throws { try run("DELETE FROM watches WHERE id=?",[id]) }
 public func alerts() throws -> [WatchAlert] { try rows("SELECT payload FROM alerts ORDER BY time DESC LIMIT 500").map { try decode($0[0],as:WatchAlert.self) } }
 public func tracks() throws -> [Track] {
  let identities = try rows("SELECT mmsi,payload FROM identities").reduce(into:[String:[String:String]]()) { result,row in result[row[0]] = try decode(row[1],as:[String:String].self) }
  let list = try watches()
  return try rows("SELECT mmsi,payload FROM positions").map { row in
   let e = try decode(row[1],as:Event.self), mmsi = row[0]
   var fields = e.fields; fields.merge(identities[mmsi] ?? [:],uniquingKeysWith: { _,new in new })
   let trail = try recentEvents(limit:100,mmsi:mmsi).reversed().compactMap { e -> [Double]? in guard let lat = e.latitude, let lon = e.longitude else { return nil }; return [lon,lat] }
   return Track(mmsi:mmsi,lat:e.latitude!,lon:e.longitude!,fields:fields,watched:list.contains { $0.mmsi == mmsi || (!$0.imo.isEmpty && $0.imo == fields["imo"]) },trail:trail)
  }
 }
 public func clearReceived() throws {
  try transaction { for table in ["events","identities","positions","alerts"] { try run("DELETE FROM \(table)") } }
  try run("PRAGMA wal_checkpoint(TRUNCATE)"); try run("VACUUM")
 }
 public func export(to url: URL) throws {
  // Stream a consistent snapshot to disk; exports include the original fragment lines.
  try transaction {
   FileManager.default.createFile(atPath:url.path,contents:nil)
   let file = try FileHandle(forWritingTo:url); defer { try? file.close() }
   let s = try statement("SELECT payload FROM events WHERE payload NOT LIKE '%\"status\":\"pending\"%' ORDER BY time ASC",[]); defer { sqlite3_finalize(s) }
   while true { let code = sqlite3_step(s); if code == SQLITE_DONE { break }; guard code == SQLITE_ROW, let p = sqlite3_column_text(s,0) else { throw NMEAError.database("Export read") }; let e = try decode(String(cString:p),as:Event.self); try file.write(contentsOf:Data((e.raw+"\n").utf8)) }
  }
 }
}
