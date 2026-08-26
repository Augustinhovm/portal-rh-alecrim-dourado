import sqlite3
from pathlib import Path

candidates = [Path("instance/portal_rh.db"), Path("instance/rh.db"), Path("portal_rh.db")]
db_path = next((p for p in candidates if p.exists()), None)
if db_path is None:
    found = list(Path("instance").glob("*.db")) + list(Path("instance").glob("*.sqlite*"))
    db_path = found[0] if found else None
if db_path is None:
    raise SystemExit("ERRO: banco SQLite não encontrado.")

backup = db_path.with_suffix(db_path.suffix + ".backup-v67")
if not backup.exists():
    backup.write_bytes(db_path.read_bytes())
    print(f"Backup criado: {backup}")

con = sqlite3.connect(db_path)
cur = con.cursor()
cols = {r[1] for r in cur.execute("PRAGMA table_info(user)").fetchall()}

if "must_change_password" not in cols:
    cur.execute("ALTER TABLE user ADD COLUMN must_change_password BOOLEAN NOT NULL DEFAULT 0")
if "password_changed_at" not in cols:
    cur.execute("ALTER TABLE user ADD COLUMN password_changed_at DATETIME")

# Usuários já existentes continuam com suas senhas atuais.
# A obrigação de troca passa a valer para novos cadastros e para redefinições feitas pelo RH.
con.commit()
con.close()
print("Migração V6.7 concluída com sucesso.")
