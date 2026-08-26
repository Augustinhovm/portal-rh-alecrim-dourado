import sqlite3
from pathlib import Path

candidates = [Path("instance/portal_rh.db"), Path("instance/rh.db"), Path("portal_rh.db")]
db_path = next((p for p in candidates if p.exists()), None)
if db_path is None:
    found = list(Path("instance").glob("*.db")) + list(Path("instance").glob("*.sqlite*"))
    db_path = found[0] if found else None
if db_path is None:
    raise SystemExit("ERRO: banco SQLite não encontrado.")

backup = db_path.with_suffix(db_path.suffix + ".backup-v69")
if not backup.exists():
    backup.write_bytes(db_path.read_bytes())
    print(f"Backup criado: {backup}")

con = sqlite3.connect(db_path)
cur = con.cursor()
cols = {r[1] for r in cur.execute("PRAGMA table_info(employee)").fetchall()}
if "profile_photo" not in cols:
    cur.execute("ALTER TABLE employee ADD COLUMN profile_photo VARCHAR(255)")
con.commit()
con.close()
print("Migração V6.9 concluída com sucesso.")
