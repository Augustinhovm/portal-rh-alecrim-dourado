import os
import secrets
from flask import Flask, redirect, url_for, request, session, abort
from dotenv import load_dotenv
from werkzeug.middleware.proxy_fix import ProxyFix
from .extensions import db, login_manager


def _database_url():
    value = os.getenv("DATABASE_URL", "").strip()
    if not value:
        return "sqlite:///rh.db"
    # Compatibilidade com provedores que ainda entregam postgres://
    if value.startswith("postgres://"):
        value = "postgresql+psycopg://" + value[len("postgres://"):]
    elif value.startswith("postgresql://") and "+psycopg" not in value:
        value = "postgresql+psycopg://" + value[len("postgresql://"):]
    return value


def create_app(test_config=None):
    load_dotenv()

    app_env = os.getenv("APP_ENV", "development").strip().lower()
    production = app_env == "production"

    secret_key = os.getenv("SECRET_KEY", "dev-change-me")
    if production and secret_key in {"", "dev-change-me"}:
        raise RuntimeError(
            "SECRET_KEY obrigatória em produção. "
            "Defina uma chave segura nas variáveis de ambiente."
        )

    app = Flask(__name__, instance_relative_config=True)
    app.config.update(
        SECRET_KEY=secret_key,
        SQLALCHEMY_DATABASE_URI=_database_url(),
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
        SQLALCHEMY_ENGINE_OPTIONS={
            "pool_pre_ping": True,
            "pool_recycle": 280,
        } if production else {},
        UPLOAD_FOLDER=os.path.abspath(
            os.getenv("UPLOAD_FOLDER", os.path.join(app.root_path, "uploads"))
        ),
        MAX_CONTENT_LENGTH=int(os.getenv("MAX_UPLOAD_MB", "10")) * 1024 * 1024,
        MAX_FORM_MEMORY_SIZE=2 * 1024 * 1024,
        MAX_FORM_PARTS=120,
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        SESSION_COOKIE_SECURE=production,
        SESSION_COOKIE_NAME="__Host-portalrh" if production else "portalrh_session",
        SESSION_REFRESH_EACH_REQUEST=True,
        REMEMBER_COOKIE_HTTPONLY=True,
        REMEMBER_COOKIE_SAMESITE="Lax",
        REMEMBER_COOKIE_SECURE=production,
        PERMANENT_SESSION_LIFETIME=int(os.getenv("SESSION_MINUTES", "480")) * 60,
        PREFERRED_URL_SCHEME="https" if production else "http",
        APP_ENV=app_env,
        PRODUCTION=production,
    )

    if test_config:
        app.config.update(test_config)

    if production:
        # Permite que Flask reconheça HTTPS/host corretamente atrás de proxy reverso
        # (Render, Railway, Nginx, etc.).
        app.wsgi_app = ProxyFix(
            app.wsgi_app,
            x_for=1,
            x_proto=1,
            x_host=1,
            x_port=1,
        )

    os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)
    os.makedirs(app.instance_path, exist_ok=True)

    db.init_app(app)
    login_manager.init_app(app)

    def format_minutes(value):
        value = int(value or 0)
        sign = "+" if value >= 0 else "-"
        total = abs(value)
        return f"{sign}{total // 60:02d}:{total % 60:02d}"

    app.jinja_env.filters["minutes_hhmm"] = format_minutes
    login_manager.login_view = "auth.login"
    login_manager.login_message = "Faça login para acessar o Portal RH."

    from .models import User

    @login_manager.user_loader
    def load_user(user_id):
        return db.session.get(User, int(user_id))

    from .auth import bp as auth_bp
    from .main import bp as main_bp
    from .rh import bp as rh_bp
    app.register_blueprint(auth_bp)
    app.register_blueprint(main_bp)
    app.register_blueprint(rh_bp)

    # ---------- CSRF simples para todos os POSTs ----------
    def csrf_token():
        token = session.get("_csrf_token")
        if not token:
            token = secrets.token_urlsafe(32)
            session["_csrf_token"] = token
        return token

    app.jinja_env.globals["csrf_token"] = csrf_token

    @app.before_request
    def security_before_request():
        from flask_login import current_user

        if request.method == "POST":
            expected = session.get("_csrf_token")
            received = request.form.get("_csrf_token") or request.headers.get("X-CSRF-Token")
            if not expected or not received or not secrets.compare_digest(expected, received):
                abort(400, description="Sessão de segurança inválida. Atualize a página e tente novamente.")

            # Segunda barreira contra requisições cross-site em produção.
            if app.config["PRODUCTION"]:
                origin = request.headers.get("Origin")
                if origin:
                    expected_origin = request.host_url.rstrip("/")
                    if origin.rstrip("/") != expected_origin:
                        abort(403)

        if current_user.is_authenticated:
            session.permanent = True
            allowed = {"auth.change_password", "auth.logout", "auth.login", "static"}
            if current_user.must_change_password and request.endpoint not in allowed:
                return redirect(url_for("auth.change_password"))
        return None

    # ---------- Segurança HTTP ----------
    @app.after_request
    def set_security_headers(response):
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Permissions-Policy"] = (
            "camera=(), microphone=(), geolocation=(), payment=(), usb=(), "
            "bluetooth=(), browsing-topics=()"
        )
        response.headers["Cross-Origin-Opener-Policy"] = "same-origin"
        response.headers["Cross-Origin-Resource-Policy"] = "same-origin"
        response.headers["X-Permitted-Cross-Domain-Policies"] = "none"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; "
            "img-src 'self' data: blob:; "
            "style-src 'self' 'unsafe-inline'; "
            "script-src 'self'; "
            "font-src 'self' data:; "
            "connect-src 'self'; "
            "media-src 'none'; "
            "object-src 'none'; "
            "worker-src 'none'; "
            "base-uri 'self'; "
            "frame-ancestors 'none'; "
            "form-action 'self'; "
            "upgrade-insecure-requests"
            if app.config["PRODUCTION"]
            else
            "default-src 'self'; img-src 'self' data: blob:; "
            "style-src 'self' 'unsafe-inline'; script-src 'self'; "
            "font-src 'self' data:; object-src 'none'; base-uri 'self'; "
            "frame-ancestors 'none'; form-action 'self'"
        )

        # Dados de RH não devem permanecer em caches compartilhados ou histórico intermediário.
        if request.path != "/health":
            response.headers["Cache-Control"] = "no-store, private, max-age=0, must-revalidate"
            response.headers["Pragma"] = "no-cache"
            response.headers["Expires"] = "0"

        if app.config["PRODUCTION"]:
            response.headers["Strict-Transport-Security"] = (
                "max-age=63072000; includeSubDomains; preload"
            )
        return response

    @app.route("/health")
    def health():
        # Endpoint mínimo para monitoramento da hospedagem, sem expor dados.
        try:
            db.session.execute(db.text("SELECT 1"))
            return {"status": "ok"}, 200
        except Exception:
            return {"status": "degraded"}, 503

    @app.errorhandler(400)
    def bad_request(_error):
        if request.path.startswith("/health"):
            return {"status": "bad_request"}, 400
        return (
            "<h1>Solicitação inválida</h1>"
            "<p>A requisição foi bloqueada por uma regra de segurança. "
            "Atualize a página e tente novamente.</p>",
            400,
            {"Content-Type": "text/html; charset=utf-8"},
        )

    @app.errorhandler(403)
    def forbidden(_error):
        return (
            "<h1>Acesso não autorizado</h1>"
            "<p>Seu usuário não possui permissão para acessar este recurso.</p>",
            403,
            {"Content-Type": "text/html; charset=utf-8"},
        )

    @app.errorhandler(404)
    def not_found(_error):
        return (
            "<h1>Página não encontrada</h1>",
            404,
            {"Content-Type": "text/html; charset=utf-8"},
        )

    @app.errorhandler(500)
    def internal_error(_error):
        db.session.rollback()
        return (
            "<h1>Não foi possível concluir esta operação</h1>"
            "<p>O erro foi interrompido com segurança. Tente novamente ou contate o RH.</p>",
            500,
            {"Content-Type": "text/html; charset=utf-8"},
        )

    @app.errorhandler(413)
    def too_large(_error):
        from flask import flash
        flash(
            f"Arquivo muito grande. Limite atual: {os.getenv('MAX_UPLOAD_MB', '10')} MB.",
            "danger",
        )
        return redirect(request.referrer or url_for("main.dashboard"))

    with app.app_context():
        # Mantido para compatibilidade com a base atual. Em produção, novas mudanças
        # estruturais continuam sendo feitas pelos scripts de migração versionados.
        db.create_all()

    return app
