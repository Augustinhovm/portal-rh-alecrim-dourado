from datetime import date, time
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from .extensions import db
from .timezone import now_local, today_local

ROLE_ADMIN = "admin"
ROLE_MANAGER = "manager"
ROLE_EMPLOYEE = "employee"

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(180), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(20), nullable=False, default=ROLE_EMPLOYEE)
    active = db.Column(db.Boolean, default=True, nullable=False)
    must_change_password = db.Column(db.Boolean, default=False, nullable=False)
    password_changed_at = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, default=now_local, nullable=False)
    employee = db.relationship("Employee", back_populates="user", uselist=False)

    @property
    def is_active(self):
        return self.active

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)


class AuthThrottle(db.Model):
    """Controle persistente de tentativas de autenticação para produção com múltiplos workers."""
    id = db.Column(db.Integer, primary_key=True)
    key_hash = db.Column(db.String(64), unique=True, nullable=False, index=True)
    failures = db.Column(db.Integer, nullable=False, default=0)
    window_started_at = db.Column(db.DateTime, default=now_local, nullable=False)
    blocked_until = db.Column(db.DateTime)
    last_failure_at = db.Column(db.DateTime)
    updated_at = db.Column(db.DateTime, default=now_local, onupdate=now_local, nullable=False)



class SecurityEvent(db.Model):
    """Eventos de segurança que precisam existir independentemente de um usuário autenticado."""
    id = db.Column(db.Integer, primary_key=True)
    event_type = db.Column(db.String(60), nullable=False, index=True)
    severity = db.Column(db.String(20), nullable=False, default="info", index=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), index=True)
    employee_id = db.Column(db.Integer, db.ForeignKey("employee.id"), index=True)
    ip_address = db.Column(db.String(64), index=True)
    details = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=now_local, nullable=False, index=True)

    user = db.relationship("User", foreign_keys=[user_id])
    employee = db.relationship("Employee", foreign_keys=[employee_id])


class Employee(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), unique=True, nullable=False)
    full_name = db.Column(db.String(180), nullable=False)
    cpf = db.Column(db.String(14), unique=True, nullable=False)
    rg = db.Column(db.String(30))
    birth_date = db.Column(db.Date)
    phone = db.Column(db.String(30))
    address = db.Column(db.String(255))
    registration = db.Column(db.String(40), unique=True)
    job_title = db.Column(db.String(120), nullable=False)
    department = db.Column(db.String(120), nullable=False)
    project = db.Column(db.String(120), nullable=False, default="Administração")
    admission_date = db.Column(db.Date, nullable=False, default=today_local)
    contract_type = db.Column(db.String(80), default="CLT")
    weekly_hours = db.Column(db.Float, default=44)
    standard_start = db.Column(db.Time, default=time(8,0))
    standard_end = db.Column(db.Time, default=time(17,0))
    manager_id = db.Column(db.Integer, db.ForeignKey("employee.id"))
    bank_minutes = db.Column(db.Integer, default=0, nullable=False)
    point_pin_hash = db.Column(db.String(255))
    profile_photo = db.Column(db.String(255))
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    user = db.relationship("User", back_populates="employee")
    manager = db.relationship("Employee", remote_side=[id], backref="team")

    def set_point_pin(self, pin):
        self.point_pin_hash = generate_password_hash(pin)

    def check_point_pin(self, pin):
        return bool(self.point_pin_hash) and check_password_hash(self.point_pin_hash, pin)


class EmployeeWorkSchedule(db.Model):
    """Configuração complementar de jornada sem alterar a tabela Employee existente."""
    id = db.Column(db.Integer, primary_key=True)
    employee_id = db.Column(
        db.Integer,
        db.ForeignKey("employee.id"),
        nullable=False,
        unique=True,
        index=True,
    )
    interval_start = db.Column(db.Time)
    interval_end = db.Column(db.Time)
    updated_at = db.Column(db.DateTime, default=now_local, onupdate=now_local, nullable=False)
    updated_by = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)

    employee = db.relationship(
        "Employee",
        backref=db.backref("work_schedule", uselist=False, cascade="all, delete-orphan"),
    )
    updater = db.relationship("User", foreign_keys=[updated_by])


class WeekendDuty(db.Model):
    """Plantão executado e creditado diretamente no banco de horas."""
    id = db.Column(db.Integer, primary_key=True)
    employee_id = db.Column(db.Integer, db.ForeignKey("employee.id"), nullable=False, index=True)
    duty_date = db.Column(db.Date, nullable=False, index=True)
    minutes = db.Column(db.Integer, nullable=False, default=840)
    note = db.Column(db.String(255))
    created_at = db.Column(db.DateTime, default=now_local, nullable=False)
    created_by = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)

    employee = db.relationship("Employee")
    creator = db.relationship("User", foreign_keys=[created_by])

    __table_args__ = (
        db.UniqueConstraint("employee_id", "duty_date", name="uq_weekend_duty_employee_date"),
    )


