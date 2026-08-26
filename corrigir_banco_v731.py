import sqlite3
from pathlib import Path

def find_db():
    candidates = [
        Path("instance/portal_rh.db"),
        Path("instance/rh.db"),
        Path("portal_rh.db"),
    ]
    for p in candidates:
        if p.exists():
            return p
    found = list(Path("instance").glob("*.db")) + list(Path("instance").glob("*.sqlite*"))
    return found[0] if found else None

db_path = find_db()
if not db_path:
    raise SystemExit("ERRO: banco SQLite não encontrado na pasta instance.")

backup = db_path.with_suffix(db_path.suffix + ".backup-v731")
if not backup.exists():
    backup.write_bytes(db_path.read_bytes())
    print(f"Backup criado: {backup}")

con = sqlite3.connect(db_path)
cur = con.cursor()

print("Verificando estrutura do banco...")

# ----- V7.0: fechamento mensal -----
cur.execute("""
CREATE TABLE IF NOT EXISTS time_period_closure (
    id INTEGER PRIMARY KEY,
    employee_id INTEGER NOT NULL,
    year INTEGER NOT NULL,
    month INTEGER NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'closed',
    closed_at DATETIME NOT NULL,
    closed_by INTEGER NOT NULL,
    reopened_at DATETIME,
    reopened_by INTEGER,
    reason TEXT,
    FOREIGN KEY(employee_id) REFERENCES employee(id),
    FOREIGN KEY(closed_by) REFERENCES user(id),
    UNIQUE(employee_id, year, month)
)
""")
cur.execute("CREATE INDEX IF NOT EXISTS ix_time_period_closure_employee_id ON time_period_closure(employee_id)")

# V7.2: employee_viewed_at may be missing even if table already existed.
closure_cols = {row[1] for row in cur.execute("PRAGMA table_info(time_period_closure)").fetchall()}
if "employee_viewed_at" not in closure_cols:
    cur.execute("ALTER TABLE time_period_closure ADD COLUMN employee_viewed_at DATETIME")
    print("OK: coluna employee_viewed_at adicionada.")

# ----- V7.0: ciência do colaborador -----
cur.execute("""
CREATE TABLE IF NOT EXISTS time_report_acknowledgement (
    id INTEGER PRIMARY KEY,
    employee_id INTEGER NOT NULL,
    year INTEGER NOT NULL,
    month INTEGER NOT NULL,
    acknowledged_at DATETIME NOT NULL,
    FOREIGN KEY(employee_id) REFERENCES employee(id),
    UNIQUE(employee_id, year, month)
)
""")
cur.execute("CREATE INDEX IF NOT EXISTS ix_time_report_acknowledgement_employee_id ON time_report_acknowledgement(employee_id)")

# ----- V7.0: férias realizadas -----
cur.execute("""
CREATE TABLE IF NOT EXISTS vacation (
    id INTEGER PRIMARY KEY,
    employee_id INTEGER NOT NULL,
    start_date DATE NOT NULL,
    days INTEGER NOT NULL DEFAULT 30,
    note VARCHAR(255),
    created_at DATETIME NOT NULL,
    created_by INTEGER NOT NULL,
    FOREIGN KEY(employee_id) REFERENCES employee(id),
    FOREIGN KEY(created_by) REFERENCES user(id)
)
""")
cur.execute("CREATE INDEX IF NOT EXISTS ix_vacation_employee_id ON vacation(employee_id)")

# ----- V7.3: férias programadas -----
cur.execute("""
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
)
""")
cur.execute("CREATE INDEX IF NOT EXISTS ix_vacation_schedule_employee_id ON vacation_schedule(employee_id)")

# ----- V6.9 photo -----
employee_cols = {row[1] for row in cur.execute("PRAGMA table_info(employee)").fetchall()}
if "profile_photo" not in employee_cols:
    cur.execute("ALTER TABLE employee ADD COLUMN profile_photo VARCHAR(255)")
    print("OK: coluna profile_photo adicionada.")
if "point_pin_hash" not in employee_cols:
    cur.execute("ALTER TABLE employee ADD COLUMN point_pin_hash VARCHAR(255)")
    print("OK: coluna point_pin_hash adicionada.")

# ----- V6.7 first access -----
user_cols = {row[1] for row in cur.execute("PRAGMA table_info(user)").fetchall()}
if "must_change_password" not in user_cols:
    cur.execute("ALTER TABLE user ADD COLUMN must_change_password BOOLEAN NOT NULL DEFAULT 0")
    print("OK: coluna must_change_password adicionada.")
if "password_changed_at" not in user_cols:
    cur.execute("ALTER TABLE user ADD COLUMN password_changed_at DATETIME")
    print("OK: coluna password_changed_at adicionada.")

# ----- V6.5 bank use state -----
request_cols = {row[1] for row in cur.execute("PRAGMA table_info(request)").fetchall()}
if "bank_effect_applied" not in request_cols:
    cur.execute("ALTER TABLE request ADD COLUMN bank_effect_applied BOOLEAN NOT NULL DEFAULT 0")
    print("OK: coluna bank_effect_applied adicionada.")
if "bank_effect_applied_at" not in request_cols:
    cur.execute("ALTER TABLE request ADD COLUMN bank_effect_applied_at DATETIME")
    print("OK: coluna bank_effect_applied_at adicionada.")

con.commit()
con.close()

print()
print("==========================================")
print(" CORRECAO CUMULATIVA V7.3.1 CONCLUIDA")
print("==========================================")
print("O banco foi verificado e as estruturas ausentes foram criadas.")
