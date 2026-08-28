import os, uuid, re, unicodedata, hashlib
from io import BytesIO
from datetime import datetime, date, timedelta
import calendar
from flask import Blueprint, render_template, request, redirect, url_for, flash, abort, current_app, send_from_directory, send_file
from flask_login import login_required, current_user
from sqlalchemy import func
from werkzeug.utils import secure_filename
from openpyxl import Workbook
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, KeepTogether
from pypdf import PdfReader, PdfWriter
from PIL import Image as PILImage
from .extensions import db
from .models import User, Employee, TimeClock, MedicalCertificate, Request, Document, AuditLog, BankHourAdjustment, Vacation, VacationSchedule, TimePeriodClosure, TimeReportAcknowledgement, Payslip, ROLE_ADMIN, ROLE_MANAGER, ROLE_EMPLOYEE
from .security import roles_required, can_manage_employee, log_action
from .timezone import now_local, today_local

bp = Blueprint("rh", __name__, url_prefix="/rh")
ALLOWED_EXTENSIONS = {"pdf", "png", "jpg", "jpeg", "webp"}






def _normalize_person_name(value):
    value = unicodedata.normalize("NFKD", value or "")
    value = "".join(ch for ch in value if not unicodedata.combining(ch))
    value = value.lower()
    value = re.sub(r"[^a-z0-9]+", " ", value)
    return " ".join(value.split())


def _match_employee_from_text(text, employees):
    """
    Identifica o colaborador pelo nome completo encontrado no texto de uma página.
    Retorna (employee, status).
    """
    normalized_text = _normalize_person_name(text)
    if not normalized_text:
        return None, "sem_texto"

    document_tokens = set(normalized_text.split())
    candidates = []

    for emp in employees:
        normalized_name = _normalize_person_name(emp.full_name)
        name_tokens = [token for token in normalized_name.split() if token]
        if not name_tokens:
            continue

        if all(token in document_tokens for token in name_tokens):
            candidates.append((len(name_tokens), len(normalized_name), emp))

    if not candidates:
        return None, "nao_encontrado"

    candidates.sort(key=lambda item: (item[0], item[1]), reverse=True)
    best = candidates[0]

    if len(candidates) > 1 and candidates[1][0:2] == best[0:2]:
        return None, "ambiguo"

    return best[2], "automatico_pdf"


def _split_payslip_pdf_by_employee(file_storage, employees):
    """
    Lê um PDF consolidado página por página.

    Retorna:
    - groups: {employee_id: {"employee": Employee, "pages": [PageObject], "page_numbers": [int]}}
    - unmatched: [{"page": int, "reason": str}]
    """
    try:
        file_storage.stream.seek(0)
        reader = PdfReader(file_storage.stream)
    except Exception:
        try:
            file_storage.stream.seek(0)
        except Exception:
            pass
        raise ValueError("Não foi possível abrir o PDF consolidado.")

    groups = {}
    unmatched = []

    for index, page in enumerate(reader.pages, start=1):
        try:
            text = page.extract_text() or ""
        except Exception:
            text = ""

        emp, status = _match_employee_from_text(text, employees)

        if not emp:
            unmatched.append({"page": index, "reason": status})
            continue

        bucket = groups.setdefault(
            emp.id,
            {"employee": emp, "pages": [], "page_numbers": []}
        )
        bucket["pages"].append(page)
        bucket["page_numbers"].append(index)

    try:
        file_storage.stream.seek(0)
    except Exception:
        pass

    return groups, unmatched


def _save_employee_payslip_pages(emp, year, month, pages, original_name, matched_by):
    """
    Gera um PDF individual somente com as páginas associadas ao colaborador.
    Substitui o holerite existente da mesma competência.
    """
    writer = PdfWriter()
    for page in pages:
        writer.add_page(page)

    stored = f"holerite_{emp.id}_{year}_{month:02d}_{uuid.uuid4().hex}.pdf"
    output_path = os.path.join(current_app.config["UPLOAD_FOLDER"], stored)

    with open(output_path, "wb") as output_file:
        writer.write(output_file)

    existing = Payslip.query.filter_by(
        employee_id=emp.id,
        year=year,
        month=month,
    ).first()

    old_stored = None
    individual_original = f"Holerite - {emp.full_name} - {month:02d}-{year}.pdf"

    if existing:
        old_stored = existing.stored_name
        existing.original_name = individual_original
        existing.stored_name = stored
        existing.matched_by = matched_by
        existing.uploaded_at = now_local()
        existing.uploaded_by = current_user.id
        existing.employee_viewed_at = None
        item = existing
    else:
        item = Payslip(
            employee_id=emp.id,
            year=year,
            month=month,
            original_name=individual_original,
            stored_name=stored,
            matched_by=matched_by,
            uploaded_by=current_user.id,
        )
        db.session.add(item)

    db.session.flush()

    if old_stored and old_stored != stored:
        old_path = os.path.join(current_app.config["UPLOAD_FOLDER"], old_stored)
        try:
            if os.path.isfile(old_path):
                os.remove(old_path)
        except OSError:
            pass

    return item


def _parse_competence(value):
    try:
        year, month = map(int, (value or "").split("-"))
        if year < 2000 or month < 1 or month > 12:
            raise ValueError
        return year, month
    except Exception:
        raise ValueError("Informe uma competência válida no formato mês/ano.")


def _save_payslip_file(file):
    if not file or not file.filename:
        raise ValueError("Selecione um arquivo de holerite.")
    filename = secure_filename(file.filename)
    if "." not in filename or filename.rsplit(".", 1)[1].lower() != "pdf":
        raise ValueError("Os holerites devem ser enviados em PDF.")
    stored = f"holerite_{uuid.uuid4().hex}.pdf"
    file.save(os.path.join(current_app.config["UPLOAD_FOLDER"], stored))
    return filename, stored


def _upsert_payslip(emp, year, month, file, matched_by):
    original, stored = _save_payslip_file(file)
    existing = Payslip.query.filter_by(
        employee_id=emp.id, year=year, month=month
    ).first()

    old_stored = None
    if existing:
        old_stored = existing.stored_name
        existing.original_name = original
        existing.stored_name = stored
        existing.matched_by = matched_by
        existing.uploaded_at = now_local()
        existing.uploaded_by = current_user.id
        existing.employee_viewed_at = None
        item = existing
    else:
        item = Payslip(
            employee_id=emp.id,
            year=year,
            month=month,
            original_name=original,
            stored_name=stored,
            matched_by=matched_by,
            uploaded_by=current_user.id,
        )
        db.session.add(item)

    db.session.flush()

    if old_stored and old_stored != stored:
        old_path = os.path.join(current_app.config["UPLOAD_FOLDER"], old_stored)
        try:
            if os.path.isfile(old_path):
                os.remove(old_path)
        except OSError:
            pass

    return item


def _time_report_signature_code(ack, emp):
    raw = (
        f"{ack.id}|{emp.id}|{emp.user_id}|{ack.year}|{ack.month}|"
        f"{ack.acknowledged_at.isoformat()}"
    )
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest().upper()
    return f"RH-{ack.year}{ack.month:02d}-{digest[:20]}"