class TimeClock(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    employee_id = db.Column(db.Integer, db.ForeignKey("employee.id"), nullable=False, index=True)
    punched_at = db.Column(db.DateTime, default=now_local, nullable=False, index=True)
    kind = db.Column(db.String(30), nullable=False)  # entrada, saida_intervalo, retorno, saida
    source = db.Column(db.String(30), default="portal", nullable=False)
    ip_address = db.Column(db.String(64))
    employee = db.relationship("Employee")


class BankHourAdjustment(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    employee_id = db.Column(db.Integer, db.ForeignKey("employee.id"), nullable=False, index=True)
    minutes = db.Column(db.Integer, nullable=False)
    reason = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=now_local, nullable=False, index=True)
    created_by = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    employee = db.relationship("Employee")
    creator = db.relationship("User", foreign_keys=[created_by])

class MedicalCertificate(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    employee_id = db.Column(db.Integer, db.ForeignKey("employee.id"), nullable=False, index=True)
    start_date = db.Column(db.Date, nullable=False)
    days = db.Column(db.Integer, nullable=False, default=1)
    note = db.Column(db.String(255))
    original_name = db.Column(db.String(255), nullable=False)
    stored_name = db.Column(db.String(255), nullable=False)
    uploaded_at = db.Column(db.DateTime, default=now_local, nullable=False)
    status = db.Column(db.String(30), default="recebido", nullable=False)
    employee = db.relationship("Employee")


class MedicalCertificateAllowance(db.Model):
    """Horas justificadas pelo RH em razão de um atestado recebido."""
    id = db.Column(db.Integer, primary_key=True)
    certificate_id = db.Column(
        db.Integer,
        db.ForeignKey("medical_certificate.id"),
        nullable=False,
        unique=True,
        index=True,
    )
    employee_id = db.Column(db.Integer, db.ForeignKey("employee.id"), nullable=False, index=True)
    minutes = db.Column(db.Integer, nullable=False, default=0)
    note = db.Column(db.String(255))
    approved_by = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    created_at = db.Column(db.DateTime, default=now_local, nullable=False)
    updated_at = db.Column(db.DateTime, default=now_local, onupdate=now_local, nullable=False)

    certificate = db.relationship(
        "MedicalCertificate",
        backref=db.backref("allowance", uselist=False, cascade="all, delete-orphan"),
    )
    employee = db.relationship("Employee")
    approver = db.relationship("User", foreign_keys=[approved_by])


class Request(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    employee_id = db.Column(db.Integer, db.ForeignKey("employee.id"), nullable=False, index=True)
    request_type = db.Column(db.String(30), nullable=False) # bank_use, overtime, clock_adjustment
    request_date = db.Column(db.Date, nullable=False)
    start_time = db.Column(db.Time)
    end_time = db.Column(db.Time)
    minutes = db.Column(db.Integer, default=0)
    reason = db.Column(db.Text, nullable=False)
    status = db.Column(db.String(20), default="pending", nullable=False, index=True)
    requested_at = db.Column(db.DateTime, default=now_local, nullable=False)
    decided_at = db.Column(db.DateTime)
    decided_by = db.Column(db.Integer, db.ForeignKey("user.id"))
    decision_note = db.Column(db.Text)
    target_clock_kind = db.Column(db.String(30))
    bank_effect_applied = db.Column(db.Boolean, default=False, nullable=False)
    bank_effect_applied_at = db.Column(db.DateTime)
    employee = db.relationship("Employee")
    decider = db.relationship("User", foreign_keys=[decided_by])


class Payslip(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    employee_id = db.Column(db.Integer, db.ForeignKey("employee.id"), nullable=False, index=True)
    year = db.Column(db.Integer, nullable=False, index=True)
    month = db.Column(db.Integer, nullable=False, index=True)
    original_name = db.Column(db.String(255), nullable=False)
    stored_name = db.Column(db.String(255), nullable=False)
    matched_by = db.Column(db.String(20), nullable=False, default="manual")
    uploaded_at = db.Column(db.DateTime, default=now_local, nullable=False)
    uploaded_by = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    employee_viewed_at = db.Column(db.DateTime)
    employee = db.relationship("Employee")
    uploader = db.relationship("User", foreign_keys=[uploaded_by])
    __table_args__ = (
        db.UniqueConstraint("employee_id", "year", "month", name="uq_payslip_employee_competence"),
    )

class Document(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    employee_id = db.Column(db.Integer, db.ForeignKey("employee.id"), nullable=False, index=True)
    category = db.Column(db.String(80), nullable=False)
    title = db.Column(db.String(180), nullable=False)
    original_name = db.Column(db.String(255), nullable=False)
    stored_name = db.Column(db.String(255), nullable=False)
    uploaded_at = db.Column(db.DateTime, default=now_local, nullable=False)
    employee = db.relationship("Employee")


class DocumentSignatureFlow(db.Model):
    """Fluxo de ciência/assinatura eletrônica associado a um documento existente."""
    id = db.Column(db.Integer, primary_key=True)
    document_id = db.Column(db.Integer, db.ForeignKey("document.id"), nullable=False, unique=True, index=True)
    requested_at = db.Column(db.DateTime, default=now_local, nullable=False)
    requested_by = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    employee_viewed_at = db.Column(db.DateTime)
    signed_at = db.Column(db.DateTime)
    signature_code = db.Column(db.String(64), unique=True)
    signer_ip = db.Column(db.String(64))
    finalized_at = db.Column(db.DateTime)
    finalized_by = db.Column(db.Integer, db.ForeignKey("user.id"))
    final_note = db.Column(db.String(255))
    cancelled_at = db.Column(db.DateTime)
    cancelled_by = db.Column(db.Integer, db.ForeignKey("user.id"))
    cancel_note = db.Column(db.String(255))

    document = db.relationship(
        "Document",
        backref=db.backref("signature_flow", uselist=False, cascade="all, delete-orphan"),
    )
    requester = db.relationship("User", foreign_keys=[requested_by])
    finalizer = db.relationship("User", foreign_keys=[finalized_by])
    canceller = db.relationship("User", foreign_keys=[cancelled_by])

    @property
    def status(self):
        if self.cancelled_at:
            return "cancelled"
        if self.finalized_at:
            return "finalized"
        if self.signed_at:
            return "awaiting_rh"
        if self.employee_viewed_at:
            return "viewed"
        return "pending"


class PayrollEmployeeConfig(db.Model):
    """Configuração remuneratória do colaborador sem alterar a tabela Employee existente."""
    id = db.Column(db.Integer, primary_key=True)
    employee_id = db.Column(
        db.Integer, db.ForeignKey("employee.id"), nullable=False, unique=True, index=True
    )
    monthly_salary = db.Column(db.Numeric(12, 2), nullable=False, default=0)
    salary_effective_date = db.Column(db.Date, nullable=False, default=today_local)
    salary_type = db.Column(db.String(30), nullable=False, default="monthly")
    has_transport_voucher = db.Column(db.Boolean, default=False, nullable=False)
    transport_discount_percent = db.Column(db.Numeric(5, 2), default=0)
    food_discount_value = db.Column(db.Numeric(12, 2), default=0)
    health_plan_discount_value = db.Column(db.Numeric(12, 2), default=0)
    pension_discount_value = db.Column(db.Numeric(12, 2), default=0)
    other_fixed_discount_value = db.Column(db.Numeric(12, 2), default=0)
    other_fixed_discount_description = db.Column(db.String(180))
    notes = db.Column(db.Text)
    updated_at = db.Column(db.DateTime, default=now_local, onupdate=now_local, nullable=False)
    updated_by = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)

    employee = db.relationship(
        "Employee",
        backref=db.backref("payroll_config", uselist=False, cascade="all, delete-orphan"),
    )
    updater = db.relationship("User", foreign_keys=[updated_by])


class PayrollDependent(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    employee_id = db.Column(db.Integer, db.ForeignKey("employee.id"), nullable=False, index=True)
    full_name = db.Column(db.String(180), nullable=False)
    cpf = db.Column(db.String(14))
    birth_date = db.Column(db.Date)
    relationship = db.Column(db.String(60))
    irrf_dependent = db.Column(db.Boolean, default=False, nullable=False)
    salary_family_eligible = db.Column(db.Boolean, default=False, nullable=False)
    active = db.Column(db.Boolean, default=True, nullable=False)
    notes = db.Column(db.String(255))
    created_at = db.Column(db.DateTime, default=now_local, nullable=False)
    created_by = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)

    employee = db.relationship(
        "Employee",
        backref=db.backref("payroll_dependents", cascade="all, delete-orphan"),
    )
    creator = db.relationship("User", foreign_keys=[created_by])


class PayrollLegalParameter(db.Model):
    """Parâmetro legal versionado por vigência para preservar cálculos históricos."""
    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(80), nullable=False, index=True)
    description = db.Column(db.String(180), nullable=False)
    value = db.Column(db.Numeric(14, 6), nullable=False)
    value_type = db.Column(db.String(20), nullable=False, default="money")
    effective_from = db.Column(db.Date, nullable=False, index=True)
    effective_to = db.Column(db.Date)
    legal_reference = db.Column(db.String(255))
    source_url = db.Column(db.String(500))
    notes = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=now_local, nullable=False)
    created_by = db.Column(db.Integer, db.ForeignKey("user.id"))

    __table_args__ = (
        db.UniqueConstraint("code", "effective_from", name="uq_payroll_legal_code_effective"),
    )


class PayrollRubric(db.Model):
    """Cadastro de verbas/rubricas para futura integração com o motor de folha."""
    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(40), nullable=False, unique=True, index=True)
    description = db.Column(db.String(180), nullable=False)
    nature = db.Column(db.String(30), nullable=False, default="earning")
    esocial_nature = db.Column(db.String(20))
    inss_incidence = db.Column(db.Boolean, default=False, nullable=False)
    fgts_incidence = db.Column(db.Boolean, default=False, nullable=False)
    irrf_incidence = db.Column(db.Boolean, default=False, nullable=False)
    active = db.Column(db.Boolean, default=True, nullable=False)
    default_percentage = db.Column(db.Numeric(7, 4))
    notes = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=now_local, nullable=False)
    created_by = db.Column(db.Integer, db.ForeignKey("user.id"))


