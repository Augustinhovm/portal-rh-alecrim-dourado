import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()
issues = []
warnings = []

env = os.getenv("APP_ENV", "development").lower()
secret = os.getenv("SECRET_KEY", "")
database = os.getenv("DATABASE_URL", "")
upload = os.getenv("UPLOAD_FOLDER", "")

if env != "production":
    warnings.append("APP_ENV ainda não está como production.")
if not secret or secret == "dev-change-me" or len(secret) < 32:
    issues.append("SECRET_KEY ausente/fraca. Use pelo menos 32 caracteres aleatórios.")
if not database:
    warnings.append("DATABASE_URL não definida: será usado SQLite local.")
elif not database.startswith(("postgresql://", "postgres://", "postgresql+psycopg://", "sqlite:")):
    issues.append("DATABASE_URL possui formato não reconhecido.")
if not upload:
    warnings.append("UPLOAD_FOLDER não definida: anexos usarão app/uploads.")

print("=== Verificação de produção ===")
for x in issues:
    print("[ERRO]", x)
for x in warnings:
    print("[AVISO]", x)

if issues:
    raise SystemExit(1)

print("[OK] Configuração mínima validada.")
