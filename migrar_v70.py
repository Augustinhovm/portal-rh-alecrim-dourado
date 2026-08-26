import sqlite3
from pathlib import Path
db_path=next((p for p in [Path("instance/portal_rh.db"),Path("instance/rh.db"),Path("portal_rh.db")] if p.exists()),None)
if not db_path:
    found=list(Path("instance").glob("*.db"))+list(Path("instance").glob("*.sqlite*")); db_path=found[0] if found else None
if not db_path: raise SystemExit("ERRO: banco SQLite não encontrado.")
backup=db_path.with_suffix(db_path.suffix+".backup-v70")
if not backup.exists(): backup.write_bytes(db_path.read_bytes()); print("Backup:",backup)
con=sqlite3.connect(db_path); cur=con.cursor()
cur.executescript("""
CREATE TABLE IF NOT EXISTS vacation (
 id INTEGER PRIMARY KEY, employee_id INTEGER NOT NULL, start_date DATE NOT NULL, days INTEGER NOT NULL DEFAULT 30,
 note VARCHAR(255), created_at DATETIME NOT NULL, created_by INTEGER NOT NULL,
 FOREIGN KEY(employee_id) REFERENCES employee(id), FOREIGN KEY(created_by) REFERENCES user(id));
CREATE INDEX IF NOT EXISTS ix_vacation_employee_id ON vacation(employee_id);
CREATE TABLE IF NOT EXISTS time_period_closure (
 id INTEGER PRIMARY KEY, employee_id INTEGER NOT NULL, year INTEGER NOT NULL, month INTEGER NOT NULL,
 status VARCHAR(20) NOT NULL DEFAULT 'closed', closed_at DATETIME NOT NULL, closed_by INTEGER NOT NULL,
 reopened_at DATETIME, reopened_by INTEGER, reason TEXT,
 FOREIGN KEY(employee_id) REFERENCES employee(id), FOREIGN KEY(closed_by) REFERENCES user(id),
 UNIQUE(employee_id,year,month));
CREATE INDEX IF NOT EXISTS ix_time_period_closure_employee_id ON time_period_closure(employee_id);
CREATE TABLE IF NOT EXISTS time_report_acknowledgement (
 id INTEGER PRIMARY KEY, employee_id INTEGER NOT NULL, year INTEGER NOT NULL, month INTEGER NOT NULL,
 acknowledged_at DATETIME NOT NULL, FOREIGN KEY(employee_id) REFERENCES employee(id),
 UNIQUE(employee_id,year,month));
CREATE INDEX IF NOT EXISTS ix_time_report_acknowledgement_employee_id ON time_report_acknowledgement(employee_id);
""")
con.commit(); con.close(); print("Migração V7.0 concluída.")