class AuditLog(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"))
    action = db.Column(db.String(120), nullable=False)
    entity = db.Column(db.String(80), nullable=False)
    entity_id = db.Column(db.Integer)
    details = db.Column(db.Text)
    ip_address = db.Column(db.String(64))
    created_at = db.Column(db.DateTime, default=now_local, nullable=False, index=True)
    user = db.relationship("User")


class Vacation(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    employee_id = db.Column(db.Integer, db.ForeignKey("employee.id"), nullable=False, index=True)
    start_date = db.Column(db.Date, nullable=False)
    days = db.Column(db.Integer, nullable=False, default=30)
    note = db.Column(db.String(255))
    created_at = db.Column(db.DateTime, default=now_local, nullable=False)
    created_by = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    employee = db.relationship("Employee")
    creator = db.relationship("User", foreign_keys=[created_by])



class VacationSchedule(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    employee_id = db.Column(db.Integer, db.ForeignKey("employee.id"), nullable=False, index=True)
    planned_start = db.Column(db.Date, nullable=False)
    planned_return = db.Column(db.Date)
    days = db.Column(db.Integer, nullable=False, default=30)
    status = db.Column(db.String(20), nullable=False, default="planned")  # planned, completed, cancelled
    note = db.Column(db.String(255))
    created_at = db.Column(db.DateTime, default=now_local, nullable=False)
    created_by = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    completed_at = db.Column(db.DateTime)
    employee = db.relationship("Employee")
    creator = db.relationship("User", foreign_keys=[created_by])

class TimePeriodClosure(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    employee_id = db.Column(db.Integer, db.ForeignKey("employee.id"), nullable=False, index=True)
    year = db.Column(db.Integer, nullable=False)
    month = db.Column(db.Integer, nullable=False)
    status = db.Column(db.String(20), default="closed", nullable=False)
    closed_at = db.Column(db.DateTime, default=now_local, nullable=False)
    closed_by = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    reopened_at = db.Column(db.DateTime)
    reopened_by = db.Column(db.Integer, db.ForeignKey("user.id"))
    employee_viewed_at = db.Column(db.DateTime)
    reason = db.Column(db.Text)
    employee = db.relationship("Employee")
    closer = db.relationship("User", foreign_keys=[closed_by])
    __table_args__ = (db.UniqueConstraint("employee_id", "year", "month", name="uq_time_period_employee_month"),)


class TimeReportFinalization(db.Model):
    """Validação final do RH após a assinatura eletrônica do colaborador."""
    id = db.Column(db.Integer, primary_key=True)
    employee_id = db.Column(db.Integer, db.ForeignKey("employee.id"), nullable=False, index=True)
    year = db.Column(db.Integer, nullable=False)
    month = db.Column(db.Integer, nullable=False)
    approved_at = db.Column(db.DateTime, default=now_local, nullable=False)
    approved_by = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    note = db.Column(db.String(255))
    employee = db.relationship("Employee")
    approver = db.relationship("User", foreign_keys=[approved_by])
    __table_args__ = (
        db.UniqueConstraint("employee_id", "year", "month", name="uq_time_final_employee_month"),
    )


class TimeReportAcknowledgement(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    employee_id = db.Column(db.Integer, db.ForeignKey("employee.id"), nullable=False, index=True)
    year = db.Column(db.Integer, nullable=False)
    month = db.Column(db.Integer, nullable=False)
    acknowledged_at = db.Column(db.DateTime, default=now_local, nullable=False)
    employee = db.relationship("Employee")
    __table_args__ = (db.UniqueConstraint("employee_id", "year", "month", name="uq_time_ack_employee_month"),)
