from pathlib import Path
from datetime import datetime
import shutil
import os

base = Path(__file__).resolve().parent
stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
backup_dir = base / "backups" / stamp
backup_dir.mkdir(parents=True, exist_ok=True)

instance = base / "instance"
uploads = Path(os.getenv("UPLOAD_FOLDER", base / "app" / "uploads"))

copied = []

if instance.exists():
    shutil.copytree(instance, backup_dir / "instance", dirs_exist_ok=True)
    copied.append("instance")

if uploads.exists():
    shutil.copytree(uploads, backup_dir / "uploads", dirs_exist_ok=True)
    copied.append("uploads")

if not copied:
    raise SystemExit("Nenhum banco ou pasta de uploads localizado para backup.")

print(f"Backup concluído em: {backup_dir}")
print("Incluído:", ", ".join(copied))