def _expected_daily_minutes(emp):
    """Jornada diária de referência. Usa horários padrão e, na ausência, carga semanal/5."""
    if emp.standard_start and emp.standard_end:
        start = datetime.combine(today_local(), emp.standard_start)
        end = datetime.combine(today_local(), emp.standard_end)
        minutes = int((end - start).total_seconds() // 60)
        # Considera 1h de intervalo padrão quando a jornada atravessa o período de almoço.
        if minutes > 6 * 60:
            minutes -= 60
        return max(minutes, 0)
    return int(round(float(emp.weekly_hours or 0) * 60 / 5))

def _month_clock_summary(emp, year, month):
    first = date(year, month, 1)
    last = date(year, month, calendar.monthrange(year, month)[1])
    rows = (TimeClock.query.filter(
        TimeClock.employee_id == emp.id,
        func.date(TimeClock.punched_at) >= first,
        func.date(TimeClock.punched_at) <= last
    ).order_by(TimeClock.punched_at.asc()).all())
    grouped = {}
    for row in rows:
        grouped.setdefault(row.punched_at.date(), []).append(row)
    expected = _expected_daily_minutes(emp)
    worked = 0
    expected_total = 0
    incomplete = 0
    balance = 0
    for day in range(1, last.day + 1):
        d = date(year, month, day)
        if d.weekday() >= 5 or d < emp.admission_date or d > today_local():
            continue
        day_rows = grouped.get(d, [])
        # Atestado cobre o dia: não gera déficit de jornada.
        covered = MedicalCertificate.query.filter(
            MedicalCertificate.employee_id == emp.id,
            MedicalCertificate.start_date <= d
        ).all()
        is_cert = any(c.start_date + timedelta(days=max(int(c.days or 1)-1,0)) >= d for c in covered)
        if is_cert:
            continue
        expected_total += expected
        wm = _worked_minutes_for_day(day_rows)
        worked += wm
        kinds = {x.kind for x in day_rows}
        if day_rows and not {"entrada", "saida"}.issubset(kinds):
            incomplete += 1
        if not day_rows:
            incomplete += 1
        balance += wm - expected
    return {"worked": worked, "expected": expected_total, "balance": balance, "incomplete": incomplete, "rows": rows}

def _add_years(value, years):
    """Adiciona anos preservando mês/dia; 29/02 vira 28/02 quando necessário."""
    target_year = value.year + years
    try:
        return value.replace(year=target_year)
    except ValueError:
        return value.replace(year=target_year, day=28)

def _vacation_entitlement(emp):
    """Resumo operacional de férias com período aquisitivo/concessivo e programação."""
    today = today_local()
    admission = emp.admission_date

    completed_periods = 0
    while _add_years(admission, completed_periods + 1) <= today:
        completed_periods += 1

    current_start = _add_years(admission, completed_periods)
    current_next_anniversary = _add_years(admission, completed_periods + 1)
    current_end = current_next_anniversary - timedelta(days=1)

    if completed_periods > 0:
        last_acq_start = _add_years(admission, completed_periods - 1)
        last_acq_end = _add_years(admission, completed_periods) - timedelta(days=1)
        concession_start = last_acq_end + timedelta(days=1)
        concession_end = _add_years(concession_start, 1) - timedelta(days=1)
    else:
        last_acq_start = None
        last_acq_end = None
        concession_start = None
        concession_end = None

    earned = completed_periods * 30
    vacations = Vacation.query.filter_by(employee_id=emp.id).all()
    used = sum(int(v.days or 0) for v in vacations)

    schedules = VacationSchedule.query.filter_by(employee_id=emp.id, status="planned").all()
    scheduled_days = sum(int(v.days or 0) for v in schedules)

    available = max(earned - used, 0)
    available_after_schedule = max(available - scheduled_days, 0)

    return {
        "completed_periods": completed_periods,
        "earned": earned,
        "used": used,
        "available": available,
        "scheduled_days": scheduled_days,
        "available_after_schedule": available_after_schedule,
        "current_acquisition_start": current_start,
        "current_acquisition_end": current_end,
        "next_entitlement_date": current_next_anniversary,
        "last_acquisition_start": last_acq_start,
        "last_acquisition_end": last_acq_end,
        "concession_start": concession_start,
        "concession_end": concession_end,
    }

def _pdf_text(value):
    """Escape basic XML-sensitive characters used by ReportLab Paragraph."""
    if value is None:
        return ""
    return str(value).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

def _month_name_pt(month):
    names = ["", "Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho",
             "Julho", "Agosto", "Setembro", "Outubro", "Novembro", "Dezembro"]
    return names[month] if 1 <= month <= 12 else str(month)

def _kind_label(kind):
    return {
        "entrada": "Entrada",
        "saida_intervalo": "Saída intervalo",
        "retorno": "Retorno",
        "saida": "Saída",
    }.get(kind, (kind or "").replace("_", " ").title())


def _format_minutes(total_minutes):
    """Formata minutos com sinal opcional em HH:MM."""
    total_minutes = int(round(total_minutes or 0))
    sign = "-" if total_minutes < 0 else ""
    total_minutes = abs(total_minutes)
    hours, minutes = divmod(total_minutes, 60)
    return f"{sign}{hours:02d}:{minutes:02d}"

def _worked_minutes_for_day(day_rows):
    """Calcula horas efetivamente registradas no dia a partir das marcações principais."""
    by_kind = {"entrada": [], "saida_intervalo": [], "retorno": [], "saida": []}
    for row in sorted(day_rows, key=lambda r: r.punched_at):
        if row.kind in by_kind:
            by_kind[row.kind].append(row)
    entrada = by_kind["entrada"][0].punched_at if by_kind["entrada"] else None
    saida_intervalo = by_kind["saida_intervalo"][0].punched_at if by_kind["saida_intervalo"] else None
    retorno = by_kind["retorno"][0].punched_at if by_kind["retorno"] else None
    saida = by_kind["saida"][0].punched_at if by_kind["saida"] else None
    total_seconds = 0
    if entrada and saida_intervalo and saida_intervalo >= entrada:
        total_seconds += (saida_intervalo - entrada).total_seconds()
    if retorno and saida and saida >= retorno:
        total_seconds += (saida - retorno).total_seconds()
    # Jornada sem intervalo registrado: usa entrada -> saída apenas quando não há marcações de intervalo.
    if entrada and saida and not saida_intervalo and not retorno and saida >= entrada:
        total_seconds = (saida - entrada).total_seconds()
    return int(round(total_seconds / 60))

def _draw_pdf_footer(canvas, doc):
    canvas.saveState()
    canvas.setFont("Helvetica", 8)
    canvas.drawString(15 * mm, 8 * mm, "Portal RH - Espelho mensal de registros de ponto")
    canvas.drawRightString(282 * mm, 8 * mm, f"Página {doc.page}")
    canvas.restoreState()

def parse_date(v): return datetime.strptime(v, "%Y-%m-%d").date() if v else None
def parse_time(v):
    if not v:
        return None
    value = v.strip()
    for fmt in ("%H:%M:%S", "%H:%M"):
        try:
            return datetime.strptime(value, fmt).time()
        except ValueError:
            continue
    raise ValueError(f"Horário inválido: {value}")


def _approved_future_bank_minutes(employee_id, from_date=None):
    """Horas de banco aprovadas para uso futuro: reservadas, mas ainda não debitadas."""
    from_date = from_date or today_local()
    rows = Request.query.filter(
        Request.employee_id == employee_id,
        Request.request_type == "bank_use",
        Request.status == "approved",
        Request.request_date > from_date
    ).all()
    return sum(int(r.minutes or 0) for r in rows)

def _apply_due_bank_uses(employee):
    """Efetiva débitos aprovados cuja data de utilização chegou, uma única vez."""
    due = Request.query.filter(
        Request.employee_id == employee.id,
        Request.request_type == "bank_use",
        Request.status == "approved",
        Request.request_date <= today_local(),
        Request.bank_effect_applied == False
    ).order_by(Request.request_date.asc()).all()
    changed = False
    for item in due:
        employee.bank_minutes -= int(item.minutes or 0)
        item.bank_effect_applied = True
        item.bank_effect_applied_at = now_local()
        log_action("efetivou utilização de banco de horas", "request", item.id,
                   f"{employee.full_name}: débito de {int(item.minutes or 0)} min na data {item.request_date.strftime('%d/%m/%Y')}")
        changed = True
    if changed:
        db.session.commit()
    return changed

def _bank_summary(employee):
    _apply_due_bank_uses(employee)
    scheduled = _approved_future_bank_minutes(employee.id)
    return {
        "current": int(employee.bank_minutes or 0),
        "scheduled": scheduled,
        "available": int(employee.bank_minutes or 0) - scheduled,
    }

def allowed_file(name):
    return "." in name and name.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS

def save_upload(file):
    if not file or not file.filename or not allowed_file(file.filename):
        raise ValueError("Envie um arquivo PDF ou imagem válida.")
    original = secure_filename(file.filename)
    ext = original.rsplit('.',1)[1].lower()
    stored = f"{uuid.uuid4().hex}.{ext}"
    file.save(os.path.join(current_app.config["UPLOAD_FOLDER"], stored))
    return original, stored


PROFILE_PHOTO_EXTENSIONS = {"png", "jpg", "jpeg", "webp"}

def save_profile_photo(file):
    if not file or not file.filename:
        return None
    filename = secure_filename(file.filename)
    if "." not in filename:
        raise ValueError("A foto deve ser JPG, JPEG, PNG ou WEBP.")
    ext = filename.rsplit(".", 1)[1].lower()
    if ext not in PROFILE_PHOTO_EXTENSIONS:
        raise ValueError("A foto deve ser JPG, JPEG, PNG ou WEBP.")
    stored = f"profile_{uuid.uuid4().hex}.{ext}"
    file.save(os.path.join(current_app.config["UPLOAD_FOLDER"], stored))
    return stored

def visible_employees():
    if current_user.role == ROLE_ADMIN:
        return Employee.query.order_by(Employee.full_name).all()
    if current_user.role == ROLE_MANAGER and current_user.employee:
        ids = [current_user.employee.id] + [e.id for e in current_user.employee.team]
        return Employee.query.filter(Employee.id.in_(ids)).order_by(Employee.full_name).all()
    return [current_user.employee] if current_user.employee else []

@bp.route("/employees")
@login_required
def employees():
    return render_template("employees.html", employees=visible_employees())

@bp.route("/employees/new", methods=["GET", "POST"])
@login_required
@roles_required(ROLE_ADMIN)
def employee_new():
    managers = Employee.query.join(User).filter(User.role.in_([ROLE_ADMIN, ROLE_MANAGER])).order_by(Employee.full_name).all()
    if request.method == "POST":
        email = request.form["email"].strip().lower()
        cpf = request.form["cpf"].strip()
        if User.query.filter_by(email=email).first() or Employee.query.filter_by(cpf=cpf).first():
            flash("E-mail ou CPF já cadastrado.", "danger")
            return render_template("employee_form.html", managers=managers)
        initial_password = (request.form.get("password") or "").strip()
        point_pin = (request.form.get("point_pin") or "").strip()
        if len(initial_password) < 8:
            flash("Defina uma senha provisória de pelo menos 8 caracteres para o primeiro acesso.", "danger")
            return render_template("employee_form.html", managers=managers)
        if not (len(point_pin) == 6 and point_pin.isdigit()):
            flash("A senha de ponto deve conter exatamente 6 dígitos numéricos.", "danger")
            return render_template("employee_form.html", managers=managers)
        user = User(
            email=email,
            role=request.form.get("role", ROLE_EMPLOYEE),
            must_change_password=True
        )
        user.set_password(initial_password)
        db.session.add(user); db.session.flush()
        emp = Employee(
            user_id=user.id, full_name=request.form["full_name"], cpf=cpf,
            rg=request.form.get("rg"), birth_date=parse_date(request.form.get("birth_date")),
            phone=request.form.get("phone"), address=request.form.get("address"),
            registration=request.form.get("registration") or None, job_title=request.form["job_title"],
            department=request.form["department"], project=request.form.get("project") or "Administração",
            admission_date=parse_date(request.form["admission_date"]), contract_type=request.form.get("contract_type") or "CLT",
            weekly_hours=float(request.form.get("weekly_hours") or 44),
            standard_start=parse_time(request.form.get("standard_start")) or datetime.strptime("08:00", "%H:%M").time(),
            standard_end=parse_time(request.form.get("standard_end")) or datetime.strptime("17:00", "%H:%M").time(),
            manager_id=int(request.form["manager_id"]) if request.form.get("manager_id") else None,
        )
        emp.set_point_pin(point_pin)
        db.session.add(emp); db.session.flush(); log_action("criou colaborador", "employee", emp.id, emp.full_name); db.session.commit()
        flash("Colaborador cadastrado. No primeiro acesso, ele deverá substituir a senha provisória pela senha pessoal.", "success")
        return redirect(url_for("rh.employee_detail", employee_id=emp.id))
    return render_template("employee_form.html", managers=managers)


@bp.route("/employees/<int:employee_id>/edit", methods=["GET", "POST"])
@login_required
@roles_required(ROLE_ADMIN)
def employee_edit(employee_id):
    emp = db.get_or_404(Employee, employee_id)
    managers = (Employee.query.join(User)
                .filter(User.role.in_([ROLE_ADMIN, ROLE_MANAGER]), Employee.id != emp.id)
                .order_by(Employee.full_name).all())

    if request.method == "POST":
        email = (request.form.get("email") or "").strip().lower()
        cpf = (request.form.get("cpf") or "").strip()
        registration = (request.form.get("registration") or "").strip() or None

        duplicate_email = User.query.filter(User.email == email, User.id != emp.user_id).first()
        duplicate_cpf = Employee.query.filter(Employee.cpf == cpf, Employee.id != emp.id).first()
        duplicate_registration = None
        if registration:
            duplicate_registration = Employee.query.filter(
                Employee.registration == registration,
                Employee.id != emp.id
            ).first()

        if duplicate_email:
            flash("Já existe outro usuário cadastrado com esse e-mail.", "danger")
            return render_template("employee_edit.html", emp=emp, managers=managers)
        if duplicate_cpf:
            flash("Já existe outro colaborador cadastrado com esse CPF.", "danger")
            return render_template("employee_edit.html", emp=emp, managers=managers)
        if duplicate_registration:
            flash("Já existe outro colaborador cadastrado com essa matrícula.", "danger")
            return render_template("employee_edit.html", emp=emp, managers=managers)

        try:
            weekly_hours = float(request.form.get("weekly_hours") or emp.weekly_hours or 44)
            birth_date = parse_date(request.form.get("birth_date"))
            admission_date = parse_date(request.form.get("admission_date"))
            standard_start = parse_time(request.form.get("standard_start"))
            standard_end = parse_time(request.form.get("standard_end"))
        except (ValueError, TypeError) as exc:
            flash(f"Revise os dados de data, horário ou carga horária: {exc}", "danger")
            return render_template("employee_edit.html", emp=emp, managers=managers)

        old_summary = (
            f"nome={emp.full_name}; email={emp.user.email}; cpf={emp.cpf}; "
            f"cargo={emp.job_title}; setor={emp.department}; projeto={emp.project}"
        )

        emp.full_name = (request.form.get("full_name") or "").strip()
        emp.cpf = cpf
        emp.rg = (request.form.get("rg") or "").strip() or None
        emp.birth_date = birth_date
        emp.phone = (request.form.get("phone") or "").strip() or None
        emp.address = (request.form.get("address") or "").strip() or None
        emp.registration = registration
        emp.job_title = (request.form.get("job_title") or "").strip()
        emp.department = (request.form.get("department") or "").strip()
        emp.project = (request.form.get("project") or "").strip() or "Administração"
        emp.admission_date = admission_date
        emp.contract_type = (request.form.get("contract_type") or "").strip() or "CLT"
        emp.weekly_hours = weekly_hours
        emp.standard_start = standard_start
        emp.standard_end = standard_end
        emp.manager_id = int(request.form["manager_id"]) if request.form.get("manager_id") else None
        emp.is_active = request.form.get("is_active") == "1"

        emp.user.email = email
        role = request.form.get("role") or ROLE_EMPLOYEE
        if role not in {ROLE_EMPLOYEE, ROLE_MANAGER, ROLE_ADMIN}:
            role = ROLE_EMPLOYEE
        emp.user.role = role
        emp.user.active = emp.is_active

        photo = request.files.get("profile_photo")
        if photo and photo.filename:
            try:
                new_photo = save_profile_photo(photo)
            except ValueError as exc:
                flash(str(exc), "danger")
                return render_template("employee_edit.html", emp=emp, managers=managers)
            old_photo = emp.profile_photo
            emp.profile_photo = new_photo
            if old_photo:
                old_path = os.path.join(current_app.config["UPLOAD_FOLDER"], old_photo)
                try:
                    if os.path.isfile(old_path):
                        os.remove(old_path)
                except OSError:
                    pass

        new_summary = (
            f"nome={emp.full_name}; email={emp.user.email}; cpf={emp.cpf}; "
            f"cargo={emp.job_title}; setor={emp.department}; projeto={emp.project}"
        )
        log_action("alterou cadastro do colaborador", "employee", emp.id,
                   f"Antes: {old_summary}. Depois: {new_summary}.")
        db.session.commit()
        flash("Cadastro do colaborador atualizado com sucesso.", "success")
        return redirect(url_for("rh.employee_detail", employee_id=emp.id))

    return render_template("employee_edit.html", emp=emp, managers=managers)


@bp.route("/employees/<int:employee_id>/photo")
@login_required
def employee_photo(employee_id):
    emp = db.get_or_404(Employee, employee_id)
    if not can_manage_employee(emp):
        abort(403)
    if not emp.profile_photo:
        abort(404)
    return send_from_directory(
        current_app.config["UPLOAD_FOLDER"],
        emp.profile_photo,
        as_attachment=False
    )


@bp.route("/employees/<int:employee_id>")
@login_required
def employee_detail(employee_id):
    emp = db.get_or_404(Employee, employee_id)
    if not can_manage_employee(emp): abort(403)
    certs = MedicalCertificate.query.filter_by(employee_id=emp.id).order_by(MedicalCertificate.uploaded_at.desc()).all()
    reqs = Request.query.filter_by(employee_id=emp.id).order_by(Request.requested_at.desc()).limit(50).all()
    docs = Document.query.filter_by(employee_id=emp.id).order_by(Document.uploaded_at.desc()).all()
    payslips = Payslip.query.filter_by(employee_id=emp.id).order_by(Payslip.year.desc(), Payslip.month.desc()).all()
    clocks = TimeClock.query.filter_by(employee_id=emp.id).order_by(TimeClock.punched_at.desc()).limit(120).all()
    bank_adjustments = BankHourAdjustment.query.filter_by(employee_id=emp.id).order_by(BankHourAdjustment.created_at.desc()).limit(100).all()
    bank_summary = _bank_summary(emp)
    vacations = Vacation.query.filter_by(employee_id=emp.id).order_by(Vacation.start_date.desc()).all()
    vacation_schedules = VacationSchedule.query.filter_by(employee_id=emp.id).order_by(VacationSchedule.planned_start.asc()).all()
    vacation_summary = _vacation_entitlement(emp)
    return render_template("employee_detail.html", emp=emp, certs=certs, reqs=reqs, docs=docs, payslips=payslips, clocks=clocks, bank_adjustments=bank_adjustments, bank_summary=bank_summary, vacations=vacations, vacation_schedules=vacation_schedules, vacation_summary=vacation_summary, current_month=today_local().strftime("%Y-%m"))


@bp.route("/employees/<int:employee_id>/reset-password", methods=["POST"])
@login_required
@roles_required(ROLE_ADMIN)
def employee_reset_password(employee_id):
    emp = db.get_or_404(Employee, employee_id)
    temporary_password = (request.form.get("temporary_password") or "").strip()
    if len(temporary_password) < 8:
        flash("A senha provisória deve possuir pelo menos 8 caracteres.", "danger")
        return redirect(url_for("rh.employee_detail", employee_id=employee_id) + "#acesso")
    emp.user.set_password(temporary_password)
    emp.user.must_change_password = True
    emp.user.password_changed_at = None
    log_action("redefiniu senha provisória", "user", emp.user.id,
               f"Nova senha provisória criada para {emp.full_name}; troca obrigatória no próximo acesso.")
    db.session.commit()
    flash("Senha provisória redefinida. O colaborador deverá criar uma nova senha no próximo acesso.", "success")
    return redirect(url_for("rh.employee_detail", employee_id=employee_id) + "#acesso")



@bp.route("/employees/<int:employee_id>/reset-point-pin", methods=["POST"])
@login_required
@roles_required(ROLE_ADMIN)
def employee_reset_point_pin(employee_id):
    emp = db.get_or_404(Employee, employee_id)
    pin = (request.form.get("point_pin") or "").strip()
    if not (len(pin) == 6 and pin.isdigit()):
        flash("A senha de ponto deve conter exatamente 6 dígitos numéricos.", "danger")
        return redirect(url_for("rh.employee_detail", employee_id=employee_id) + "#acesso")
    emp.set_point_pin(pin)
    log_action("redefiniu senha de ponto", "employee", emp.id,
               f"Senha de ponto de 6 dígitos redefinida para {emp.full_name}.")
    db.session.commit()
    flash("Senha de ponto redefinida com sucesso.", "success")
    return redirect(url_for("rh.employee_detail", employee_id=employee_id) + "#acesso")


@bp.route("/employees/<int:employee_id>/bank-adjustment", methods=["POST"])
@login_required
@roles_required(ROLE_ADMIN)
def employee_bank_adjustment(employee_id):
    emp = db.get_or_404(Employee, employee_id)
    operation = request.form.get("operation", "credit")
    hours = max(int(request.form.get("hours") or 0), 0)
    minutes_part = max(min(int(request.form.get("minutes") or 0), 59), 0)
    total = hours * 60 + minutes_part
    reason = (request.form.get("reason") or "").strip()
    if total <= 0 or not reason:
        flash("Informe a quantidade de horas/minutos e a justificativa do ajuste.", "danger")
        return redirect(url_for("rh.employee_detail", employee_id=employee_id) + "#banco-horas")
    signed = total if operation == "credit" else -total
    old_balance = emp.bank_minutes
    emp.bank_minutes += signed
    movement = BankHourAdjustment(employee_id=emp.id, minutes=signed, reason=reason, created_by=current_user.id)
    db.session.add(movement); db.session.flush()
    log_action("ajustou banco de horas", "bank_hour_adjustment", movement.id,
               f"{emp.full_name}: {old_balance} min -> {emp.bank_minutes} min; ajuste {signed:+d} min; motivo: {reason}")
    db.session.commit()
    flash("Banco de horas ajustado com sucesso.", "success")
    return redirect(url_for("rh.employee_detail", employee_id=employee_id) + "#banco-horas")


@bp.route("/employees/<int:employee_id>/time-clock/add", methods=["POST"])
@login_required
@roles_required(ROLE_ADMIN)
def employee_time_clock_add(employee_id):
    emp = db.get_or_404(Employee, employee_id)
    punch_date = parse_date(request.form.get("date"))
    punch_time = parse_time(request.form.get("time"))
    kind = request.form.get("kind")
    reason = (request.form.get("reason") or "").strip()
    allowed_kinds = {"entrada", "saida_intervalo", "retorno", "saida"}
    if not punch_date or not punch_time or kind not in allowed_kinds or not reason:
        flash("Preencha data, horário, tipo e justificativa do ajuste de ponto.", "danger")
        return redirect(url_for("rh.employee_detail", employee_id=employee_id) + "#controle-ponto")
    dt = datetime.combine(punch_date, punch_time)
    row = TimeClock(employee_id=emp.id, punched_at=dt, kind=kind, source="ajuste_rh",
                    ip_address=request.headers.get("X-Forwarded-For", request.remote_addr))
    db.session.add(row); db.session.flush()
    log_action("incluiu marcação de ponto pelo RH", "time_clock", row.id,
               f"{emp.full_name}; {dt.strftime('%d/%m/%Y %H:%M:%S')}; {kind}; motivo: {reason}")
    db.session.commit()
    flash("Marcação de ponto incluída com sucesso.", "success")
    return redirect(url_for("rh.employee_detail", employee_id=employee_id) + "#controle-ponto")


@bp.route("/time-clock/<int:clock_id>/edit", methods=["POST"])
@login_required
@roles_required(ROLE_ADMIN)
def time_clock_edit(clock_id):
    row = db.get_or_404(TimeClock, clock_id)
    punch_date = parse_date(request.form.get("date"))
    punch_time = parse_time(request.form.get("time"))
    kind = request.form.get("kind")
    reason = (request.form.get("reason") or "").strip()
    allowed_kinds = {"entrada", "saida_intervalo", "retorno", "saida"}
    if not punch_date or not punch_time or kind not in allowed_kinds or not reason:
        flash("Preencha data, horário, tipo e justificativa para alterar a marcação.", "danger")
        return redirect(url_for("rh.employee_detail", employee_id=row.employee_id) + "#controle-ponto")
    old = f"{row.punched_at.strftime('%d/%m/%Y %H:%M:%S')} {row.kind} origem={row.source}"
    row.punched_at = datetime.combine(punch_date, punch_time)
    row.kind = kind
    row.source = "ajuste_rh"
    new = f"{row.punched_at.strftime('%d/%m/%Y %H:%M:%S')} {row.kind}"
    log_action("alterou marcação de ponto pelo RH", "time_clock", row.id, f"antes: {old}; depois: {new}; motivo: {reason}")
    db.session.commit()
    flash("Marcação alterada com sucesso.", "success")
    return redirect(url_for("rh.employee_detail", employee_id=row.employee_id) + "#controle-ponto")


@bp.route("/time-clock/<int:clock_id>/delete", methods=["POST"])
@login_required
@roles_required(ROLE_ADMIN)
def time_clock_delete(clock_id):
    row = db.get_or_404(TimeClock, clock_id)
    employee_id = row.employee_id
    reason = (request.form.get("reason") or "").strip()
    if not reason:
        flash("Informe a justificativa para excluir a marcação duplicada/incorreta.", "danger")
        return redirect(url_for("rh.employee_detail", employee_id=employee_id) + "#controle-ponto")
    details = f"{row.employee.full_name}; registro #{row.id}; {row.punched_at.strftime('%d/%m/%Y %H:%M:%S')}; {row.kind}; origem={row.source}; motivo: {reason}"
    log_action("excluiu marcação de ponto pelo RH", "time_clock", row.id, details)
    db.session.delete(row)
    db.session.commit()
    flash("Marcação removida. A exclusão permanece registrada na Auditoria.", "success")
    return redirect(url_for("rh.employee_detail", employee_id=employee_id) + "#controle-ponto")


@bp.route("/clock", methods=["GET", "POST"])
@login_required
def clock():
    emp = current_user.employee
    if not emp: abort(403)
    if request.method == "POST":
        point_pin = (request.form.get("point_pin") or "").strip()
        if not emp.point_pin_hash:
            flash("Sua senha de ponto ainda não foi cadastrada. Procure o RH.", "danger")
            return redirect(url_for("rh.clock"))
        if not (len(point_pin) == 6 and point_pin.isdigit()) or not emp.check_point_pin(point_pin):
            log_action("tentativa inválida de registro de ponto", "employee", emp.id, "PIN de ponto inválido.")
            db.session.commit()
            flash("Senha de ponto inválida. O registro não foi realizado.", "danger")
            return redirect(url_for("rh.clock"))

        kinds = ["entrada", "saida_intervalo", "retorno", "saida"]
        today_rows = TimeClock.query.filter(TimeClock.employee_id==emp.id, db.func.date(TimeClock.punched_at) == today_local()).order_by(TimeClock.punched_at).all()
        kind = kinds[min(len(today_rows), 3)]
        row = TimeClock(employee_id=emp.id, kind=kind, ip_address=request.headers.get("X-Forwarded-For", request.remote_addr))
        db.session.add(row); db.session.flush(); log_action("registrou ponto", "time_clock", row.id, kind); db.session.commit()
        flash(f"Ponto registrado: {kind.replace('_',' ')} às {row.punched_at.strftime('%H:%M:%S')}.", "success")
        return redirect(url_for("rh.clock"))
    rows = TimeClock.query.filter(TimeClock.employee_id==emp.id, db.func.date(TimeClock.punched_at) == today_local()).order_by(TimeClock.punched_at).all()
    return render_template("clock.html", rows=rows)

@bp.route("/certificates", methods=["GET", "POST"])
@login_required
def certificates():
    emp = current_user.employee
    if not emp: abort(403)
    if request.method == "POST":
        try: original, stored = save_upload(request.files.get("file"))
        except ValueError as e:
            flash(str(e), "danger"); return redirect(url_for("rh.certificates"))
        cert = MedicalCertificate(employee_id=emp.id, start_date=parse_date(request.form["start_date"]), days=int(request.form.get("days") or 1), note=request.form.get("note"), original_name=original, stored_name=stored)
        db.session.add(cert); db.session.flush(); log_action("enviou atestado", "medical_certificate", cert.id, original); db.session.commit()
        flash("Atestado enviado ao RH.", "success"); return redirect(url_for("rh.certificates"))
    rows = MedicalCertificate.query.filter_by(employee_id=emp.id).order_by(MedicalCertificate.uploaded_at.desc()).all()
    return render_template("certificates.html", rows=rows)


def _certificate_cover_pdf(cert):
    """Gera uma folha de identificação antes de cada atestado no PDF em lote."""
    output = BytesIO()
    doc = SimpleDocTemplate(
        output,
        pagesize=A4,
        leftMargin=18 * mm,
        rightMargin=18 * mm,
        topMargin=18 * mm,
        bottomMargin=18 * mm,
        title=f"Atestado - {cert.employee.full_name}",
        author="Portal RH",
    )
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "CertificateBatchTitle",
        parent=styles["Title"],
        fontName="Helvetica-Bold",
        fontSize=17,
        leading=21,
        alignment=TA_CENTER,
        spaceAfter=8 * mm,
    )
    normal = ParagraphStyle(
        "CertificateBatchNormal",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=10,
        leading=14,
    )
    data = [
        [Paragraph("<b>Colaborador</b>", normal), Paragraph(_pdf_text(cert.employee.full_name), normal)],
        [Paragraph("<b>Cargo</b>", normal), Paragraph(_pdf_text(cert.employee.job_title), normal)],
        [Paragraph("<b>Projeto/Unidade</b>", normal), Paragraph(_pdf_text(cert.employee.project), normal)],
        [Paragraph("<b>Data inicial do atestado</b>", normal), Paragraph(cert.start_date.strftime("%d/%m/%Y"), normal)],
        [Paragraph("<b>Dias</b>", normal), Paragraph(str(cert.days), normal)],
        [Paragraph("<b>Data de envio ao Portal</b>", normal), Paragraph(cert.uploaded_at.strftime("%d/%m/%Y %H:%M"), normal)],
        [Paragraph("<b>Status</b>", normal), Paragraph(_pdf_text(cert.status.title()), normal)],
        [Paragraph("<b>Arquivo original</b>", normal), Paragraph(_pdf_text(cert.original_name), normal)],
        [Paragraph("<b>Observação</b>", normal), Paragraph(_pdf_text(cert.note or "—"), normal)],
    ]
    table = Table(data, colWidths=[52 * mm, 118 * mm], hAlign="LEFT")
    table.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#D9E2E8")),
        ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#F2F5F7")),
        ("LEFTPADDING", (0, 0), (-1, -1), 7),
        ("RIGHTPADDING", (0, 0), (-1, -1), 7),
        ("TOPPADDING", (0, 0), (-1, -1), 7),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
    ]))
    story = [
        Paragraph("Atestado Médico — Documento Anexado", title_style),
        Paragraph(
            "Folha de identificação gerada automaticamente pelo Portal RH. "
            "O documento original anexado pelo colaborador aparece nas páginas seguintes.",
            normal,
        ),
        Spacer(1, 7 * mm),
        table,
    ]
    doc.build(story)
    output.seek(0)
    return output


