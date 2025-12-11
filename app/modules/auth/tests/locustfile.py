import random
import re
import uuid

import pyotp
from locust import HttpUser, TaskSet, between, events, task

from app import create_app
from app.modules.auth.repositories import UserRepository
from core.environment.host import get_host_for_locust_testing
from core.locust.common import fake, get_csrf_token


class SignupBehavior(TaskSet):
    def on_start(self):
        self.signup()

    @task
    def signup(self):
        response = self.client.get("/signup")
        csrf_token = get_csrf_token(response)

        response = self.client.post(
            "/signup", data={"email": fake.email(), "password": fake.password(), "csrf_token": csrf_token}
        )
        if response.status_code != 200:
            print(f"Signup failed: {response.status_code}")


class LoginBehavior(TaskSet):
    def on_start(self):
        self.ensure_logged_out()
        self.login()

    @task
    def ensure_logged_out(self):
        response = self.client.get("/logout")
        if response.status_code != 200:
            print(f"Logout failed or no active session: {response.status_code}")

    @task
    def login(self):
        response = self.client.get("/login")
        if response.status_code != 200 or "Login" not in response.text:
            print("Already logged in or unexpected response, redirecting to logout")
            self.ensure_logged_out()
            response = self.client.get("/login")

        csrf_token = get_csrf_token(response)

        response = self.client.post(
            "/login", data={"email": "user1@example.com", "password": "1234", "csrf_token": csrf_token}
        )
        if response.status_code != 200:
            print(f"Login failed: {response.status_code}")


class AuthUser(HttpUser):
    tasks = [SignupBehavior, LoginBehavior]
    min_wait = 5000
    max_wait = 9000
    host = get_host_for_locust_testing()


# --- CONSTANTES DE CONFIGURACIÓN ---
USER_EMAIL = "user4@example.com"
USER_PASSWORD = "1234"

# --- CONSTANTES PARA SESIONES ACTIVAS ---
USER_EMAIL_SESSIONS = "sessions_user@example.com"
USER_PASSWORD_SESSIONS = "12345678"

# Definimos un secreto FIJO aquí. El script forzará que la DB tenga este valor al iniciar.
FIXED_SECRET = "VHZHTPR5ZSXR564A2XTZ56JSLUA4XNYK"


# --- SETUP INICIAL (SE EJECUTA UNA VEZ AL INICIO) ---
@events.test_start.add_listener
def on_test_start(environment, **kwargs):
    """
    Este método se ejecuta antes de empezar el test de carga.
    Se conecta a la DB, crea user4 si no existe y le ASIGNA el secreto fijo.
    """
    print("🚀 [SETUP] Iniciando preparación de datos para los usuarios...")

    flask_app = create_app()
    with flask_app.app_context():
        repo = UserRepository()
        user = repo.get_by_email(USER_EMAIL)

        # 1. Crear usuario si no existe
        if not user:
            print(f"👤 [SETUP] Creando usuario {USER_EMAIL}...")
            user = repo.create(email=USER_EMAIL, password=USER_PASSWORD)

        # 2. Forzar el secreto determinado
        # Esto es clave: actualizamos la DB para que coincida con nuestra constante
        needs_save = False

        if user.two_factor_secret != FIXED_SECRET:
            print("🔑 [SETUP] Actualizando secreto 2FA en DB para coincidir con el test...")
            user.two_factor_secret = FIXED_SECRET
            needs_save = True

        if not user.two_factor_enabled:
            print("🛡️ [SETUP] Activando 2FA para el usuario...")
            user.two_factor_enabled = True
            needs_save = True

        if needs_save:
            repo.session.add(user)
            repo.session.commit()
            print("✅ [SETUP] Base de datos sincronizada correctamente.")
        else:
            print("✅ [SETUP] El usuario ya estaba configurado correctamente.")

        user_sessions = repo.get_by_email(USER_EMAIL_SESSIONS)
        if not user_sessions:
            print(f"👤 [SETUP] Creando usuario sesiones {USER_EMAIL_SESSIONS}...")
            user_sessions = repo.create(email=USER_EMAIL_SESSIONS, password=USER_PASSWORD_SESSIONS)
            repo.session.commit()
            print(f"✅ [SETUP] Usuario sesiones {USER_EMAIL_SESSIONS} creado.")

        # Asegurar que NO tiene 2FA habilitado
        if getattr(user_sessions, "two_factor_enabled", False):
            print("🛡️ [SETUP] Deshabilitando 2FA para usuario de sesiones activas...")
            user_sessions.two_factor_enabled = False
            repo.session.commit()


