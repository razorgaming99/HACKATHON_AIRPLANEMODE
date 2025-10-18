import re
import os
from flask import Flask, render_template, url_for, request, redirect
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from werkzeug.security import generate_password_hash, check_password_hash
from flask_mail import Mail, Message
from itsdangerous import URLSafeTimedSerializer, SignatureExpired
from flask_dance.contrib.google import make_google_blueprint, google
from openai import OpenAI
import oauthlib.oauth2.rfc6749.parameters
from flask import session
from flask_dance.consumer import oauth_authorized
from flask import flash 


db = SQLAlchemy()
login_manager = LoginManager()
mail = Mail()
s = URLSafeTimedSerializer("Z76sRi58peEjdjsScncr")
client = OpenAI(
  base_url="https://openrouter.ai/api/v1",
  api_key="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",)

old_validate = oauthlib.oauth2.rfc6749.parameters.validate_token_parameters
def new_validate(params):
    try:
        return old_validate(params)
    except Warning as w:
        if "Scope has changed" in str(w):
            return
        raise w

oauthlib.oauth2.rfc6749.parameters.validate_token_parameters = new_validate


class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(16), unique=True, nullable=False)
    full_name = db.Column(db.String(80), unique=True, nullable=True)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    phone = db.Column(db.String(20))
    address = db.Column(db.String(255))
    details = db.Column(db.Text)
    is_verified = db.Column(db.Boolean, default=False)
    role = db.Column(db.String(20), nullable=False, default="client")
    
    def __repr__(self):
        return f"<User {self.username}>"