def _image_file_to_pdf(path):
    """Converte JPG/PNG/WEBP em PDF para permitir impressão em lote."""
    output = BytesIO()
    with PILImage.open(path) as image:
        if getattr(image, "is_animated", False):
            image.seek(0)
        if image.mode not in ("RGB", "L"):
            background = PILImage.new("RGB", image.size, "white")
            if "A" in image.getbands():
                background.paste(image, mask=image.getchannel("A"))
            else:
                background.paste(image)
            image = background
        elif image.mode == "L":
            image = image.convert("RGB")
        else:
            image = image.copy()
        image.save(output, format="PDF", resolution=150.0)
    output.seek(0)
    return output


@bp.route("/certificates/print-batch.pdf")
@login_required
@roles_required(ROLE_ADMIN)
def certificates_print_batch():
    start_raw = (request.args.get("start_date") or "").strip()
    end_raw = (request.args.get("end_date") or "").strip()

    try:
        start = parse_date(start_raw)
        end = parse_date(end_raw)
    except (ValueError, TypeError):
        start = end = None

    if not start or not end:
        flash("Informe a data inicial e final para imprimir os atestados.", "danger")
        return redirect(url_for("rh.certificates_manage"))

    if end < start:
        flash("A data final não pode ser anterior à data inicial.", "danger")
        return redirect(url_for("rh.certificates_manage", start_date=start_raw, end_date=end_raw))

    if (end - start).days > 29:
        flash("O intervalo para impressão deve ter no máximo 30 dias corridos.", "danger")
        return redirect(url_for("rh.certificates_manage", start_date=start_raw, end_date=end_raw))

    # O pedido é pelos documentos ANEXADOS no período; portanto usamos uploaded_at.
    rows = (MedicalCertificate.query
            .filter(
                func.date(MedicalCertificate.uploaded_at) >= start,
                func.date(MedicalCertificate.uploaded_at) <= end,
            )
            .order_by(MedicalCertificate.uploaded_at.asc(), MedicalCertificate.id.asc())
            .all())

    if not rows:
        flash("Nenhum atestado foi anexado ao Portal nesse intervalo.", "danger")
        return redirect(url_for("rh.certificates_manage", start_date=start_raw, end_date=end_raw))

    writer = PdfWriter()
    included = 0
    skipped = []

    for cert in rows:
        # Sempre inclui uma capa de identificação do documento.
        cover = _certificate_cover_pdf(cert)
        cover_reader = PdfReader(cover)
        for page in cover_reader.pages:
            writer.add_page(page)

        file_path = os.path.join(current_app.config["UPLOAD_FOLDER"], cert.stored_name)
        if not os.path.isfile(file_path):
            skipped.append(f"{cert.employee.full_name}: arquivo não localizado")
            continue

        ext = cert.stored_name.rsplit(".", 1)[-1].lower() if "." in cert.stored_name else ""
        try:
            if ext == "pdf":
                source = PdfReader(file_path)
                for page in source.pages:
                    writer.add_page(page)
            elif ext in {"jpg", "jpeg", "png", "webp"}:
                image_pdf = _image_file_to_pdf(file_path)
                source = PdfReader(image_pdf)
                for page in source.pages:
                    writer.add_page(page)
            else:
                skipped.append(f"{cert.employee.full_name}: formato não suportado")
                continue
            included += 1
        except Exception:
            skipped.append(f"{cert.employee.full_name}: não foi possível processar o arquivo")

    if included == 0:
        flash("Os atestados foram encontrados, mas nenhum arquivo pôde ser processado para impressão.", "danger")
        return redirect(url_for("rh.certificates_manage", start_date=start_raw, end_date=end_raw))

    output = BytesIO()
    writer.write(output)
    output.seek(0)

    details = (
        f"Período de envio {start.strftime('%d/%m/%Y')} a {end.strftime('%d/%m/%Y')}; "
        f"{included} arquivo(s) incluído(s)"
    )
    if skipped:
        details += f"; {len(skipped)} arquivo(s) com falha"
    log_action("gerou impressão em lote de atestados", "medical_certificate", None, details)
    db.session.commit()

    filename = f"atestados_{start.strftime('%Y-%m-%d')}_a_{end.strftime('%Y-%m-%d')}.pdf"
    return send_file(
        output,
        mimetype="application/pdf",
        as_attachment=False,
        download_name=filename,
    )


