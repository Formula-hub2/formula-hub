import pyotp
from locust import HttpUser, TaskSet, events, task

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
# Definimos un secreto FIJO aquí. El script forzará que la DB tenga este valor al iniciar.
FIXED_SECRET = "VHZHTPR5ZSXR564A2XTZ56JSLUA4XNYK"


# --- SETUP INICIAL (SE EJECUTA UNA VEZ AL INICIO) ---
@events.test_start.add_listener
def on_test_start(environment, **kwargs):
    """
    Este método se ejecuta antes de empezar el test de carga.
    Se conecta a la DB, crea user4 si no existe y le ASIGNA el secreto fijo.
    """
    print("🚀 [SETUP] Iniciando preparación de datos para User4...")

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
        user = repo.get_by_email(USER_EMAIL)

        if user:
            # Como el modelo no tiene cascade delete, primero borramos sus sesiones manualmente
            if hasattr(user, "sessions") and user.sessions:
                try:
                    print(f"🧹 [TEARDOWN] Borrando {len(user.sessions)} sesiones activas...")
                    for session in user.sessions:
                        repo.session.delete(session)
                    repo.session.commit()
                except Exception as e:
                    print(f"⚠️ [TEARDOWN] Error borrando sesiones: {e}")
                    repo.session.rollback()

            # Ahora ya podemos borrar el usuario seguro
            repo.delete(user.id)
            print(f"🗑️ [TEARDOWN] Usuario {USER_EMAIL} eliminado correctamente.")
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
