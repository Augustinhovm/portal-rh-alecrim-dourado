from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_user, logout_user, login_required, current_user
from .extensions import db
from .models import User
from .timezone import now_local
from .security import log_action
from collections import defaultdict, deque
from time import monotonic

_login_attempts = defaultdict(deque)
LOGIN_WINDOW_SECONDS = 15 * 60
LOGIN_MAX_FAILURES = 8

def _login_key(email):
    return f"{request.remote_addr or 'unknown'}:{email}"

def _is_login_blocked(key):
    now = monotonic()
    attempts = _login_attempts[key]
    while attempts and now - attempts[0] > LOGIN_WINDOW_SECONDS:
        attempts.popleft()
    return len(attempts) >= LOGIN_MAX_FAILURES

def _record_login_failure(key):
    _login_attempts[key].append(monotonic())

def _clear_login_failures(key):
    _login_attempts.pop(key, None)

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
        if not user or not user.check_password(password) or not user.active:
            _record_login_failure(key)
            flash("E-mail ou senha inválidos.", "danger")
        else:
            _clear_login_failures(key)
            login_user(user)
            if user.must_change_password:
                flash("Por segurança, defina sua senha pessoal antes de continuar.", "info")
                return redirect(url_for("auth.change_password"))
            return redirect(url_for("main.dashboard"))
    return render_template("login.html")

@bp.route("/logout", methods=["POST"])
@login_required
def logout():
    logout_user()
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

        if len(new_password) < 8:
            flash("A nova senha deve possuir pelo menos 8 caracteres.", "danger")
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