@bp.route("/certificates/manage")
@login_required
@roles_required(ROLE_ADMIN)
def certificates_manage():
    q = MedicalCertificate.query
    employee_id = request.args.get("employee_id", type=int)
    status = request.args.get("status", "").strip()
    start_date = request.args.get("start_date", "").strip()
    end_date = request.args.get("end_date", "").strip()

    if employee_id:
        q = q.filter(MedicalCertificate.employee_id == employee_id)
    if status:
        q = q.filter(MedicalCertificate.status == status)
    if start_date:
        q = q.filter(MedicalCertificate.start_date >= parse_date(start_date))
    if end_date:
        q = q.filter(MedicalCertificate.start_date <= parse_date(end_date))

    rows = q.order_by(MedicalCertificate.uploaded_at.desc()).all()
    employees = Employee.query.order_by(Employee.full_name).all()
    local_today = today_local()
    batch_end_date = local_today.isoformat()
    batch_start_date = (local_today - timedelta(days=29)).isoformat()
    return render_template(
        "certificates_manage.html",
        rows=rows,
        employees=employees,
        selected_employee=employee_id,
        selected_status=status,
        start_date=start_date,
        end_date=end_date,
        batch_start_date=batch_start_date,
        batch_end_date=batch_end_date,
    )


@bp.route("/certificates/<int:certificate_id>/status", methods=["POST"])
@login_required
@roles_required(ROLE_ADMIN)
def certificate_status(certificate_id):
    cert = db.get_or_404(MedicalCertificate, certificate_id)
    new_status = request.form.get("status", "")
    allowed = {"recebido", "conferido", "arquivado", "devolvido"}
    if new_status not in allowed:
        abort(400)
    old_status = cert.status
    cert.status = new_status
    log_action(
        "alterou status do atestado",
        "medical_certificate",
        cert.id,
        f"{old_status} -> {new_status}",
    )
    db.session.commit()
    flash("Status do atestado atualizado.", "success")
    return redirect(request.referrer or url_for("rh.certificates_manage"))


