import sqlite3
from pathlib import Path

def find_db():
    candidates=[Path("instance/portal_rh.db"),Path("instance/rh.db"),Path("portal_rh.db")]
    for p in candidates:
        if p.exists():
            return p
    found=list(Path("instance").glob("*.db"))+list(Path("instance").glob("*.sqlite*"))
    return found[0] if found else None

db_path=find_db()
if not db_path:
    raise SystemExit("ERRO: banco SQLite não encontrado.")

backup=db_path.with_suffix(db_path.suffix+".backup-v732")
if not backup.exists():
    backup.write_bytes(db_path.read_bytes())
    print(f"Backup criado: {backup}")

con=sqlite3.connect(db_path)
cur=con.cursor()

# Preserve all cumulative fixes from V7.3.1
cur.execute("""
CREATE TABLE IF NOT EXISTS vacation_schedule (
 id INTEGER PRIMARY KEY,
 employee_id INTEGER NOT NULL,
 planned_start DATE NOT NULL,
 planned_return DATE,
 days INTEGER NOT NULL DEFAULT 30,
 status VARCHAR(20) NOT NULL DEFAULT 'planned',
 note VARCHAR(255),
 created_at DATETIME NOT NULL,
 created_by INTEGER NOT NULL,
 completed_at DATETIME,
 FOREIGN KEY(employee_id) REFERENCES employee(id),
 FOREIGN KEY(created_by) REFERENCES user(id)
)
""")
cur.execute("CREATE INDEX IF NOT EXISTS ix_vacation_schedule_employee_id ON vacation_schedule(employee_id)")
cols={r[1] for r in cur.execute("PRAGMA table_info(vacation_schedule)").fetchall()}
if "planned_return" not in cols:
    cur.execute("ALTER TABLE vacation_schedule ADD COLUMN planned_return DATE")
    print("OK: coluna planned_return adicionada.")

# Fill old programmed vacations using start + days as estimated return.
rows=cur.execute("""
SELECT id, planned_start, days
FROM vacation_schedule
WHERE planned_return IS NULL
  AND planned_start IS NOT NULL
""").fetchall()

from datetime import datetime, timedelta
for row_id, planned_start, days in rows:
    try:
        start=datetime.strptime(planned_start,"%Y-%m-%d").date()
        ret=start+timedelta(days=int(days or 0))
        cur.execute("UPDATE vacation_schedule SET planned_return=? WHERE id=?",(ret.isoformat(),row_id))
    except Exception:
        pass

con.commit()
con.close()
print("Correção V7.3.2 concluída.")
