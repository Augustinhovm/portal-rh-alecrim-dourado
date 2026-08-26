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
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        SESSION_COOKIE_SECURE=production,
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
        response.headers["X-Frame-Options"] = "SAMEORIGIN"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = (
            "camera=(), microphone=(), geolocation=(), payment=()"
        )
        response.headers["Cross-Origin-Opener-Policy"] = "same-origin"
        # O Portal ainda possui alguns scripts/estilos inline; CSP compatível com a V8.0.
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; "
            "img-src 'self' data: blob:; "
            "style-src 'self' 'unsafe-inline'; "
            "script-src 'self' 'unsafe-inline'; "
            "font-src 'self' data:; "
            "object-src 'none'; "
            "base-uri 'self'; "
            "frame-ancestors 'self'; "
            "form-action 'self'"
        )
        if app.config["PRODUCTION"]:
            response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        return response

    @app.route("/health")
    def health():
        # Endpoint mínimo para monitoramento da hospedagem, sem expor dados.
        try:
            db.session.execute(db.text("SELECT 1"))
            return {"status": "ok"}, 200
        except Exception:
            return {"status": "degraded"}, 503

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
