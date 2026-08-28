from flask import Blueprint, render_template
from flask_login import login_required, current_user
from sqlalchemy import func
from datetime import timedelta
from .extensions import db
from .models import User, Employee, MedicalCertificate, Request, TimeClock, TimePeriodClosure, TimeReportAcknowledgement, TimeReportFinalization, VacationSchedule, BankHourAdjustment, WeekendDuty, Payslip, ROLE_ADMIN, ROLE_MANAGER
from .timezone import today_local

bp = Blueprint("main", __name__)

@bp.route("/")
@login_required
def dashboard():
    today = today_local()
    data = {}
    if current_user.role == ROLE_ADMIN:
        employee_ids = [e.id for e in Employee.query.filter_by(is_active=True).all()]
        data["employees"] = len(employee_ids)
        data["certificates_month"] = MedicalCertificate.query.filter(
            func.extract('month', MedicalCertificate.start_date) == today.month,
            func.extract('year', MedicalCertificate.start_date) == today.year,
        ).count()
        data["pending"] = Request.query.filter_by(status="pending").count()
        data["bank_minutes"] = db_sum_bank()
        data["today_punches"] = TimeClock.query.filter(
            TimeClock.employee_id.in_(employee_ids),
            func.date(TimeClock.punched_at) == today
        ).order_by(TimeClock.punched_at.desc()).limit(20).all() if employee_ids else []
        data["pending_requests"] = Request.query.filter_by(status="pending").order_by(Request.requested_at.desc()).limit(10).all()
        data["recent_certificates"] = MedicalCertificate.query.order_by(MedicalCertificate.uploaded_at.desc()).limit(10).all()
        data["certificates_received"] = MedicalCertificate.query.filter_by(status="recebido").count()

        data["incomplete_today"] = 0
        for eid in employee_ids:
            count = TimeClock.query.filter(
                TimeClock.employee_id == eid,
                func.date(TimeClock.punched_at) == today
            ).count()
            if count not in (0, 4):
                data["incomplete_today"] += 1

        # Indicadores executivos do RH para a competência atual.
        current_closures = TimePeriodClosure.query.filter(
            TimePeriodClosure.employee_id.in_(employee_ids),
            TimePeriodClosure.year == today.year,
            TimePeriodClosure.month == today.month,
            TimePeriodClosure.status == "closed",
        ).all() if employee_ids else []

        closure_keys = {(c.employee_id, c.year, c.month) for c in current_closures}
        data["closed_current_month"] = len(current_closures)
        data["open_current_month"] = max(len(employee_ids) - len(current_closures), 0)

        data["awaiting_employee_signature"] = 0
        data["awaiting_rh_validation"] = 0
        for closure in current_closures:
            ack = TimeReportAcknowledgement.query.filter_by(
                employee_id=closure.employee_id,
                year=closure.year,
                month=closure.month,
            ).first()
            if not ack:
                data["awaiting_employee_signature"] += 1
            else:
                final = TimeReportFinalization.query.filter_by(
                    employee_id=closure.employee_id,
                    year=closure.year,
                    month=closure.month,
                ).first()
                if not final:
                    data["awaiting_rh_validation"] += 1

        data["unread_payslips"] = Payslip.query.filter(
            Payslip.employee_id.in_(employee_ids),
            Payslip.employee_viewed_at.is_(None),
        ).count() if employee_ids else 0

        data["employees_without_pin"] = Employee.query.filter(
            Employee.is_active.is_(True),
            Employee.point_pin_hash.is_(None),
        ).count()

        data["password_change_pending"] = (
            Employee.query.join(User)
            .filter(
                Employee.is_active.is_(True),
                User.must_change_password.is_(True),
            )
            .count()
        )

        next_30 = today + timedelta(days=30)
        data["vacations_next_30"] = VacationSchedule.query.filter(
            VacationSchedule.employee_id.in_(employee_ids),
            VacationSchedule.status == "planned",
            VacationSchedule.planned_start >= today,
            VacationSchedule.planned_start <= next_30,
        ).count() if employee_ids else 0

        data["total_pending_rh"] = (
            data["pending"]
            + data["certificates_received"]
            + data["incomplete_today"]
            + data["open_current_month"]
            + data["awaiting_employee_signature"]
            + data["awaiting_rh_validation"]
            + data["employees_without_pin"]
            + data["password_change_pending"]
        )
    elif current_user.role == ROLE_MANAGER and current_user.employee:
        team_ids = [e.id for e in current_user.employee.team]
        visible_ids = team_ids + [current_user.employee.id]
        data["employees"] = len(visible_ids)
        data["pending"] = Request.query.filter(Request.employee_id.in_(team_ids), Request.status == "pending").count() if team_ids else 0
        data["certificates_month"] = MedicalCertificate.query.filter(
            MedicalCertificate.employee_id.in_(visible_ids),
            func.extract('month', MedicalCertificate.start_date) == today.month,
            func.extract('year', MedicalCertificate.start_date) == today.year,
        ).count() if visible_ids else 0
        data["bank_minutes"] = sum(e.bank_minutes for e in current_user.employee.team)
        data["today_punches"] = TimeClock.query.filter(
            TimeClock.employee_id.in_(visible_ids),
            func.date(TimeClock.punched_at) == today
        ).order_by(TimeClock.punched_at.desc()).limit(20).all() if visible_ids else []
        data["pending_requests"] = Request.query.filter(
            Request.employee_id.in_(team_ids), Request.status == "pending"
        ).order_by(Request.requested_at.desc()).limit(10).all() if team_ids else []
    else:
        emp = current_user.employee
        if emp:
            # Import local evita dependência circular entre os blueprints.
            from .rh import _bank_summary, _expected_daily_minutes, _worked_minutes_for_day
            bank_summary = _bank_summary(emp)
            data["bank_minutes"] = bank_summary["current"]
            data["bank_scheduled_minutes"] = bank_summary["scheduled"]
            data["bank_available_minutes"] = bank_summary["available"]

            today_rows = TimeClock.query.filter(
                TimeClock.employee_id == emp.id,
                func.date(TimeClock.punched_at) == today
            ).order_by(TimeClock.punched_at.asc()).all()
            data["last_punch"] = today_rows[-1] if today_rows else None
            data["worked_today_minutes"] = _worked_minutes_for_day(today_rows)
            data["expected_today_minutes"] = _expected_daily_minutes(emp) if today.weekday() < 5 else 0
            data["day_balance_minutes"] = data["worked_today_minutes"] - data["expected_today_minutes"] if data["worked_today_minutes"] else 0

            month_start = today.replace(day=1)
            approved_month = Request.query.filter(
                Request.employee_id == emp.id,
                Request.status == "approved",
                Request.request_date >= month_start,
                Request.request_date <= today,
                Request.request_type.in_(["overtime", "bank_use"])
            ).all()
            month_adjustments = BankHourAdjustment.query.filter(
                BankHourAdjustment.employee_id == emp.id,
                func.date(BankHourAdjustment.created_at) >= month_start,
                func.date(BankHourAdjustment.created_at) <= today
            ).all()
            month_duties = WeekendDuty.query.filter(
                WeekendDuty.employee_id == emp.id,
                WeekendDuty.duty_date >= month_start,
                WeekendDuty.duty_date <= today
            ).all()

            credits = sum(int(q.minutes or 0) for q in approved_month if q.request_type == "overtime")
            credits += sum(int(a.minutes or 0) for a in month_adjustments if int(a.minutes or 0) > 0)
            credits += sum(int(d.minutes or 0) for d in month_duties)
            debits = sum(int(q.minutes or 0) for q in approved_month if q.request_type == "bank_use" and q.request_date <= today)
            debits += abs(sum(int(a.minutes or 0) for a in month_adjustments if int(a.minutes or 0) < 0))
            data["bank_credits_month"] = credits
            data["bank_debits_month"] = debits
            data["bank_previous_balance"] = int(emp.bank_minutes or 0) - credits + debits

            data["pending_certificate_count"] = MedicalCertificate.query.filter(
                MedicalCertificate.employee_id == emp.id,
                MedicalCertificate.status == "recebido"
            ).count()
            data["latest_pending_certificate"] = MedicalCertificate.query.filter(
                MedicalCertificate.employee_id == emp.id,
                MedicalCertificate.status == "recebido"
            ).order_by(MedicalCertificate.uploaded_at.desc()).first()
            data["latest_unread_payslip"] = (Payslip.query
                .filter(
                    Payslip.employee_id == emp.id,
                    Payslip.employee_viewed_at.is_(None)
                )
                .order_by(Payslip.year.desc(), Payslip.month.desc())
                .first())
        else:
            data["bank_minutes"] = 0
            data["bank_scheduled_minutes"] = 0
            data["bank_available_minutes"] = 0
        data["pending"] = Request.query.filter_by(employee_id=emp.id, status="pending").count() if emp else 0
        data["today_punches"] = TimeClock.query.filter(
            TimeClock.employee_id == emp.id,
            func.date(TimeClock.punched_at) == today
        ).order_by(TimeClock.punched_at).all() if emp else []
        data["closed_unacknowledged"] = []
        data["next_vacation"] = None
        if emp:
            closures = TimePeriodClosure.query.filter_by(employee_id=emp.id,status="closed").order_by(TimePeriodClosure.year.desc(),TimePeriodClosure.month.desc()).all()
            for c in closures:
                if not TimeReportAcknowledgement.query.filter_by(employee_id=emp.id,year=c.year,month=c.month).first():
                    data["closed_unacknowledged"].append(c)
            data["finalized_time_reports"] = (
                TimeReportFinalization.query
                .filter_by(employee_id=emp.id)
                .order_by(TimeReportFinalization.year.desc(), TimeReportFinalization.month.desc())
                .limit(12)
                .all()
            )
            data["next_vacation"] = (VacationSchedule.query
                .filter(
                    VacationSchedule.employee_id == emp.id,
                    VacationSchedule.status == "planned",
                    VacationSchedule.planned_start >= today
                )
                .order_by(VacationSchedule.planned_start.asc())
                .first())
    # Holerites ficam vinculados diretamente ao cadastro Employee do usuário logado.
    # Esta consulta é feita fora dos blocos de papel para funcionar também quando
    # um colaborador possui perfil de responsável/gestor.
    if current_user.role != ROLE_ADMIN and current_user.employee:
        employee_id = current_user.employee.id
        data["latest_payslip"] = (Payslip.query
            .filter(Payslip.employee_id == employee_id)
            .order_by(Payslip.year.desc(), Payslip.month.desc(), Payslip.uploaded_at.desc())
            .first())
        data["unread_payslip_count"] = (Payslip.query
            .filter(
                Payslip.employee_id == employee_id,
                Payslip.employee_viewed_at.is_(None)
            )
            .count())
        data["latest_unread_payslip"] = (Payslip.query
            .filter(
                Payslip.employee_id == employee_id,
                Payslip.employee_viewed_at.is_(None)
            )
            .order_by(Payslip.year.desc(), Payslip.month.desc(), Payslip.uploaded_at.desc())
            .first())

    return render_template("dashboard.html", data=data, today=today)

def db_sum_bank():
    result = Employee.query.with_entities(func.coalesce(func.sum(Employee.bank_minutes), 0)).scalar()
    return int(result or 0)