@bp.route("/requests", methods=["GET", "POST"])
@login_required
def requests_page():
    emp = current_user.employee
    if not emp: abort(403)
    if request.method == "POST":
        rtype = request.form["request_type"]
        start = parse_time(request.form.get("start_time")); end = parse_time(request.form.get("end_time"))
        minutes = int(request.form.get("minutes") or 0)
        if not minutes and start and end:
            a = datetime.combine(today_local(), start); b = datetime.combine(today_local(), end); minutes = int((b-a).total_seconds()/60)
        item = Request(employee_id=emp.id, request_type=rtype, request_date=parse_date(request.form["request_date"]), start_time=start, end_time=end, minutes=max(minutes,0), reason=request.form["reason"], target_clock_kind=request.form.get("target_clock_kind") or None)
        db.session.add(item); db.session.flush(); log_action("criou solicitação", "request", item.id, rtype); db.session.commit()
        flash("Solicitação enviada para aprovação.", "success"); return redirect(url_for("rh.requests_page"))
    rows = Request.query.filter_by(employee_id=emp.id).order_by(Request.requested_at.desc()).all()
    bank_summary = _bank_summary(emp)
    return render_template("requests.html", rows=rows, bank_summary=bank_summary)

@bp.route("/approvals")
@login_required
@roles_required(ROLE_ADMIN, ROLE_MANAGER)
def approvals():
    q = Request.query.filter_by(status="pending")
    if current_user.role == ROLE_MANAGER:
        ids = [e.id for e in current_user.employee.team]
        q = q.filter(Request.employee_id.in_(ids))
    return render_template("approvals.html", rows=q.order_by(Request.requested_at).all())

@bp.route("/requests/<int:request_id>/decision", methods=["POST"])
@login_required
@roles_required(ROLE_ADMIN, ROLE_MANAGER)
def request_decision(request_id):
    item = db.get_or_404(Request, request_id)
    if current_user.role == ROLE_MANAGER and item.employee.manager_id != current_user.employee.id: abort(403)
    decision = request.form["decision"]
    if decision not in ["approved", "rejected"]: abort(400)
    item.status=decision; item.decided_at=now_local(); item.decided_by=current_user.id; item.decision_note=request.form.get("decision_note")
    if decision == "approved":
        if item.request_type == "bank_use":
            if item.request_date <= today_local():
                item.employee.bank_minutes -= int(item.minutes or 0)
                item.bank_effect_applied = True
                item.bank_effect_applied_at = now_local()
            else:
                # Solicitação futura: aprovada e reservada, sem reduzir o saldo realizado ainda.
                item.bank_effect_applied = False
        elif item.request_type == "overtime": item.employee.bank_minutes += item.minutes
        elif item.request_type == "clock_adjustment" and item.start_time:
            dt = datetime.combine(item.request_date, item.start_time)
            tc = TimeClock(employee_id=item.employee_id, punched_at=dt, kind=item.target_clock_kind or "ajuste", source="ajuste_aprovado")
            db.session.add(tc)
    log_action(f"{decision} solicitação", "request", item.id, item.request_type); db.session.commit()
    flash("Decisão registrada.", "success"); return redirect(url_for("rh.approvals"))


@bp.route("/payslips")
@login_required
def payslips():
    if current_user.role == ROLE_ADMIN:
        return redirect(url_for("rh.payslips_manage"))

    emp = current_user.employee
    if not emp:
        abort(403)

    rows = (Payslip.query
            .filter(Payslip.employee_id == emp.id)
            .order_by(Payslip.year.desc(), Payslip.month.desc(), Payslip.uploaded_at.desc())
            .all())

    return render_template(
        "payslips.html",
        rows=rows,
        emp=emp,
    )


@bp.route("/payslips/manage")
@login_required
@roles_required(ROLE_ADMIN)
def payslips_manage():
    employees = Employee.query.filter_by(is_active=True).order_by(Employee.full_name).all()
    rows = (Payslip.query
            .order_by(Payslip.year.desc(), Payslip.month.desc(), Payslip.uploaded_at.desc())
            .limit(300).all())
    return render_template(
        "payslips_manage.html",
        employees=employees,
        rows=rows,
        current_competence=today_local().strftime("%Y-%m"),
    )


@bp.route("/payslips/upload-batch", methods=["POST"])
@login_required
@roles_required(ROLE_ADMIN)
def payslips_upload_batch():
    try:
        year, month = _parse_competence(request.form.get("competence"))
    except ValueError as exc:
        flash(str(exc), "danger")
        return redirect(url_for("rh.payslips_manage"))

    file = request.files.get("file")
    if not file or not file.filename:
        flash("Selecione o PDF consolidado dos holerites.", "danger")
        return redirect(url_for("rh.payslips_manage"))

    if "." not in file.filename or file.filename.rsplit(".", 1)[1].lower() != "pdf":
        flash("O arquivo consolidado precisa estar em PDF.", "danger")
        return redirect(url_for("rh.payslips_manage"))

    employees = Employee.query.filter_by(is_active=True).order_by(Employee.full_name).all()

    try:
        groups, unmatched = _split_payslip_pdf_by_employee(file, employees)
    except ValueError as exc:
        flash(str(exc), "danger")
        return redirect(url_for("rh.payslips_manage"))

    created = []
    skipped_without_access = []
    for group in groups.values():
        emp = group["employee"]

        # O holerite precisa estar associado a um cadastro com acesso ao Portal.
        if not emp.user:
            skipped_without_access.append(emp.full_name)
            continue

        item = _save_employee_payslip_pages(
            emp=emp,
            year=year,
            month=month,
            pages=group["pages"],
            original_name=file.filename,
            matched_by="automatic_pdf_page",
        )
        created.append((emp, item, group["page_numbers"]))
        log_action(
            "separou holerite de PDF consolidado",
            "payslip",
            item.id,
            (
                f"{emp.full_name}; competência {month:02d}/{year}; "
                f"página(s) {', '.join(map(str, group['page_numbers']))}"
            ),
        )

    db.session.commit()

    if created:
        flash(
            f"{len(created)} colaborador(es) receberam holerite da competência {month:02d}/{year}.",
            "success",
        )
    else:
        flash(
            "Nenhuma página pôde ser associada automaticamente a um colaborador.",
            "danger",
        )

    if skipped_without_access:
        flash(
            f"{len(skipped_without_access)} colaborador(es) foram identificados no PDF, "
            "mas não possuem usuário de acesso vinculado ao Portal RH: "
            + ", ".join(skipped_without_access[:8]),
            "warning",
        )

    if unmatched:
        reason_counts = {}
        for row in unmatched:
            reason_counts[row["reason"]] = reason_counts.get(row["reason"], 0) + 1

        details = []
        if reason_counts.get("sem_texto"):
            details.append(f"{reason_counts['sem_texto']} sem texto pesquisável")
        if reason_counts.get("nao_encontrado"):
            details.append(f"{reason_counts['nao_encontrado']} sem nome cadastrado identificado")
        if reason_counts.get("ambiguo"):
            details.append(f"{reason_counts['ambiguo']} com identificação ambígua")

        page_list = ", ".join(str(row["page"]) for row in unmatched[:20])
        if len(unmatched) > 20:
            page_list += "..."

        flash(
            f"{len(unmatched)} página(s) não foram distribuídas automaticamente "
            f"(páginas: {page_list}). " + "; ".join(details) + ".",
            "warning",
        )

    return redirect(url_for("rh.payslips_manage"))


@bp.route("/payslips/upload-manual", methods=["POST"])
@login_required
@roles_required(ROLE_ADMIN)
def payslips_upload_manual():
    emp = db.get_or_404(Employee, request.form.get("employee_id", type=int))
    try:
        year, month = _parse_competence(request.form.get("competence"))
        item = _upsert_payslip(emp, year, month, request.files.get("file"), "manual")
    except ValueError as exc:
        flash(str(exc), "danger")
        return redirect(url_for("rh.payslips_manage"))

    log_action(
        "anexou holerite manualmente",
        "payslip",
        item.id,
        f"{emp.full_name}; competência {month:02d}/{year}; arquivo {item.original_name}"
    )
    db.session.commit()
    flash(f"Holerite de {emp.full_name} — {month:02d}/{year} — salvo com sucesso.", "success")
    return redirect(url_for("rh.payslips_manage"))


@bp.route("/payslips/<int:payslip_id>/delete", methods=["POST"])
@login_required
@roles_required(ROLE_ADMIN)
def payslip_delete(payslip_id):
    item = db.get_or_404(Payslip, payslip_id)
    stored = item.stored_name
    description = f"{item.employee.full_name}; competência {item.month:02d}/{item.year}"
    db.session.delete(item)
    log_action("removeu holerite", "payslip", payslip_id, description)
    db.session.commit()
    path = os.path.join(current_app.config["UPLOAD_FOLDER"], stored)
    try:
        if os.path.isfile(path):
            os.remove(path)
    except OSError:
        pass
    flash("Holerite removido.", "success")
    return redirect(url_for("rh.payslips_manage"))


@bp.route("/documents/<int:employee_id>", methods=["POST"])
@login_required
@roles_required(ROLE_ADMIN)
def document_upload(employee_id):
    emp = db.get_or_404(Employee, employee_id)
    try: original, stored = save_upload(request.files.get("file"))
    except ValueError as e:
        flash(str(e), "danger"); return redirect(url_for("rh.employee_detail", employee_id=employee_id))
    doc = Document(employee_id=emp.id, category=request.form.get("category") or "Outros", title=request.form.get("title") or original, original_name=original, stored_name=stored)
    db.session.add(doc); db.session.flush(); log_action("anexou documento", "document", doc.id, original); db.session.commit()
    flash("Documento anexado.", "success"); return redirect(url_for("rh.employee_detail", employee_id=employee_id))

