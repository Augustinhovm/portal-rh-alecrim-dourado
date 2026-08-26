import sqlite3
from pathlib import Path

candidates = [Path("instance/portal_rh.db"), Path("instance/rh.db"), Path("portal_rh.db")]
db_path = next((p for p in candidates if p.exists()), None)
if not db_path:
    # discover sqlite/db file
    found = list(Path("instance").glob("*.db")) + list(Path("instance").glob("*.sqlite*"))
    db_path = found[0] if found else None
if not db_path:
    raise SystemExit("Banco SQLite não encontrado na pasta instance.")

backup = db_path.with_suffix(db_path.suffix + ".backup-v65")
if not backup.exists():
    backup.write_bytes(db_path.read_bytes())
    print(f"Backup criado: {backup}")

con = sqlite3.connect(db_path)
cur = con.cursor()
cols = {r[1] for r in cur.execute("PRAGMA table_info(request)").fetchall()}
if "bank_effect_applied" not in cols:
    cur.execute("ALTER TABLE request ADD COLUMN bank_effect_applied BOOLEAN NOT NULL DEFAULT 0")
if "bank_effect_applied_at" not in cols:
    cur.execute("ALTER TABLE request ADD COLUMN bank_effect_applied_at DATETIME")

# Compatibilidade: na V6.4 e anteriores, todo bank_use aprovado era debitado imediatamente.
# Marcamos os já existentes como aplicados para impedir débito duplicado após a atualização.
cur.execute("""
UPDATE request
SET bank_effect_applied = 1,
    bank_effect_applied_at = COALESCE(decided_at, requested_at)
WHERE request_type='bank_use' AND status='approved'
""")
con.commit()
con.close()
print("Migração V6.5 concluída. Solicitações antigas aprovadas foram preservadas sem débito duplicado.")