# --- TEARDOWN FINAL (SE EJECUTA AL TERMINAR) ---
@events.test_stop.add_listener
def on_test_stop(environment, **kwargs):
    """
    Se ejecuta una sola vez al detenerse el test (por tiempo o Ctrl+C).
    Elimina el usuario de prueba para no dejar basura en la DB.
    """
    print("🧹 [TEARDOWN] Limpiando datos de prueba...")

    flask_app = create_app()
    with flask_app.app_context():
        repo = UserRepository()

        # 1. Limpiar usuario para sesiones activas
        user_sessions = repo.get_by_email(USER_EMAIL_SESSIONS)
        if user_sessions:
            print(f"🧹 [TEARDOWN] Limpiando usuario sesiones {USER_EMAIL_SESSIONS}...")

            # A. Buscar y eliminar perfil usando query directa
            try:
                from app.modules.profile.models import UserProfile

                profile = UserProfile.query.filter_by(user_id=user_sessions.id).first()
                if profile:
                    print(f"🧹 [TEARDOWN] Eliminando perfil ID {profile.id}...")
                    repo.session.delete(profile)
                    repo.session.commit()
            except Exception as e:
                print(f"⚠️ [TEARDOWN] Error eliminando perfil sesiones: {e}")
                repo.session.rollback()

            # B. Eliminar sesiones
            if hasattr(user_sessions, "sessions") and user_sessions.sessions:
                try:
                    print(f"🧹 [TEARDOWN] Borrando {len(user_sessions.sessions)} sesiones activas...")
                    for session in user_sessions.sessions:
                        repo.session.delete(session)
                    repo.session.commit()
                except Exception as e:
                    print(f"⚠️ [TEARDOWN] Error borrando sesiones: {e}")
                    repo.session.rollback()

            # C. Finalmente eliminar el usuario
            try:
                repo.delete(user_sessions.id)
                print(f"🗑️ [TEARDOWN] Usuario sesiones {USER_EMAIL_SESSIONS} eliminado correctamente.")
            except Exception as e:
                print(f"❌ [TEARDOWN] Error eliminando usuario sesiones: {e}")
                print("ℹ️  [TEARDOWN] El usuario podría tener referencias pendientes.")

        # 2. Limpiar usuario 2FA
        user = repo.get_by_email(USER_EMAIL)
        if user:
            print(f"🧹 [TEARDOWN] Limpiando usuario 2FA {USER_EMAIL}...")

            # A. Buscar y eliminar perfil usando query directa
            try:
                from app.modules.profile.models import UserProfile

                profile = UserProfile.query.filter_by(user_id=user.id).first()
                if profile:
                    print(f"🧹 [TEARDOWN] Eliminando perfil ID {profile.id}...")
                    repo.session.delete(profile)
                    repo.session.commit()
            except Exception as e:
                print(f"⚠️ [TEARDOWN] Error eliminando perfil 2FA: {e}")
                repo.session.rollback()

            # B. Eliminar sesiones
            if hasattr(user, "sessions") and user.sessions:
                try:
                    print(f"🧹 [TEARDOWN] Borrando {len(user.sessions)} sesiones activas...")
                    for session in user.sessions:
                        repo.session.delete(session)
                    repo.session.commit()
                except Exception as e:
                    print(f"⚠️ [TEARDOWN] Error borrando sesiones 2FA: {e}")
                    repo.session.rollback()

            # C. Finalmente eliminar el usuario
            try:
                repo.delete(user.id)
                print(f"🗑️ [TEARDOWN] Usuario {USER_EMAIL} eliminado correctamente.")
            except Exception as e:
                print(f"❌ [TEARDOWN] Error eliminando usuario 2FA: {e}")
                print("ℹ️  [TEARDOWN] El usuario podría tener referencias pendientes.")
        else:
            print(f"ℹ️ [TEARDOWN] El usuario {USER_EMAIL} no se encontró (¿ya eliminado?).")


class TwoFactorLoginBehavior(TaskSet):
    def on_start(self):
        """Al iniciar, aseguramos sesión limpia e intentamos el login completo"""
        self.ensure_logged_out()
        self.login_with_2fa()

    def ensure_logged_out(self):
        self.client.get("/logout")

    @task
    def login_with_2fa(self):
        # 1. Limpieza agresiva de cookies para forzar que nos pida 2FA
        self.client.cookies.clear()

        # 2. GET LOGIN
        response = self.client.get("/login")
        try:
            csrf_token_login = get_csrf_token(response)
        except ValueError:
            return  # Si falla aquí, reiniciamos

        # 3. POST CREDENCIALES
        # Nota: Importante no enviar cookies de device_id si queremos forzar el 2FA
        response = self.client.post(
            "/login", data={"email": USER_EMAIL, "password": USER_PASSWORD, "csrf_token": csrf_token_login}
        )

        # Caso A: Nos mandó al Index (Se saltó el 2FA o login normal)
        if "/verify_2fa" not in response.url:
            if response.status_code == 200:
                print(
                    f"⚠️ 2FA OMITIDO: El servidor nos mandó directo a {response.url}. "
                    "(Posible cookie device_id residual)"
                )
            else:
                print(f"❌ Login fallido. Status: {response.status_code}")
            return  # Terminamos esta tarea aquí, no intentamos buscar tokens que no existen

        # Caso B: Estamos correctamente en la pantalla de 2FA
        try:
            # Ahora sí es seguro buscar el token, porque sabemos que estamos en la página correcta
            csrf_token_2fa = get_csrf_token(response)
        except ValueError:
            print("❌ Estamos en /verify_2fa pero no veo el input hidden csrf_token.")
            return

        # Generar código usando la CONSTANTE FIJA. Como el setup ya forzó este secreto en la DB, siempre funcionará
        totp = pyotp.TOTP(FIXED_SECRET).now()

        response_final = self.client.post("/verify_2fa", data={"token": totp, "csrf_token": csrf_token_2fa})

        if response_final.status_code == 200 and "/verify_2fa" not in response_final.url:
            print("✅ 2FA Completado Exitosamente")
        else:
            print("❌ Fallo al enviar el código TOTP.")


