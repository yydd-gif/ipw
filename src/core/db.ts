import fs from 'node:fs'
import path from 'node:path'
import initSqlJs, { type Database, type SqlJsStatic } from 'sql.js'

let SQL: SqlJsStatic | null = null

function wasmFile(file: string): string {
  const candidates = [
    path.join(process.cwd(), 'node_modules/sql.js/dist', file),
    path.join(__dirname, '../../node_modules/sql.js/dist', file),
    path.join(__dirname, '../../../node_modules/sql.js/dist', file)
  ]
  for (const candidate of candidates) {
    if (fs.existsSync(candidate)) return candidate
  }
  return candidates[0]!
}

async function loadSql(): Promise<SqlJsStatic> {
  if (SQL) return SQL
  SQL = await initSqlJs({
    locateFile: (file) => wasmFile(file)
  })
  return SQL
}

const SCHEMA = `
CREATE TABLE IF NOT EXISTS projects (
  id TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  type TEXT NOT NULL DEFAULT 'hybrid',
  owner TEXT DEFAULT '',
  supervisor TEXT DEFAULT '',
  contractor TEXT DEFAULT '',
  contract_no TEXT DEFAULT '',
  phase TEXT DEFAULT '',
  doc_no TEXT DEFAULT '',
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS daily_logs (
  id TEXT PRIMARY KEY,
  project_id TEXT NOT NULL,
  date TEXT NOT NULL,
  weather TEXT DEFAULT '',
  location TEXT DEFAULT '',
  work_done TEXT DEFAULT '',
  qs_check TEXT DEFAULT '',
  crew_count INTEGER DEFAULT 0,
  issues TEXT DEFAULT '',
  coordination TEXT DEFAULT '',
  created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS catalog_instances (
  id TEXT PRIMARY KEY,
  project_id TEXT NOT NULL,
  item_code TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'empty',
  payload TEXT DEFAULT '{}',
  generated_path TEXT,
  notes TEXT DEFAULT '',
  updated_at TEXT NOT NULL,
  print_status TEXT NOT NULL DEFAULT 'unprinted',
  content_fingerprint TEXT DEFAULT '',
  last_printed_at TEXT,
  last_printed_fingerprint TEXT DEFAULT '',
  UNIQUE(project_id, item_code)
);

CREATE TABLE IF NOT EXISTS uploads (
  id TEXT PRIMARY KEY,
  project_id TEXT NOT NULL,
  item_code TEXT NOT NULL,
  original_name TEXT NOT NULL,
  stored_path TEXT NOT NULL,
  created_at TEXT NOT NULL
);
`

export class SqliteStore {
  private db!: Database
  private filePath: string

  constructor(filePath: string) {
    this.filePath = filePath
  }

  async init(): Promise<void> {
    const Sql = await loadSql()
    fs.mkdirSync(path.dirname(this.filePath), { recursive: true })
    if (fs.existsSync(this.filePath)) {
      const file = fs.readFileSync(this.filePath)
      this.db = new Sql.Database(file)
    } else {
      this.db = new Sql.Database()
    }
    this.db.run(SCHEMA)
    this.migrate()
    this.persist()
  }

  private migrate(): void {
    this.ensureColumn('catalog_instances', 'print_status', "TEXT NOT NULL DEFAULT 'unprinted'")
    this.ensureColumn('catalog_instances', 'content_fingerprint', "TEXT DEFAULT ''")
    this.ensureColumn('catalog_instances', 'last_printed_at', 'TEXT')
    this.ensureColumn('catalog_instances', 'last_printed_fingerprint', "TEXT DEFAULT ''")
  }

  private ensureColumn(table: string, column: string, spec: string): void {
    const cols = this.all<{ name: string }>(`PRAGMA table_info(${table})`)
    if (cols.some((c) => c.name === column)) return
    this.db.run(`ALTER TABLE ${table} ADD COLUMN ${column} ${spec}`)
  }

  persist(): void {
    const data = this.db.export()
    fs.writeFileSync(this.filePath, Buffer.from(data))
  }

  exec(sql: string, params: unknown[] = []): void {
    this.db.run(sql, params as never[])
    this.persist()
  }

  get<T>(sql: string, params: unknown[] = []): T | undefined {
    const stmt = this.db.prepare(sql)
    stmt.bind(params as never[])
    if (!stmt.step()) {
      stmt.free()
      return undefined
    }
    const row = stmt.getAsObject() as T
    stmt.free()
    return row
  }

  all<T>(sql: string, params: unknown[] = []): T[] {
    const stmt = this.db.prepare(sql)
    stmt.bind(params as never[])
    const rows: T[] = []
    while (stmt.step()) {
      rows.push(stmt.getAsObject() as T)
    }
    stmt.free()
    return rows
  }
}