def create_app():
    app = Flask(__name__)

    app.config['SECRET_KEY'] = 'jJC2vs3Bxdu4juQIWuqW'
    app.config['SQLALCHEMY_DATABASE_URI'] = "sqlite:///app.db"
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

    app.config['MAIL_SERVER'] = 'smtp.zoho.com'
    app.config['MAIL_PORT'] = 587
    app.config['MAIL_USE_TLS'] = True
    app.config['MAIL_USE_SSL'] = False
    app.config['MAIL_USERNAME'] = 'noreply@sidejobbanda.my.id'      
    app.config['MAIL_PASSWORD'] = 'v4zUUCZ9E7kY'
    app.config['MAIL_DEFAULT_SENDER'] = ('Sidejob Banda', 'noreply@sidejobbanda.my.id')
    app.config['MAIL_DEBUG'] = True
    
    app.config["GOOGLE_OAUTH_CLIENT_ID"] = "1013029711245-0ld664mod2dmrmagv02pbugoireeljqb.apps.googleusercontent.com"
    app.config["GOOGLE_OAUTH_CLIENT_SECRET"] = "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"
    app.config["OAUTHLIB_INSECURE_TRANSPORT"] = True
    os.environ["OAUTHLIB_INSECURE_TRANSPORT"] = "1"
    

    db.init_app(app)
    mail.init_app(app)
    mail.connection = None
    login_manager.init_app(app)
    login_manager.login_view = "login" 
    
    app.config["SESSION_PERMANENT"] = True
    app.config["SESSION_TYPE"] = "filesystem"
    import smtplib
    smtplib.SMTP.debuglevel = 1

    google_bp = make_google_blueprint(
        client_id=app.config["GOOGLE_OAUTH_CLIENT_ID"],
        client_secret=app.config["GOOGLE_OAUTH_CLIENT_SECRET"],
        scope=[
            "openid",
            "https://www.googleapis.com/auth/userinfo.email",
            "https://www.googleapis.com/auth/userinfo.profile",
            "https://www.googleapis.com/auth/user.birthday.read",
            "https://www.googleapis.com/auth/user.gender.read",
        ]
    )
    app.register_blueprint(google_bp, url_prefix="/login")
    
    @oauth_authorized.connect_via(google_bp)
    def google_logged_in(blueprint, token):
        if not token:
            print("⚠️ Google OAuth: no token received")
            return False

        resp = blueprint.session.get("/oauth2/v2/userinfo")
        if not resp.ok:
            print("⚠️ Google OAuth: failed to fetch userinfo:", resp.text)
            return False

        data = resp.json()
        email = data.get("email")

        print("✅ Google OAuth userinfo:", data)

        user = User.query.filter_by(email=email).first()
        if not user:
            user = User(
                username=email.split("@")[0],
                full_name=None,
                email=email,
                password_hash="google_oauth",
                is_verified=True,
            )
            db.session.add(user)
            db.session.commit()
            print("🆕 Created new Google user:", email)

        login_user(user)
        session.permanent = True
        print("🔐 Logged in:", email)

        flash("✅ Login berhasil dengan Google! Selamat datang kembali 👋", "success")

        return False

    
    @app.route("/login/google")
    def google_login():
        if not google.authorized:
            return redirect(url_for("google.login"))
        else:
            return redirect(url_for("dashboard"))
        

    @app.route("/profile", methods=["GET", "POST"])
    @login_required
    def profile():
        if request.method == "POST":
            current_user.full_name = request.form.get("full_name")
            current_user.username = request.form.get("username")
            current_user.email = request.form.get("email")
            current_user.phone = request.form.get("phone")
            current_user.address = request.form.get("address")
            current_user.details = request.form.get("details")
            db.session.commit()
            return redirect(url_for("profile"))
        return render_template("profile.html", user=current_user)

    @app.route("/health/db")
    def health_db(): 
        try:
            db.session.execute(text("SELECT 1"))
            return {"db": "ok"}, 200
        except Exception as e:
            return {"db": "error", "detail": str(e)}, 500

    with app.app_context():
        db.create_all()

    @app.route("/")
    def index():
        if current_user.is_authenticated:
            return redirect(url_for("dashboard"))
        return render_template("index.html")

    @app.route("/dashboard")
    @login_required
    def dashboard():
       # if current_user.role == "provider":
        #   return render_template("dashboard_provider.html")
       # else:
        #   return render_template("dashboard_client.html")
        return render_template("dashboard.html")


    @app.route("/register", methods=["GET", "POST"])
    def register():
        errors = []
        success = None 

        if request.method == "POST":
            username = (request.form.get("username") or "").strip()
            email = (request.form.get("email") or "").strip()
            password = request.form.get("password") or ""
            confirm = request.form.get("confirm_password") or ""
            role = request.form.get("role")


            if not (3 <= len(username) <= 80):
                errors.append("Username must be between 3 and 80 characters")
            if not re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", email):
                errors.append("Please enter a valid email address")
            if len(password) < 6:
                errors.append("Password needs to be at least 6 characters")
            if password != confirm:
                errors.append("Passwords don't match")

            if not errors:
                try:
                    print("💾 Menyimpan user ke database...")
                    pw_hash = generate_password_hash(password)
                    user = User(username=username, email=email, password_hash=pw_hash, role=role)
                    db.session.add(user)
                    db.session.commit()
                    print("✅ Data user tersimpan.")

                    token = s.dumps(email, salt="email-confirm")
                    link = url_for("confirm_email", token=token, _external=True)
                    print("🔗 Link verifikasi:", link)

                    msg = Message(
                        subject="Verifikasi Akunmu",
                        sender=("Sidejob Banda", app.config['MAIL_USERNAME']),
                        recipients=[email],
                        body=f"Halo {username}, klik link berikut untuk verifikasi akunmu:\n\n{link}\n\nTerima kasih telah bergabung!"
                    )
                    mail.send(msg)
                    print("📨 Email verifikasi terkirim!")

                    success = "Pendaftaran berhasil 🎉 Silakan cek email kamu untuk verifikasi sebelum login."
                    return render_template("login.html", success=success, errors=[])

                except IntegrityError as ie:
                    db.session.rollback()
                    print("⚠️ IntegrityError:", ie)
                    errors.append("That username or email is already registered.")

                except Exception as e:
                    print("❌ Gagal mengirim email:", e)
                    errors.append("Gagal mengirim email. Coba lagi nanti.")

        return render_template("register.html", errors=errors, success=success)

    @app.route("/ai-assist", methods=["GET", "POST"])
    def ai_assist():
        if request.method == "GET":
            return render_template("ai-assist.html")
    
        # Ambil input dari form
        user_text = (request.form.get("user_input") or "").strip()
        image_url = (request.form.get("image_url") or "").strip()
    
        # Buat prompt untuk AI
        prompt_text = f"{user_text}. Tolong balas dalam bahasa Indonesia."
        content_list = [{"type": "text", "text": prompt_text}]
        if image_url:
            content_list.append({"type": "image_url", "image_url": {"url": image_url}})
    
        answer = "⚠️ Memu sedang sibuk, coba beberapa saat lagi ya..."
    
        try:
            completion = client.chat.completions.create(
                model="openai/gpt-oss-20b:free",
                messages=[{"role": "user", "content": content_list}]
            )
            msg = completion.choices[0].message
            if isinstance(msg, dict):
                answer = msg.get("content", "⚠️ Tidak ada respons dari AI.")
            else:
                answer = str(msg)
        except Exception as e:
            print("AI ERROR:", e)
            if "Rate limit" in str(e):
                answer = "Batas harian model gratis sudah tercapai. Tambahkan kredit atau coba besok ya!"
            else:
                answer = "Terjadi kesalahan internal pada AI."
    
        # Kembalikan sebagai plain text
        return answer, 200, {"Content-Type": "text/plain; charset=utf-8"}


    
    @app.route("/verify/<token>")
    def confirm_email(token):
        try:
            email = s.loads(token, salt="email-confirm", max_age=3600)
        except SignatureExpired:
            return "<h1>❌ Link verifikasi sudah kadaluarsa.</h1>"

        user = User.query.filter_by(email=email).first_or_404()
        if user.is_verified:
            return "<h1>✅ Akun sudah diverifikasi sebelumnya.</h1>"

        user.is_verified = True
        db.session.commit()
        return render_template("verify_success.html", user=user)

    @app.route("/login", methods=["GET", "POST"])
    def login():
        errors = []
        if request.method == "POST":
            email = (request.form.get("email") or "").strip()
            password = request.form.get("password") or ""

            if not email:
                errors.append("Email is required")
            if not password:
                errors.append("Password is required")

            if not errors:
                user = User.query.filter_by(email=email).first()
                if not user or not check_password_hash(user.password_hash, password):
                    errors.append("Invalid email or password")
                elif not user.is_verified:
                    errors.append("Akun belum diverifikasi. Cek email kamu.")                    
                else:
                    login_user(user)
                    return redirect(url_for("dashboard"))

        return render_template("login.html", errors=errors)
    
    @app.route("/layanan")
    def layanan():
        return render_template("services.html")

    @app.route("/detail-pemesanan/<service>", methods=["GET", "POST"])
    @login_required
    def detail_pemesanan(service):
        if request.method == "POST":
            nama = request.form.get("nama")
            wa = request.form.get("wa")
            email = request.form.get("email")
            alamat = request.form.get("alamat")
            waktu = request.form.get("waktu")
            harga = request.form.get("harga")
            gender = request.form.get("gender")

            print(f"Pesanan dikonfirmasi: {nama}, {wa}, {email}, {alamat}, {service}, {waktu}, {harga}, {gender}")

            return redirect(url_for("order_success"))

        services = {
            "Home_Cleaning": {"name": "Home Cleaning", "price": "Rp. 150.000", "gender_default": "Wanita"},
            "Cuci_Gosok": {"name": "Cuci & Gosok", "price": "Rp. 80.000", "gender_default": "Wanita"},
            "Supir_Pribadi": {"name": "Supir Pribadi", "price": "Rp. 250.000", "gender_default": "Pria"},
        }

        s = services.get(service, {"name": "Layanan Tidak Diketahui", "price": "Rp. 0", "gender_default": "Wanita"})
        return render_template("detail_pemesanan.html", service_data=s)

    
    @app.route("/order_success")
    @login_required
    def order_success():
        return render_template("order_success.html")


    @app.route("/logout")
    def logout():
        logout_user()
        return redirect(url_for("index"))

    @login_manager.user_loader
    def load_user(user_id):
        return User.query.get(int(user_id))
    
    app.config["SESSION_COOKIE_SECURE"] = False
    app.config["SESSION_COOKIE_SAMESITE"] = "Lax"


    return app

if __name__ == "__main__":
    app = create_app()
    app.run(debug=True)