class AuthUser2FA(HttpUser):
    # Ejecutamos solo el comportamiento de 2FA
    tasks = [TwoFactorLoginBehavior]
    min_wait = 5000
    max_wait = 9000
    host = get_host_for_locust_testing()


# TEST DE CARGA DE ACTIVE SESSIONS
class ActiveSessionsBehavior(TaskSet):
    def on_start(self):
        self.ensure_logged_out()
        self.login()

    def ensure_logged_out(self):
        self.client.get("/logout")
        self.client.cookies.clear()

    def login(self):
        response = self.client.get("/login")
        if response.status_code != 200:
            return False

        try:
            csrf_token = get_csrf_token(response)
        except ValueError:
            return False

        device_id = str(uuid.uuid4())

        response = self.client.post(
            "/login",
            data={"email": USER_EMAIL_SESSIONS, "password": USER_PASSWORD_SESSIONS, "csrf_token": csrf_token},
            headers={"User-Agent": f"Locust-Test-Agent/{device_id}", "Referer": self.user.host + "/login"},
        )

        if response.status_code == 200 or response.status_code == 302:
            response = self.client.get("/")
            if response.status_code == 200:
                return True
        return False

    @task
    def view_active_sessions(self):
        response = self.client.get("/active_sessions")

        if response.status_code == 200:

            session_ids = re.findall(r'session_id[\'"]?\s*:\s*[\'"]([^\'"]+)[\'"]', response.text)
            if session_ids:
                self.session_ids = session_ids
        elif response.status_code == 401:
            self.login()

    @task
    def create_multiple_sessions(self):
        import random

        devices = [
            {"agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"},
            {"agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"},
            {"agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 14_0 like Mac OS X)"},
        ]

        device = random.choice(devices)

        response = self.client.get("/login")
        try:
            csrf_token = get_csrf_token(response)
        except ValueError:
            return

        response = self.client.post(
            "/login",
            data={"email": USER_EMAIL_SESSIONS, "password": USER_PASSWORD_SESSIONS, "csrf_token": csrf_token},
            headers={"User-Agent": device["agent"], "Referer": self.user.host + "/login"},
        )

    @task
    def terminate_specific_session(self):
        response = self.client.get("/active_sessions")

        if response.status_code != 200:
            if self.login():
                response = self.client.get("/active_sessions")

        if response.status_code == 200:

            session_ids = re.findall(r'data-session-id[\'"]?\s*[:=]\s*[\'"]([^\'"]+)[\'"]', response.text)
            if not session_ids:
                session_ids = re.findall(r"session-(\w{8}-\w{4}-\w{4}-\w{4}-\w{12})", response.text)

            if session_ids and len(session_ids) > 1:
                session_id = session_ids[0]
                terminate_url = f"/terminate_session/{session_id}"
                response = self.client.get(terminate_url, allow_redirects=False)

    @task
    def navigation_with_active_sessions(self):
        import random

        pages = ["/", "/active_sessions", "/login"]
        page = random.choice(pages)
        self.client.get(page)


class ActiveSessionsUser(HttpUser):
    tasks = [ActiveSessionsBehavior]
    min_wait = 3000
    max_wait = 8000
    host = get_host_for_locust_testing()


# --- TEST LOGIN BRUTE FORCE ---

import random
import re
import uuid
from locust import HttpUser, TaskSet, between, events, task
from app import create_app
from app.modules.auth.repositories import UserRepository

# --- CONFIGURACIÓN DE USUARIOS ---
# 1. Usuario para pruebas de carga (SIEMPRE debe entrar bien)
USER_EMAIL_LOAD = "load_user@example.com"
USER_PASS_LOAD = "1234"

