import sqlite3
from pathlib import Path

candidates=[Path("instance/portal_rh.db"),Path("instance/rh.db"),Path("portal_rh.db")]
db_path=next((p for p in candidates if p.exists()),None)
if not db_path:
    found=list(Path("instance").glob("*.db"))+list(Path("instance").glob("*.sqlite*"))
    db_path=found[0] if found else None
if not db_path:
    raise SystemExit("ERRO: banco SQLite não encontrado.")

backup=db_path.with_suffix(db_path.suffix+".backup-v73")
if not backup.exists():
    backup.write_bytes(db_path.read_bytes())
    print(f"Backup criado: {backup}")

con=sqlite3.connect(db_path)
cur=con.cursor()
cur.executescript("""
CREATE TABLE IF NOT EXISTS vacation_schedule (
 id INTEGER PRIMARY KEY,
 employee_id INTEGER NOT NULL,
 planned_start DATE NOT NULL,
 days INTEGER NOT NULL DEFAULT 30,
 status VARCHAR(20) NOT NULL DEFAULT 'planned',
 note VARCHAR(255),
 created_at DATETIME NOT NULL,
 created_by INTEGER NOT NULL,
 completed_at DATETIME,
 FOREIGN KEY(employee_id) REFERENCES employee(id),
 FOREIGN KEY(created_by) REFERENCES user(id)
);
CREATE INDEX IF NOT EXISTS ix_vacation_schedule_employee_id ON vacation_schedule(employee_id);
""")
con.commit(); con.close()
print("Migração V7.3 concluída.")
