"""Migração única da versão 2 para a versão 3.

Converte datas/horários que eram gravados em UTC sem indicação de fuso para
America/Sao_Paulo. Cria um marcador para impedir execução duplicada.
"""
from pathlib import Path
from datetime import datetime
import shutil
from app import create_app
from app.extensions import db
from app.models import User, TimeClock, MedicalCertificate, Request, Document, AuditLog
from app.timezone import utc_naive_to_local

app = create_app()

with app.app_context():
    marker = Path(app.instance_path) / ".timezone_migrated_v3"
    if marker.exists():
        print("A migração de fuso já foi executada neste banco. Nenhuma alteração foi feita.")
        raise SystemExit(0)

    db_path = db.engine.url.database
    if db.engine.url.get_backend_name() == "sqlite" and db_path:
        source = Path(db_path)
        if source.exists():
            backup = source.with_name(f"{source.stem}_backup_antes_fuso_v3_{datetime.now().strftime('%Y%m%d_%H%M%S')}{source.suffix}")
            shutil.copy2(source, backup)
            print(f"Backup criado: {backup}")

    fields = [
        (User, "created_at"),
        (TimeClock, "punched_at"),
        (MedicalCertificate, "uploaded_at"),
        (Request, "requested_at"),
        (Request, "decided_at"),
        (Document, "uploaded_at"),
        (AuditLog, "created_at"),
    ]

    changed = 0
    for model, field in fields:
        for row in model.query.all():
            value = getattr(row, field)
            if value is not None:
                setattr(row, field, utc_naive_to_local(value))
                changed += 1

    db.session.commit()
    marker.write_text("Migrado para America/Sao_Paulo\n", encoding="utf-8")
    print(f"Migração concluída. {changed} campos de data/hora foram convertidos para America/Sao_Paulo.")
