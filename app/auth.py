from flask import Blueprint, render_template, request, redirect, url_for, flash, session, current_app
from flask_login import login_user, logout_user, login_required, current_user
from .extensions import db
from .models import User, AuthThrottle
from .timezone import now_local
from datetime import timedelta
import hashlib
import re
from werkzeug.security import generate_password_hash, check_password_hash
from .security import log_action, client_ip

LOGIN_WINDOW_MINUTES = 15
LOGIN_MAX_FAILURES = 6
LOGIN_BLOCK_MINUTES = 20
DUMMY_PASSWORD_HASH = generate_password_hash("Portal-RH-dummy-password-not-a-user")


def _login_key(email):
    # O bloqueio principal é por origem/IP para evitar bypass usando e-mails aleatórios.
    raw = f"login|{client_ip()}|{current_app.config['SECRET_KEY']}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _get_throttle(key_hash):
    return AuthThrottle.query.filter_by(key_hash=key_hash).first()


def _is_login_blocked(key_hash):
    row = _get_throttle(key_hash)
    if not row:
        return False
    now = now_local()
    if row.blocked_until and row.blocked_until > now:
        return True
    if row.blocked_until and row.blocked_until <= now:
        row.failures = 0
        row.blocked_until = None
        row.window_started_at = now
        db.session.commit()
    return False


def _record_login_failure(key_hash):
    now = now_local()
    row = _get_throttle(key_hash)
    if not row:
        row = AuthThrottle(
            key_hash=key_hash,
            failures=0,
            window_started_at=now,
        )
        db.session.add(row)

    if not row.window_started_at or now - row.window_started_at > timedelta(minutes=LOGIN_WINDOW_MINUTES):
        row.failures = 0
        row.window_started_at = now

    row.failures += 1
    row.last_failure_at = now

    if row.failures >= LOGIN_MAX_FAILURES:
        row.blocked_until = now + timedelta(minutes=LOGIN_BLOCK_MINUTES)

    db.session.commit()


def _clear_login_failures(key_hash):
    row = _get_throttle(key_hash)
    if row:
        db.session.delete(row)
        db.session.commit()


def _password_is_strong(password):
    if len(password or "") < 10:
        return False
    checks = [
        re.search(r"[A-Z]", password),
        re.search(r"[a-z]", password),
        re.search(r"\d", password),
        re.search(r"[^A-Za-z0-9]", password),
    ]
    return all(checks)


bp = Blueprint("auth", __name__, url_prefix="/auth")

@bp.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("main.dashboard"))
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        key = _login_key(email)

        if _is_login_blocked(key):
            flash("Muitas tentativas de acesso. Aguarde alguns minutos e tente novamente.", "danger")
            return render_template("login.html"), 429

        user = User.query.filter_by(email=email).first()

        # Executa uma verificação de hash também quando o usuário não existe,
        # reduzindo diferenças de tempo que poderiam facilitar enumeração de contas.
        password_ok = user.check_password(password) if user else check_password_hash(DUMMY_PASSWORD_HASH, password)

        if not user or not password_ok or not user.active:
            _record_login_failure(key)
            flash("E-mail ou senha inválidos.", "danger")
        else:
            _clear_login_failures(key)
            # Mitiga fixation: descarta a sessão anônima/CSRF anterior antes de autenticar.
            session.clear()
            login_user(user, remember=False, fresh=True)
            session.permanent = True
            log_action("login realizado", "user", user.id, "Autenticação concluída com sucesso.")
            db.session.commit()
            if user.must_change_password:
                flash("Por segurança, defina sua senha pessoal antes de continuar.", "info")
                return redirect(url_for("auth.change_password"))
            return redirect(url_for("main.dashboard"))
    return render_template("login.html")

@bp.route("/logout", methods=["POST"])
@login_required
def logout():
    logout_user()
    session.clear()
    return redirect(url_for("auth.login"))


@bp.route("/change-password", methods=["GET", "POST"])
@login_required
def change_password():
    if request.method == "POST":
        current_password = request.form.get("current_password", "")
        new_password = request.form.get("new_password", "")
        confirm_password = request.form.get("confirm_password", "")

        if not current_user.check_password(current_password):
            flash("A senha provisória informada está incorreta.", "danger")
            return render_template("change_password.html")

        if not _password_is_strong(new_password):
            flash(
                "A nova senha deve ter pelo menos 10 caracteres, incluindo letra maiúscula, "
                "letra minúscula, número e caractere especial.",
                "danger",
            )
            return render_template("change_password.html")

        if new_password != confirm_password:
            flash("A confirmação da nova senha não confere.", "danger")
            return render_template("change_password.html")

        if current_user.check_password(new_password):
            flash("A nova senha deve ser diferente da senha provisória.", "danger")
            return render_template("change_password.html")

        current_user.set_password(new_password)
        current_user.must_change_password = False
        current_user.password_changed_at = now_local()
        log_action("alterou senha no primeiro acesso", "user", current_user.id, "Senha pessoal definida pelo usuário.")
        db.session.commit()
        flash("Senha pessoal criada com sucesso.", "success")
        return redirect(url_for("main.dashboard"))

    return render_template("change_password.html")