@bp.route("/files/<string:kind>/<int:item_id>")
@login_required
def file_download(kind, item_id):
    if kind == "certificate":
        item = db.get_or_404(MedicalCertificate, item_id); emp=item.employee
        # Gestores não recebem acesso ao conteúdo médico; apenas RH e titular.
        if current_user.role != ROLE_ADMIN and (not current_user.employee or current_user.employee.id != emp.id): abort(403)
    elif kind == "document":
        item = db.get_or_404(Document, item_id); emp=item.employee
        if current_user.role != ROLE_ADMIN and (not current_user.employee or current_user.employee.id != emp.id): abort(403)
    elif kind == "payslip":
        item = db.get_or_404(Payslip, item_id); emp=item.employee
        # Holerite contém informação remuneratória: acesso apenas do RH e do titular.
        if current_user.role != ROLE_ADMIN and (not current_user.employee or current_user.employee.id != emp.id):
            abort(403)
        if current_user.role != ROLE_ADMIN and not item.employee_viewed_at:
            item.employee_viewed_at = now_local()
            log_action(
                "visualizou holerite",
                "payslip",
                item.id,
                f"{emp.full_name}; competência {item.month:02d}/{item.year}"
            )
            db.session.commit()
    else: abort(404)
    return send_from_directory(current_app.config["UPLOAD_FOLDER"], item.stored_name, as_attachment=False, download_name=item.original_name)



@bp.route("/employees/<int:employee_id>/vacations", methods=["POST"])
@login_required
@roles_required(ROLE_ADMIN)
def employee_vacation_add(employee_id):
    emp = db.get_or_404(Employee, employee_id)
    start = parse_date(request.form.get("start_date"))
    days = int(request.form.get("days") or 0)
    note = (request.form.get("note") or "").strip() or None
    if not start or days <= 0:
        flash("Informe a data de início e a quantidade de dias das férias.", "danger")
        return redirect(url_for("rh.employee_detail", employee_id=employee_id) + "#ferias")
    item = Vacation(employee_id=emp.id, start_date=start, days=days, note=note, created_by=current_user.id)
    db.session.add(item); db.session.flush()
    log_action("registrou férias", "vacation", item.id, f"{emp.full_name}; {start.strftime('%d/%m/%Y')}; {days} dias")
    db.session.commit()
    flash("Férias registradas com sucesso.", "success")
    return redirect(url_for("rh.employee_detail", employee_id=employee_id) + "#ferias")


@bp.route("/employees/<int:employee_id>/vacation-schedule", methods=["POST"])
@login_required
@roles_required(ROLE_ADMIN)
def employee_vacation_schedule_add(employee_id):
    emp = db.get_or_404(Employee, employee_id)
    planned_start = parse_date(request.form.get("planned_start"))
    planned_return = parse_date(request.form.get("planned_return"))
    days = int(request.form.get("days") or 0)
    note = (request.form.get("note") or "").strip() or None
    if not planned_start or days <= 0 or days > 30:
        flash("Informe uma data válida e entre 1 e 30 dias para a programação de férias.", "danger")
        return redirect(url_for("rh.employee_detail", employee_id=employee_id) + "#ferias")
    if not planned_return:
        planned_return = planned_start + timedelta(days=days)
    if planned_return <= planned_start:
        flash("A data prevista de retorno deve ser posterior ao início das férias.", "danger")
        return redirect(url_for("rh.employee_detail", employee_id=employee_id) + "#ferias")
    item = VacationSchedule(
        employee_id=emp.id,
        planned_start=planned_start,
        planned_return=planned_return,
        days=days,
        note=note,
        created_by=current_user.id,
        status="planned",
    )
    db.session.add(item); db.session.flush()
    log_action("programou férias", "vacation_schedule", item.id,
               f"{emp.full_name}; início {planned_start.strftime('%d/%m/%Y')}; retorno {planned_return.strftime('%d/%m/%Y')}; {days} dias")
    db.session.commit()
    flash("Previsão de férias registrada. Os dias ainda não foram descontados como férias realizadas.", "success")
    return redirect(url_for("rh.employee_detail", employee_id=employee_id) + "#ferias")

@bp.route("/vacation-schedules/<int:schedule_id>/complete", methods=["POST"])
@login_required
@roles_required(ROLE_ADMIN)
def vacation_schedule_complete(schedule_id):
    item = db.get_or_404(VacationSchedule, schedule_id)
    if item.status != "planned":
        flash("Essa programação já foi finalizada ou cancelada.", "danger")
        return redirect(url_for("rh.employee_detail", employee_id=item.employee_id) + "#ferias")
    vacation = Vacation(
        employee_id=item.employee_id,
        start_date=item.planned_start,
        days=item.days,
        note=item.note or "Férias realizadas conforme programação",
        created_by=current_user.id,
    )
    db.session.add(vacation)
    item.status = "completed"
    item.completed_at = now_local()
    log_action("confirmou férias programadas como realizadas", "vacation_schedule", item.id,
               f"{item.employee.full_name}; {item.planned_start.strftime('%d/%m/%Y')}; {item.days} dias")
    db.session.commit()
    flash("Férias marcadas como realizadas e descontadas do saldo disponível.", "success")
    return redirect(url_for("rh.employee_detail", employee_id=item.employee_id) + "#ferias")

@bp.route("/vacation-schedules/<int:schedule_id>/cancel", methods=["POST"])
@login_required
@roles_required(ROLE_ADMIN)
def vacation_schedule_cancel(schedule_id):
    item = db.get_or_404(VacationSchedule, schedule_id)
    if item.status == "planned":
        item.status = "cancelled"
        log_action("cancelou programação de férias", "vacation_schedule", item.id,
                   f"{item.employee.full_name}; previsão {item.planned_start.strftime('%d/%m/%Y')}")
        db.session.commit()
        flash("Programação de férias cancelada.", "success")
    return redirect(url_for("rh.employee_detail", employee_id=item.employee_id) + "#ferias")

@bp.route("/bank-statement")
@login_required
@roles_required(ROLE_ADMIN)
def bank_statement():
    employee_id = request.args.get("employee_id", type=int)
    employees = Employee.query.order_by(Employee.full_name).all()
    emp = db.session.get(Employee, employee_id) if employee_id else None
    movements = []
    if emp:
        adjustments = BankHourAdjustment.query.filter_by(employee_id=emp.id).all()
        requests_rows = Request.query.filter(
            Request.employee_id == emp.id, Request.status == "approved",
            Request.request_type.in_(["overtime","bank_use"])
        ).all()
        for a in adjustments:
            movements.append({"date": a.created_at, "label": a.reason, "minutes": int(a.minutes or 0), "source": "Ajuste RH"})
        for q in requests_rows:
            sign = 1 if q.request_type == "overtime" else -1
            movements.append({"date": datetime.combine(q.request_date, q.start_time or datetime.min.time()),
                              "label": "Hora extra aprovada" if sign > 0 else "Utilização de banco",
                              "minutes": sign * int(q.minutes or 0), "source": "Solicitação aprovada"})
        movements.sort(key=lambda x:x["date"])
        running = 0
        for x in movements:
            running += x["minutes"]; x["running"] = running
    return render_template("bank_statement.html", employees=employees, emp=emp, movements=movements)

@bp.route("/time-closing")
@login_required
@roles_required(ROLE_ADMIN)
def time_closing():
    month_value = request.args.get("month") or today_local().strftime("%Y-%m")
    try: year, month = map(int, month_value.split("-"))
    except Exception: year, month = today_local().year, today_local().month
    employees = Employee.query.filter_by(is_active=True).order_by(Employee.full_name).all()
    summaries=[]
    for emp in employees:
        s=_month_clock_summary(emp,year,month)
        closure=TimePeriodClosure.query.filter_by(employee_id=emp.id,year=year,month=month,status="closed").first()
        ack=TimeReportAcknowledgement.query.filter_by(employee_id=emp.id,year=year,month=month).first()
        signature_log = None
        if ack:
            signature_log = (AuditLog.query
                .filter_by(entity="time_report_acknowledgement", entity_id=ack.id)
                .order_by(AuditLog.created_at.desc())
                .first())
        summaries.append({
            "emp": emp,
            "summary": s,
            "closure": closure,
            "ack": ack,
            "signature_log": signature_log,
        })
    return render_template("time_closing.html", rows=summaries, month_value=month_value, year=year, month=month)

@bp.route("/employees/<int:employee_id>/time-closing", methods=["POST"])
@login_required
@roles_required(ROLE_ADMIN)
def employee_time_close(employee_id):
    emp=db.get_or_404(Employee,employee_id)
    year=int(request.form["year"]); month=int(request.form["month"])
    s=_month_clock_summary(emp,year,month)
    if s["incomplete"] and request.form.get("force")!="1":
        flash(f"Não foi possível fechar: existem {s['incomplete']} dia(s) com ponto ausente/incompleto. Revise ou use o fechamento justificado.", "danger")
        return redirect(url_for("rh.time_closing",month=f"{year:04d}-{month:02d}"))
    closure=TimePeriodClosure.query.filter_by(employee_id=emp.id,year=year,month=month).first()
    if not closure:
        closure=TimePeriodClosure(employee_id=emp.id,year=year,month=month,closed_by=current_user.id,
                                  reason=(request.form.get("reason") or "").strip() or None)
        db.session.add(closure)
    else:
        closure.status="closed"; closure.closed_at=now_local(); closure.closed_by=current_user.id
        closure.reason=(request.form.get("reason") or "").strip() or closure.reason
    log_action("fechou competência de ponto","time_period_closure",employee_id,f"{month:02d}/{year}")
    db.session.commit(); flash("Competência fechada.", "success")
    return redirect(url_for("rh.time_closing",month=f"{year:04d}-{month:02d}"))

@bp.route("/time-report/acknowledge", methods=["POST"])
@login_required
def time_report_acknowledge():
    emp = current_user.employee
    if not emp:
        abort(403)

    year = int(request.form["year"])
    month = int(request.form["month"])
    closure = TimePeriodClosure.query.filter_by(
        employee_id=emp.id,
        year=year,
        month=month,
        status="closed",
    ).first()
    if not closure:
        abort(400)

    if not closure.employee_viewed_at:
        flash("Abra e confira o relatório mensal antes de assinar.", "danger")
        return redirect(url_for("main.dashboard"))

    if request.form.get("confirm_ack") != "1":
        flash("Confirme que você leu e conferiu o espelho mensal.", "danger")
        return redirect(url_for("main.dashboard"))

    pin = (request.form.get("point_pin") or "").strip()
    if not re.fullmatch(r"\d{6}", pin) or not emp.check_point_pin(pin):
        flash("Senha de ponto inválida. A assinatura não foi registrada.", "danger")
        return redirect(url_for("main.dashboard"))

    ack = TimeReportAcknowledgement.query.filter_by(
        employee_id=emp.id,
        year=year,
        month=month,
    ).first()

    if not ack:
        ack = TimeReportAcknowledgement(
            employee_id=emp.id,
            year=year,
            month=month,
        )
        db.session.add(ack)
        db.session.flush()

        signature_code = _time_report_signature_code(ack, emp)
        log_action(
            "assinou eletronicamente o espelho mensal de ponto e banco de horas",
            "time_report_acknowledgement",
            ack.id,
            (
                f"{emp.full_name}; competência {month:02d}/{year}; "
                f"assinatura {signature_code}; autenticação por sessão e PIN pessoal"
            ),
        )
        db.session.commit()

    flash(
        "Espelho mensal conferido e assinado eletronicamente com sucesso. "
        "O documento assinado já está disponível para o RH.",
        "success",
    )
    return redirect(url_for("main.dashboard"))

