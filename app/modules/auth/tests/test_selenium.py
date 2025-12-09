import time

import pyotp
from selenium.common.exceptions import NoSuchElementException, TimeoutException
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

from app import create_app  # <--- IMPORTANTE: Necesitas esto
from app.modules.auth.repositories import UserRepository
from core.environment.host import get_host_for_selenium_testing
from core.selenium.common import close_driver, initialize_driver


def test_login_and_check_element():

    driver = initialize_driver()

    try:
        host = get_host_for_selenium_testing()

        # Open the login page
        driver.get(f"{host}/login")

        # Wait a little while to make sure the page has loaded completely
        time.sleep(4)

        # Find the username and password field and enter the values
        email_field = driver.find_element(By.NAME, "email")
        password_field = driver.find_element(By.NAME, "password")

        email_field.send_keys("user2@example.com")
        password_field.send_keys("1234")

        # Send the form
        password_field.send_keys(Keys.RETURN)

        # Wait a little while to ensure that the action has been completed
        time.sleep(4)

        try:

            driver.find_element(By.XPATH, "//h1[contains(@class, 'h2 mb-3') and contains(., 'Latest datasets')]")
            print("Test passed!")

        except NoSuchElementException:
            raise AssertionError("Test failed!")

    finally:

        # Close the browser
        close_driver(driver)


def test_login_with_2fa_selenium():
    driver = initialize_driver()

    try:
        host = get_host_for_selenium_testing()

        # --- PREPARACIÓN DE DATOS ---
        # Creamos una instancia de la app solo para consultar/escribir en la DB
        flask_app = create_app()

        # Entramos en el contexto de la aplicación
        with flask_app.app_context():
            repo = UserRepository()
            user = repo.get_by_email("user3@example.com")

            # Si el usuario NO existe, lo creamos dinámicamente
            if not user:
                print("El usuario user3 no existe. Creando...")
                # Nota: Ajusta la clase User según los campos obligatorios de tu modelo
                user = repo.create(email="user3@example.com", password="1234")

            # Configurar 2FA
            # (Lo hacemos en un paso separado por si el usuario ya existía pero no tenía 2FA)
            if not user.two_factor_secret:
                user.two_factor_secret = pyotp.random_base32()
                user.two_factor_enabled = True
                repo.session.commit()

            # Guardamos el secreto en una variable para usarla fuera del contexto
            secret = user.two_factor_secret
        # --- FIN PREPARACION ---

        # Abrir la página de login
        driver.get(f"{host}/login")
        time.sleep(2)

        # Encontrar campos de email y password
        email_field = driver.find_element(By.NAME, "email")
        password_field = driver.find_element(By.NAME, "password")

        # Usamos los credenciales de user3 que aseguramos existen arriba
        email_field.send_keys("user3@example.com")
        password_field.send_keys("1234")
        password_field.send_keys(Keys.RETURN)
        time.sleep(2)

        # Ahora debería redirigir a /verify_2fa
        assert "/verify_2fa" in driver.current_url

        # Obtener token TOTP usando el secreto real de la DB
        totp = pyotp.TOTP(secret).now()

        # Ingresar token en el formulario
        token_field = driver.find_element(By.NAME, "token")
        token_field.send_keys(totp)
        token_field.send_keys(Keys.RETURN)
        time.sleep(2)

        # Comprobar que se redirige a la página principal
        try:
            driver.find_element(By.XPATH, "//h1[contains(@class, 'h2 mb-3') and contains(., 'Latest datasets')]")
            print("Test passed with user3!")

        except NoSuchElementException:
            raise AssertionError("Test failed!")

    finally:
        # TEARDOWN: Limpieza de la Base de Datos
        print("🧹 [TEARDOWN] Iniciando limpieza...")

        # Usamos un nuevo contexto para asegurar conexión limpia
        try:
            # Forzamos una nueva instancia de app para evitar sesiones cacheadas
            cleanup_app = create_app()
            with cleanup_app.app_context():
                repo = UserRepository()
                user_to_delete = repo.get_by_email("user3@example.com")

                if user_to_delete:
                    # A) Borrar sesiones activas primero (Evita IntegrityError)
                    # Verifica si el modelo tiene la relación 'sessions'
                    if hasattr(user_to_delete, "sessions") and user_to_delete.sessions:
                        for session in user_to_delete.sessions:
                            repo.session.delete(session)
                        repo.session.commit()

                    # B) Borrar el usuario
                    repo.delete(user_to_delete.id)
                    print(f"   - Usuario user3 (ID: {user_to_delete.id}) eliminado correctamente.")
                else:
                    print("   - El usuario user3 ya no existe.")

        except Exception as e:
            print(f"⚠️ [TEARDOWN ERROR] No se pudo limpiar la DB: {e}")

        close_driver(driver)


def test_limiter_selenium():
    driver = initialize_driver()
    wait = WebDriverWait(driver, 5)

    try:
        host = get_host_for_selenium_testing()
        login_url = f"{host}/login"
        driver.get(login_url)

        target_email = "user1@example.com"

        print("Iniciando prueba de fuerza bruta...")

        for i in range(1, 6):
            print(f"Intento fallido #{i}")

            try:
                email_field = wait.until(EC.presence_of_element_located((By.NAME, "email")))
                password_field = driver.find_element(By.NAME, "password")
            except TimeoutException:

                print(f"Alerta: No se encontró el campo email en el intento {i}. ¿Bloqueado antes de tiempo?")
                break

            email_field.clear()
            email_field.send_keys(target_email)

            password_field.clear()
            password_field.send_keys(f"wrong_password_{i}")

            password_field.send_keys(Keys.RETURN)

            time.sleep(0.5)

        print("Intento #6 (Debe estar bloqueado)...")

        try:
            email_field = wait.until(EC.presence_of_element_located((By.NAME, "email")))
            password_field = driver.find_element(By.NAME, "password")

            email_field.clear()
            email_field.send_keys(target_email)
            password_field.send_keys("1234")
            password_field.send_keys(Keys.RETURN)

            time.sleep(2)

        except TimeoutException:
            print("El formulario de login ya no aparece. Bloqueo exitoso.")

        try:
            wait_short = WebDriverWait(driver, 2)
            wait_short.until(
                EC.presence_of_element_located(
                    (By.XPATH, "//h1[contains(@class, 'h2 mb-3') and contains(., 'Latest datasets')]")
                )
            )
            raise AssertionError("FALLO DE SEGURIDAD: El usuario pudo entrar en el 6to intento.")
        except TimeoutException:
            print("Correcto: El usuario no pudo acceder al dashboard.")

        body_text = driver.find_element(By.TAG_NAME, "body").text
        expected_errors = ["Too many failed attempts", "blocked", "Try again later", "bloqueada"]

        if any(error in body_text for error in expected_errors):
            print("Test passed! Mensaje de bloqueo detectado.")
        else:
            print("Advertencia: Acceso denegado confirmado, pero sin mensaje explícito.")

    finally:
        close_driver(driver)


# Call the test function
# test_login_and_check_element()
# test_login_with_2fa_selenium()
# test_limiter_selenium()
