import sqlite3
from pathlib import Path

candidates=[Path("instance/portal_rh.db"),Path("instance/rh.db"),Path("portal_rh.db")]
db_path=next((p for p in candidates if p.exists()),None)
if not db_path:
    found=list(Path("instance").glob("*.db"))+list(Path("instance").glob("*.sqlite*"))
    db_path=found[0] if found else None
if not db_path:
    raise SystemExit("ERRO: banco SQLite não encontrado.")

backup=db_path.with_suffix(db_path.suffix+".backup-v72")
if not backup.exists():
    backup.write_bytes(db_path.read_bytes())
    print(f"Backup criado: {backup}")

con=sqlite3.connect(db_path)
cur=con.cursor()
cols={r[1] for r in cur.execute("PRAGMA table_info(time_period_closure)").fetchall()}
if "employee_viewed_at" not in cols:
    cur.execute("ALTER TABLE time_period_closure ADD COLUMN employee_viewed_at DATETIME")
con.commit()
con.close()
print("Migração V7.2 concluída com sucesso.")