# 2. Usuario para pruebas de fuerza bruta (SERÁ bloqueado)
USER_EMAIL_BRUTE = "brute_user@example.com"
USER_PASS_BRUTE = "1234" # Contraseña real (aunque usaremos incorrectas)

# 3. Usuario para sesiones activas
USER_EMAIL_SESSIONS = "sessions_user@example.com"
USER_PASSWORD_SESSIONS = "12345678"

INVALID_PASSWORD = "wrong_password_"
FIXED_SECRET = "VHZHTPR5ZSXR564A2XTZ56JSLUA4XNYK"

# --- HELPER PARA CSRF ---
def get_csrf_token(response):
    """Extrae el token CSRF buscando el atributo name='csrf_token'"""
    match = re.search(r'name="csrf_token" type="hidden" value="([^"]+)"', response.text)
    if match:
        return match.group(1)
    # Intento alternativo por si cambia el orden de atributos
    match_alt = re.search(r'value="([^"]+)"[^>]*name="csrf_token"', response.text)
    if match_alt:
        return match_alt.group(1)
    return None

# --- SETUP INICIAL ---
@events.test_start.add_listener
def on_test_start(environment, **kwargs):
    print("🚀 [SETUP] Creando usuarios separados para Carga y Seguridad...")
    flask_app = create_app()
    with flask_app.app_context():
        repo = UserRepository()
        
        # 1. Configurar Usuario de Carga (Debe empezar LIMPIO)
        user_load = repo.get_by_email(USER_EMAIL_LOAD)
        if not user_load:
            user_load = repo.create(email=USER_EMAIL_LOAD, password=USER_PASS_LOAD)
        
        # Asegurar que no está bloqueado por tests anteriores
        user_load.failed_login_attempts = 0
        user_load.last_failed_login = None
        repo.session.add(user_load)
        repo.session.commit()

        # 2. Configurar Usuario para Fuerza Bruta
        user_brute = repo.get_by_email(USER_EMAIL_BRUTE)
        if not user_brute:
            user_brute = repo.create(email=USER_EMAIL_BRUTE, password=USER_PASS_BRUTE)
        
        # Este también debe empezar limpio para que el test funcione
        user_brute.failed_login_attempts = 0
        user_brute.last_failed_login = None
        repo.session.add(user_brute)
        repo.session.commit()

        print("✅ [SETUP] Usuarios listos.")

# --- CLASE BASE ---
class BaseLoginUser(HttpUser):
    abstract = True
    # Ajusta esto si tu puerto es diferente
    host = "http://localhost:5000" 
    wait_time = between(1, 3)

    def on_start(self):
        self.client.cookies.clear()
        self.device_id = str(uuid.uuid4())
        self.client.headers = {"User-Agent": f"LocustTestUser/{self.device_id}"}

    def get_login_token(self):
        resp = self.client.get("/login", name="/login [GET]")
        # Si redirige al index, hacemos logout
        if "/login" not in resp.url and resp.status_code == 200:
            self.client.get("/logout")
            resp = self.client.get("/login", name="/login [GET Retry]")
        
        return get_csrf_token(resp)

# --- USUARIO DE CARGA (LEGÍTIMO) ---
class LoadTestUser(BaseLoginUser):
    @task
    def login_success(self):
        token = self.get_login_token()
        if not token: return

        # Usamos el email de CARGA
        with self.client.post("/login", data={
            "email": USER_EMAIL_LOAD,
            "password": USER_PASS_LOAD,
            "csrf_token": token,
            "remember_me": "y"
        }, name="Login Success", catch_response=True) as response:
            
            if response.status_code == 200 and "/login" not in response.url:
                response.success()
                self.client.get("/logout")
            elif response.status_code == 429:
                # Si falla aquí, es el Flask-Limiter por IP, no por cuenta
                response.failure("Bloqueado por IP (429) - Revisa config de Flask-Limiter")
            else:
                response.failure(f"Fallo login: {response.status_code} URL: {response.url}")

# --- USUARIO DE ATAQUE (FUERZA BRUTA) ---
class BruteForceUser(BaseLoginUser):
    @task
    def login_bruteforce(self):
        token = self.get_login_token()
        if not token: return

        # Usamos el email de BRUTE
        fake_pass = f"{INVALID_PASSWORD}{random.randint(1,999)}"
        
        with self.client.post("/login", data={
            "email": USER_EMAIL_BRUTE,
            "password": fake_pass,
            "csrf_token": token,
            "remember_me": "n"
        }, name="Login BruteForce", catch_response=True) as response:
            
            if response.status_code == 429:
                # Éxito: El sistema nos bloqueó
                response.success()
            elif response.status_code == 200 and "Invalid credentials" in response.text:
                # Fallo normal, aún no bloqueado
                response.success()
            elif "/login" not in response.url:
                response.failure("¡ERROR! Entró con contraseña incorrecta")