@bp.route("/time-records")
@login_required
@roles_required(ROLE_ADMIN, ROLE_MANAGER)
def time_records():
    emps = visible_employees()
    ids = [e.id for e in emps]
    q = TimeClock.query.filter(TimeClock.employee_id.in_(ids)) if ids else TimeClock.query.filter(db.text("0=1"))

    employee_id = request.args.get("employee_id", type=int)
    start_date_raw = request.args.get("start_date")
    end_date_raw = request.args.get("end_date")
    start_date = parse_date(start_date_raw) if start_date_raw else None
    end_date = parse_date(end_date_raw) if end_date_raw else None

    if employee_id and employee_id in ids:
        q = q.filter(TimeClock.employee_id == employee_id)
    if start_date:
        q = q.filter(func.date(TimeClock.punched_at) >= start_date)
    if end_date:
        q = q.filter(func.date(TimeClock.punched_at) <= end_date)

    rows = q.order_by(TimeClock.punched_at.desc()).limit(500).all()
    return render_template(
        "time_records.html",
        rows=rows,
        employees=emps,
        selected_employee=employee_id,
        start_date=start_date_raw or "",
        end_date=end_date_raw or "",
    )


@bp.route("/employees/<int:employee_id>/time-report.pdf")
@login_required
def employee_time_report_pdf(employee_id):
    emp = db.get_or_404(Employee, employee_id)

    month_value = (request.args.get("month") or "").strip()
    try:
        if month_value:
            year, month = [int(x) for x in month_value.split("-", 1)]
            if month < 1 or month > 12:
                raise ValueError
        else:
            local_today = today_local()
            year, month = local_today.year, local_today.month
    except (ValueError, TypeError):
        flash("Informe um mês válido para gerar o PDF.", "danger")
        return redirect(url_for("rh.employee_detail", employee_id=employee_id) + "#controle-ponto")

    # RH pode consultar qualquer colaborador. O próprio colaborador só acessa
    # o seu relatório quando a competência já estiver formalmente fechada.
    closure = TimePeriodClosure.query.filter_by(
        employee_id=emp.id, year=year, month=month, status="closed"
    ).first()

    ack = TimeReportAcknowledgement.query.filter_by(
        employee_id=emp.id, year=year, month=month
    ).first()
    report_version = (request.args.get("version") or "original").strip().lower()
    if report_version not in {"original", "signed"}:
        report_version = "original"

    if report_version == "signed" and not ack:
        flash("O colaborador ainda não assinou eletronicamente esta competência.", "danger")
        if current_user.role == ROLE_ADMIN:
            return redirect(url_for("rh.time_closing", month=f"{year:04d}-{month:02d}"))
        return redirect(url_for("main.dashboard"))

    if current_user.role != ROLE_ADMIN:
        if not current_user.employee or current_user.employee.id != emp.id:
            abort(403)
        if not closure:
            flash("Este relatório ainda não foi fechado pelo RH.", "danger")
            return redirect(url_for("main.dashboard"))

    first_day = date(year, month, 1)
    last_day = date(year, month, calendar.monthrange(year, month)[1])
    rows = (TimeClock.query
            .filter(TimeClock.employee_id == emp.id,
                    func.date(TimeClock.punched_at) >= first_day,
                    func.date(TimeClock.punched_at) <= last_day)
            .order_by(TimeClock.punched_at.asc())
            .all())

    grouped = {}
    for row in rows:
        grouped.setdefault(row.punched_at.date(), []).append(row)

    # Movimentações aprovadas no período: somente solicitações efetivamente aprovadas
    # entram no espelho mensal e no saldo apresentado ao RH.
    approved_requests = (Request.query
        .filter(Request.employee_id == emp.id,
                Request.status == "approved",
                Request.request_date >= first_day,
                Request.request_date <= last_day,
                Request.request_type.in_(["overtime", "bank_use"]))
        .order_by(Request.request_date.asc())
        .all())
    overtime_by_day = {}
    bank_use_by_day = {}
    for req_item in approved_requests:
        target = overtime_by_day if req_item.request_type == "overtime" else bank_use_by_day
        target[req_item.request_date] = target.get(req_item.request_date, 0) + int(req_item.minutes or 0)

    month_adjustments = (BankHourAdjustment.query
        .filter(BankHourAdjustment.employee_id == emp.id,
                func.date(BankHourAdjustment.created_at) >= first_day,
                func.date(BankHourAdjustment.created_at) <= last_day)
        .all())

    # Extrato mensal completo do banco de horas.
    bank_movements = []
    for item in approved_requests:
        minutes_value = int(item.minutes or 0)
        signed = minutes_value if item.request_type == "overtime" else -minutes_value
        bank_movements.append({
            "date": datetime.combine(item.request_date, item.start_time or datetime.min.time()),
            "description": "Hora extra aprovada" if item.request_type == "overtime" else "Utilização de banco aprovada",
            "source": "Solicitação",
            "minutes": signed,
        })
    for item in month_adjustments:
        bank_movements.append({
            "date": item.created_at,
            "description": item.reason or "Ajuste administrativo",
            "source": "Ajuste RH",
            "minutes": int(item.minutes or 0),
        })
    bank_movements.sort(key=lambda x: x["date"])

    output = BytesIO()
    doc = SimpleDocTemplate(
        output,
        pagesize=landscape(A4),
        leftMargin=15 * mm, rightMargin=15 * mm, topMargin=14 * mm, bottomMargin=14 * mm,
        title=f"Ponto - {emp.full_name} - {month:02d}/{year}",
        author="Portal RH",
    )
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle("ReportTitle", parent=styles["Title"], fontName="Helvetica-Bold",
                                 fontSize=16, leading=19, alignment=TA_CENTER, spaceAfter=4 * mm)
    small_style = ParagraphStyle("Small", parent=styles["Normal"], fontName="Helvetica", fontSize=8.5, leading=11)
    small_bold = ParagraphStyle("SmallBold", parent=small_style, fontName="Helvetica-Bold")
    note_style = ParagraphStyle("Note", parent=styles["Normal"], fontName="Helvetica", fontSize=8, leading=10, textColor=colors.HexColor("#555555"))

    story = [
        Paragraph("ESPELHO MENSAL DE REGISTROS DE PONTO", title_style),
        Paragraph(f"<b>Competência:</b> {_month_name_pt(month)} de {year}", small_style),
        Spacer(1, 2 * mm),
    ]

    info_data = [
        [Paragraph("Colaborador", small_bold), Paragraph(_pdf_text(emp.full_name), small_style),
         Paragraph("CPF", small_bold), Paragraph(_pdf_text(emp.cpf), small_style)],
        [Paragraph("Cargo", small_bold), Paragraph(_pdf_text(emp.job_title), small_style),
         Paragraph("Setor/Projeto", small_bold), Paragraph(_pdf_text(f"{emp.department} / {emp.project}"), small_style)],
        [Paragraph("Admissão", small_bold), Paragraph(emp.admission_date.strftime("%d/%m/%Y"), small_style),
         Paragraph("Carga semanal", small_bold), Paragraph(f"{emp.weekly_hours:g}h", small_style)],
    ]
    info_table = Table(info_data, colWidths=[27*mm, 93*mm, 30*mm, 100*mm])
    info_table.setStyle(TableStyle([
        ("GRID", (0,0), (-1,-1), 0.35, colors.HexColor("#CCCCCC")),
        ("BACKGROUND", (0,0), (0,-1), colors.HexColor("#F1F3F5")),
        ("BACKGROUND", (2,0), (2,-1), colors.HexColor("#F1F3F5")),
        ("VALIGN", (0,0), (-1,-1), "MIDDLE"),
        ("LEFTPADDING", (0,0), (-1,-1), 5), ("RIGHTPADDING", (0,0), (-1,-1), 5),
        ("TOPPADDING", (0,0), (-1,-1), 4), ("BOTTOMPADDING", (0,0), (-1,-1), 4),
    ]))
    story.extend([info_table, Spacer(1, 4 * mm)])

    header = ["Data", "Entrada", "Saída intervalo", "Retorno", "Saída", "Horas trabalhadas", "Horas extras", "Outras marcações / observações"]
    data = [[Paragraph(f"<b>{h}</b>", small_style) for h in header]]
    total_worked_minutes = 0

    for day in range(1, last_day.day + 1):
        current_day = date(year, month, day)
        day_rows = grouped.get(current_day, [])
        by_kind = {"entrada": [], "saida_intervalo": [], "retorno": [], "saida": []}
        other = []
        for r in day_rows:
            if r.kind in by_kind:
                by_kind[r.kind].append(r)
            else:
                other.append(r)

        def first_or_dash(kind):
            values = by_kind[kind]
            return values[0].punched_at.strftime("%H:%M:%S") if values else "-"

        extras = []
        for kind, values in by_kind.items():
            if len(values) > 1:
                extras.append(f"{_kind_label(kind)} adicional: " + ", ".join(v.punched_at.strftime("%H:%M:%S") for v in values[1:]))
        for r in other:
            extras.append(f"{_kind_label(r.kind)}: {r.punched_at.strftime('%H:%M:%S')}")
        if day_rows and any(r.source != "portal" for r in day_rows):
            adjusted = [r for r in day_rows if r.source != "portal"]
            extras.append("Ajuste administrativo: " + ", ".join(f"{_kind_label(r.kind)} {r.punched_at.strftime('%H:%M:%S')}" for r in adjusted))

        worked_minutes = _worked_minutes_for_day(day_rows)
        total_worked_minutes += worked_minutes
        overtime_minutes = overtime_by_day.get(current_day, 0)
        bank_use_minutes = bank_use_by_day.get(current_day, 0)
        if bank_use_minutes:
            extras.append(f"Banco de horas utilizado: {_format_minutes(bank_use_minutes)}")

        weekday = ["Seg", "Ter", "Qua", "Qui", "Sex", "Sáb", "Dom"][current_day.weekday()]
        data.append([
            f"{current_day.strftime('%d/%m/%Y')} ({weekday})",
            first_or_dash("entrada"), first_or_dash("saida_intervalo"),
            first_or_dash("retorno"), first_or_dash("saida"),
            _format_minutes(worked_minutes) if worked_minutes else "-",
            _format_minutes(overtime_minutes) if overtime_minutes else "-",
            Paragraph(_pdf_text("; ".join(extras) if extras else ""), note_style),
        ])

    table = Table(data, repeatRows=1, colWidths=[31*mm, 25*mm, 29*mm, 25*mm, 25*mm, 30*mm, 27*mm, 58*mm])
    table_style = [
        ("BACKGROUND", (0,0), (-1,0), colors.HexColor("#E9ECEF")),
        ("GRID", (0,0), (-1,-1), 0.3, colors.HexColor("#C8CDD2")),
        ("VALIGN", (0,0), (-1,-1), "MIDDLE"),
        ("ALIGN", (1,1), (6,-1), "CENTER"),
        ("FONTNAME", (0,1), (6,-1), "Helvetica"),
        ("FONTSIZE", (0,0), (-1,-1), 7.5),
        ("TOPPADDING", (0,0), (-1,-1), 3.2),
        ("BOTTOMPADDING", (0,0), (-1,-1), 3.2),
    ]
    for idx in range(1, len(data)):
        day_date = date(year, month, idx)
        if day_date.weekday() >= 5:
            table_style.append(("BACKGROUND", (0,idx), (-1,idx), colors.HexColor("#FAFAFA")))
    table.setStyle(TableStyle(table_style))
    story.append(table)

    total_overtime = sum(overtime_by_day.values())
    total_bank_use = sum(bank_use_by_day.values())
    positive_adjustments = sum(a.minutes for a in month_adjustments if a.minutes > 0)
    negative_adjustments = abs(sum(a.minutes for a in month_adjustments if a.minutes < 0))
    total_credits = total_overtime + positive_adjustments
    total_debits = total_bank_use + negative_adjustments
    month_balance = total_credits - total_debits

    story.append(Spacer(1, 4 * mm))
    story.append(Paragraph("<b>RESUMO MENSAL</b>", small_style))
    summary_data = [
        [Paragraph("Horas trabalhadas registradas", small_bold), _format_minutes(total_worked_minutes),
         Paragraph("Horas extras aprovadas", small_bold), _format_minutes(total_overtime)],
        [Paragraph("Créditos manuais de banco", small_bold), _format_minutes(positive_adjustments),
         Paragraph("Horas descontadas / banco utilizado", small_bold), _format_minutes(total_debits)],
        [Paragraph("Total de créditos no mês", small_bold), _format_minutes(total_credits),
         Paragraph("Saldo do banco no mês", small_bold), _format_minutes(month_balance)],
    ]
    summary_table = Table(summary_data, colWidths=[60*mm, 35*mm, 70*mm, 35*mm])
    summary_table.setStyle(TableStyle([
        ("GRID", (0,0), (-1,-1), 0.35, colors.HexColor("#C8CDD2")),
        ("BACKGROUND", (0,0), (0,-1), colors.HexColor("#F1F3F5")),
        ("BACKGROUND", (2,0), (2,-1), colors.HexColor("#F1F3F5")),
        ("ALIGN", (1,0), (1,-1), "CENTER"),
        ("ALIGN", (3,0), (3,-1), "CENTER"),
        ("VALIGN", (0,0), (-1,-1), "MIDDLE"),
        ("FONTSIZE", (0,0), (-1,-1), 8.5),
        ("TOPPADDING", (0,0), (-1,-1), 5),
        ("BOTTOMPADDING", (0,0), (-1,-1), 5),
    ]))
    story.append(summary_table)
    story.append(Spacer(1, 5 * mm))

    story.append(Paragraph("<b>EXTRATO MENSAL DO BANCO DE HORAS</b>", small_style))
    bank_header = [
        Paragraph("<b>Data</b>", small_style),
        Paragraph("<b>Movimentação</b>", small_style),
        Paragraph("<b>Origem</b>", small_style),
        Paragraph("<b>Crédito</b>", small_style),
        Paragraph("<b>Débito</b>", small_style),
        Paragraph("<b>Saldo do mês</b>", small_style),
    ]
    bank_data = [bank_header]
    running_month = 0
    if bank_movements:
        for movement in bank_movements:
            running_month += movement["minutes"]
            bank_data.append([
                movement["date"].strftime("%d/%m/%Y"),
                Paragraph(_pdf_text(movement["description"]), note_style),
                movement["source"],
                _format_minutes(movement["minutes"]) if movement["minutes"] > 0 else "-",
                _format_minutes(abs(movement["minutes"])) if movement["minutes"] < 0 else "-",
                _format_minutes(running_month),
            ])
    else:
        bank_data.append([
            "-", Paragraph("Nenhuma movimentação de banco de horas nesta competência.", note_style),
            "-", "-", "-", _format_minutes(0),
        ])

    bank_table = Table(
        bank_data,
        repeatRows=1,
        colWidths=[28*mm, 88*mm, 32*mm, 30*mm, 30*mm, 34*mm],
    )
    bank_table.setStyle(TableStyle([
        ("BACKGROUND", (0,0), (-1,0), colors.HexColor("#E9ECEF")),
        ("GRID", (0,0), (-1,-1), 0.3, colors.HexColor("#C8CDD2")),
        ("VALIGN", (0,0), (-1,-1), "MIDDLE"),
        ("ALIGN", (0,1), (0,-1), "CENTER"),
        ("ALIGN", (3,1), (-1,-1), "CENTER"),
        ("FONTSIZE", (0,0), (-1,-1), 8),
        ("TOPPADDING", (0,0), (-1,-1), 4),
        ("BOTTOMPADDING", (0,0), (-1,-1), 4),
    ]))
    story.append(bank_table)
    story.append(Spacer(1, 4 * mm))

    if closure:
        closure_text = (
            f"<b>Fechamento da competência:</b> {closure.closed_at.strftime('%d/%m/%Y às %H:%M:%S')}"
        )
        if closure.reason:
            closure_text += f" · <b>Observação do RH:</b> {_pdf_text(closure.reason)}"
        story.append(Paragraph(closure_text, note_style))
        story.append(Spacer(1, 2 * mm))

    story.append(Spacer(1, 5 * mm))
    story.append(Paragraph("<b>ASSINATURA ELETRÔNICA DO COLABORADOR</b>", small_style))

    if report_version == "signed" and ack:
        signature_log = (AuditLog.query
            .filter_by(entity="time_report_acknowledgement", entity_id=ack.id)
            .order_by(AuditLog.created_at.desc())
            .first())
        signature_code = _time_report_signature_code(ack, emp)
        signature_ip = signature_log.ip_address if signature_log and signature_log.ip_address else "-"
        signer_email = emp.user.email if emp.user else "-"
        signature_data = [
            [Paragraph("Status", small_bold), Paragraph("ASSINADO ELETRONICAMENTE", small_bold)],
            [Paragraph("Colaborador", small_bold), Paragraph(_pdf_text(emp.full_name), small_style)],
            [Paragraph("Usuário autenticado", small_bold), Paragraph(_pdf_text(signer_email), small_style)],
            [Paragraph("Data e hora do aceite", small_bold), Paragraph(ack.acknowledged_at.strftime("%d/%m/%Y às %H:%M:%S"), small_style)],
            [Paragraph("Identificador da assinatura", small_bold), Paragraph(signature_code, small_style)],
            [Paragraph("Registro de acesso", small_bold), Paragraph(_pdf_text(signature_ip), small_style)],
            [Paragraph("Método de confirmação", small_bold), Paragraph("Sessão autenticada no Portal RH + senha pessoal de ponto (6 dígitos)", small_style)],
        ]
        signature_table = Table(signature_data, colWidths=[55*mm, 145*mm])
        signature_table.setStyle(TableStyle([
            ("GRID", (0,0), (-1,-1), 0.45, colors.HexColor("#D4B13F")),
            ("BACKGROUND", (0,0), (0,-1), colors.HexColor("#FFF4CF")),
            ("BACKGROUND", (1,0), (1,0), colors.HexColor("#EAF6EC")),
            ("VALIGN", (0,0), (-1,-1), "MIDDLE"),
            ("TOPPADDING", (0,0), (-1,-1), 5),
            ("BOTTOMPADDING", (0,0), (-1,-1), 5),
        ]))
        story.append(signature_table)
        story.append(Spacer(1, 2 * mm))
        story.append(Paragraph(
            "O colaborador declarou ter visualizado e conferido este espelho mensal, "
            "registrando seu aceite eletrônico no Portal RH.",
            note_style,
        ))
    else:
        pending_signature = [
            [Paragraph("Status", small_bold), Paragraph("AGUARDANDO CIÊNCIA E ASSINATURA DO COLABORADOR", small_style)],
            [Paragraph("Colaborador", small_bold), Paragraph(_pdf_text(emp.full_name), small_style)],
            [Paragraph("Competência", small_bold), Paragraph(f"{month:02d}/{year}", small_style)],
            [Paragraph("Assinatura", small_bold), Paragraph("____________________________________________________________", small_style)],
        ]
        pending_table = Table(pending_signature, colWidths=[55*mm, 145*mm])
        pending_table.setStyle(TableStyle([
            ("GRID", (0,0), (-1,-1), 0.4, colors.HexColor("#C8CDD2")),
            ("BACKGROUND", (0,0), (0,-1), colors.HexColor("#F1F3F5")),
            ("VALIGN", (0,0), (-1,-1), "MIDDLE"),
            ("TOPPADDING", (0,0), (-1,-1), 5),
            ("BOTTOMPADDING", (0,0), (-1,-1), 5),
        ]))
        story.append(pending_table)

    story.append(Spacer(1, 3 * mm))
    story.append(Paragraph(
        f"Documento gerado em {now_local().strftime('%d/%m/%Y às %H:%M:%S')} pelo Portal RH. "
        "Marcações ajustadas administrativamente permanecem registradas na trilha de Auditoria do sistema.",
        note_style,
    ))

    doc.build(story, onFirstPage=_draw_pdf_footer, onLaterPages=_draw_pdf_footer)
    output.seek(0)

    safe_name = secure_filename(emp.full_name).replace("_", "-") or f"colaborador-{emp.id}"
    suffix = "-assinado" if report_version == "signed" and ack else ""
    filename = f"ponto-banco-{safe_name}-{year}-{month:02d}{suffix}.pdf"
    if current_user.role != ROLE_ADMIN and closure and report_version == "original":
        closure.employee_viewed_at = now_local()
        log_action(
            "visualizou relatório mensal para ciência",
            "time_period_closure",
            closure.id,
            f"{emp.full_name}; competência {month:02d}/{year}"
        )
    else:
        log_action("gerou PDF mensal de ponto e banco", "employee", emp.id, f"competência {month:02d}/{year}")
    db.session.commit()

    # Para o colaborador, abre no navegador para leitura antes da ciência.
    # Para o RH, mantém o comportamento de download.
    return send_file(
        output,
        as_attachment=(current_user.role == ROLE_ADMIN),
        download_name=filename,
        mimetype="application/pdf"
    )

@bp.route("/report/time.xlsx")
@login_required
@roles_required(ROLE_ADMIN, ROLE_MANAGER)
def report_time():
    emps = visible_employees(); ids=[e.id for e in emps]
    rows=TimeClock.query.filter(TimeClock.employee_id.in_(ids)).order_by(TimeClock.punched_at.desc()).all()
    wb=Workbook(); ws=wb.active; ws.title="Ponto"
    ws.append(["Colaborador","Projeto","Setor","Data","Hora","Tipo","Origem"])
    for r in rows: ws.append([r.employee.full_name,r.employee.project,r.employee.department,r.punched_at.strftime("%d/%m/%Y"),r.punched_at.strftime("%H:%M:%S"),r.kind,r.source])
    bio=BytesIO(); wb.save(bio); bio.seek(0)
    return send_file(bio, as_attachment=True, download_name="relatorio_ponto.xlsx", mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

@bp.route("/audit")
@login_required
@roles_required(ROLE_ADMIN)
def audit():
    rows=AuditLog.query.order_by(AuditLog.created_at.desc()).limit(500).all()
    return render_template("audit.html", rows=rows)
