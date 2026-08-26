import sqlite3
from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo

TZ = ZoneInfo("America/Sao_Paulo")
TODAY = datetime.now(TZ).date().isoformat()
MIGRATION_KEY = "v6.6_restore_future_bank_use_legacy"

candidates = [
    Path("instance/portal_rh.db"),
    Path("instance/rh.db"),
    Path("portal_rh.db"),
]

db_path = next((p for p in candidates if p.exists()), None)
if db_path is None:
    found = list(Path("instance").glob("*.db")) + list(Path("instance").glob("*.sqlite*"))
    db_path = found[0] if found else None

if db_path is None:
    raise SystemExit("ERRO: banco SQLite não encontrado na pasta instance.")

backup = db_path.with_suffix(db_path.suffix + ".backup-v66")
if not backup.exists():
    backup.write_bytes(db_path.read_bytes())
    print(f"Backup criado: {backup}")

con = sqlite3.connect(db_path)
con.row_factory = sqlite3.Row
cur = con.cursor()

# Migration marker table: prevents running the financial correction twice.
cur.execute("""
CREATE TABLE IF NOT EXISTS portal_migration (
    migration_key TEXT PRIMARY KEY,
    applied_at TEXT NOT NULL,
    details TEXT
)
""")

already = cur.execute(
    "SELECT 1 FROM portal_migration WHERE migration_key = ?",
    (MIGRATION_KEY,)
).fetchone()

if already:
    print("Correção V6.6 já foi aplicada anteriormente. Nenhum saldo foi alterado.")
    con.close()
    raise SystemExit(0)

# Ensure V6.5 columns exist, even if the user skipped the previous updater.
cols = {r["name"] for r in cur.execute("PRAGMA table_info(request)").fetchall()}
if "bank_effect_applied" not in cols:
    cur.execute("ALTER TABLE request ADD COLUMN bank_effect_applied BOOLEAN NOT NULL DEFAULT 0")
if "bank_effect_applied_at" not in cols:
    cur.execute("ALTER TABLE request ADD COLUMN bank_effect_applied_at DATETIME")

# Legacy behavior (V6.4 and earlier):
# approved bank_use was deducted immediately, even when request_date was in the future.
# V6.5 then started showing that future request as "programmed", causing a second subtraction
# in the displayed available balance.
#
# Only approved FUTURE bank uses that are still marked as already applied are repaired.
rows = cur.execute("""
SELECT id, employee_id, minutes, request_date
FROM request
WHERE request_type = 'bank_use'
  AND status = 'approved'
  AND request_date > ?
  AND COALESCE(bank_effect_applied, 0) = 1
ORDER BY employee_id, request_date, id
""", (TODAY,)).fetchall()

restored_by_employee = {}
for row in rows:
    minutes = int(row["minutes"] or 0)
    if minutes <= 0:
        continue

    cur.execute(
        "UPDATE employee SET bank_minutes = bank_minutes + ? WHERE id = ?",
        (minutes, row["employee_id"])
    )
    cur.execute("""
        UPDATE request
        SET bank_effect_applied = 0,
            bank_effect_applied_at = NULL
        WHERE id = ?
    """, (row["id"],))
    restored_by_employee[row["employee_id"]] = (
        restored_by_employee.get(row["employee_id"], 0) + minutes
    )

details = "; ".join(
    f"employee {employee_id}: +{minutes} min restaurados"
    for employee_id, minutes in sorted(restored_by_employee.items())
) or "nenhuma utilização futura antiga necessitou correção"

cur.execute("""
INSERT INTO portal_migration (migration_key, applied_at, details)
VALUES (?, ?, ?)
""", (
    MIGRATION_KEY,
    datetime.now(TZ).isoformat(timespec="seconds"),
    details
))

con.commit()

print()
print("==========================================")
print(" CORRECAO V6.6 CONCLUIDA")
print("==========================================")
if restored_by_employee:
    for employee_id, minutes in sorted(restored_by_employee.items()):
        h, m = divmod(minutes, 60)
        print(f"Colaborador ID {employee_id}: +{h:02d}:{m:02d} devolvidos ao saldo realizado.")
    print()
    print("Essas horas continuam como PROGRAMADAS e serão debitadas somente na data de uso.")
else:
    print("Nenhum saldo precisou ser restaurado.")

con.close()
