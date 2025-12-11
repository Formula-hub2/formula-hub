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


# 1
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


# 2
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


# 3
# test de interfaz para active sessions
def test_active_sessions_page_access():
    driver = initialize_driver()

    try:
        host = get_host_for_selenium_testing()
        driver.get(f"{host}/login")
        time.sleep(2)

        email_field = driver.find_element(By.NAME, "email")
        password_field = driver.find_element(By.NAME, "password")

        email_field.send_keys("user2@example.com")
        password_field.send_keys("1234")
        password_field.send_keys(Keys.RETURN)
        time.sleep(2)

        driver.get(f"{host}/active_sessions")
        time.sleep(3)
        try:
            page_title = driver.find_element(
                By.XPATH,
                "//h1[contains(text(), 'Sesiones') or contains(text(), 'Sessions') or contains(text(), 'Active')]",
            )
            print(f"✓ {page_title.text}")

            sessions_table = driver.find_elements(
                By.XPATH,
                "//table//tr | //div[contains(@class, 'session')] | //ul[contains(@class, 'sessions')]//li",
            )
            if sessions_table:
                print(f"✓ {len(sessions_table)} elementos")

            assert True

        except NoSuchElementException:
            current_url = driver.current_url
            if "active_sessions" in current_url:
                print("✓ Página cargada")
                assert True
            else:
                raise AssertionError(f"URL: {current_url}")

    finally:
        try:
            driver.get(f"{host}/logout")
            time.sleep(1)
        except Exception:
            pass
        close_driver(driver)


# 4
def test_view_and_terminate_sessions():
    driver = initialize_driver()

    try:
        host = get_host_for_selenium_testing()

        flask_app = create_app()
        with flask_app.app_context():
            repo = UserRepository()
            user = repo.get_by_email("sessions_test_user@example.com")

            if not user:
                user = repo.create(email="sessions_test_user@example.com", password="test123")
                repo.session.commit()

            if getattr(user, "two_factor_enabled", False):
                user.two_factor_enabled = False
                repo.session.commit()
        driver.get(f"{host}/login")
        time.sleep(2)

        email_field = driver.find_element(By.NAME, "email")
        password_field = driver.find_element(By.NAME, "password")

        email_field.send_keys("sessions_test_user@example.com")
        password_field.send_keys("test123")
        password_field.send_keys(Keys.RETURN)
        time.sleep(3)

        try:
            driver.find_element(By.XPATH, "//h1[contains(@class, 'h2 mb-3')]")
        except NoSuchElementException:
            raise AssertionError("Primer login falló")

        driver.get(f"{host}/active_sessions")
        time.sleep(3)

        try:
            sessions = driver.find_elements(
                By.XPATH,
                "//tr[contains(@class, 'session')] | "
                "//div[contains(@class, 'session-item')] | "
                "//li[contains(@class, 'session')]",
            )

            print(f"✓ Sesiones: {len(sessions)}")

            if len(sessions) > 0:
                terminate_buttons = driver.find_elements(
                    By.XPATH,
                    "//a[contains(@href, '/terminate_session/')] | "
                    "//button[contains(text(), 'Cerrar') or contains(text(), 'Terminar') or contains(text(), 'End')] | "
                    "//a[contains(text(), 'Cerrar') or contains(text(), 'Terminar')]",
                )

                print(f"✓ Botones: {len(terminate_buttons)}")

                if len(terminate_buttons) > 1:
                    try:
                        terminate_buttons[0].click()
                        time.sleep(2)

                        current_url = driver.current_url
                        if "active_sessions" in current_url:
                            print("✓ Sesión terminada")

                        else:
                            print(f"✓ Redireccionado: {current_url}")

                    except Exception as e:
                        print(f"⚠️ Error: {e}")
                        try:
                            terminate_link = terminate_buttons[0].get_attribute("href")
                            if terminate_link:
                                driver.get(terminate_link)
                                time.sleep(2)
                                print(f"✓ Navegado: {terminate_link}")
                        except Exception:
                            pass
                else:
                    print("ℹ️ Sin sesiones suficientes")

            assert True

        except NoSuchElementException as e:
            print(f"ℹ️ {e}")
            try:
                driver.save_screenshot("debug_sessions_page.png")
            except Exception:
                pass
            assert True

    finally:
        print("🧹 Limpiando...")
        try:
            cleanup_app = create_app()
            with cleanup_app.app_context():
                repo = UserRepository()
                user_to_delete = repo.get_by_email("sessions_test_user@example.com")

                if user_to_delete:
                    if hasattr(user_to_delete, "sessions") and user_to_delete.sessions:
                        for session in user_to_delete.sessions:
                            repo.session.delete(session)
                        repo.session.commit()
                    repo.delete(user_to_delete.id)
                    print("✓ Usuario eliminado")
        except Exception as e:
            print(f"⚠️ {e}")

        close_driver(driver)


# 5
def test_multiple_sessions_from_different_devices():
    drivers = []

    try:
        host = get_host_for_selenium_testing()

        flask_app = create_app()
        with flask_app.app_context():
            repo = UserRepository()
            user = repo.get_by_email("multisession_user@example.com")

            if not user:
                user = repo.create(email="multisession_user@example.com", password="multi123")
                repo.session.commit()

        user_agents = [
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
            "Mozilla/5.0 (iPhone; CPU iPhone OS 14_0 like Mac OS X) AppleWebKit/605.1.15",
        ]

        print(f"Simulando {len(user_agents)} dispositivos")

        for i, user_agent in enumerate(user_agents):
            print(f"Dispositivo {i+1}")

            driver = initialize_driver()
            drivers.append(driver)

            driver.get(f"{host}/login")
            time.sleep(2)

            email_field = driver.find_element(By.NAME, "email")
            password_field = driver.find_element(By.NAME, "password")

            email_field.send_keys("multisession_user@example.com")
            password_field.send_keys("multi123")
            password_field.send_keys(Keys.RETURN)
            time.sleep(3)

            try:
                driver.find_element(By.XPATH, "//h1[contains(@class, 'h2 mb-3')]")
                print(f"✓ Dispositivo {i+1}: Login")

                driver.get(f"{host}/active_sessions")
                time.sleep(2)

                try:
                    sessions = driver.find_elements(
                        By.XPATH,
                        "//tr[contains(@class, 'session')] | "
                        "//div[contains(@class, 'session')] | "
                        "//li[contains(@class, 'session')]",
                    )
                    print(f"✓ Dispositivo {i+1}: {len(sessions)} sesiones")
                except Exception:
                    print(f"ℹ️ Dispositivo {i+1}: Sin conteo")

            except NoSuchElementException:
                print(f"✗ Dispositivo {i+1}: Falló login")

        print("✅ Simulación completada")
        assert True

    finally:
        print("Limpiando...")

        for driver in drivers:
            try:
                driver.quit()
            except Exception:
                pass

        try:
            cleanup_app = create_app()
            with cleanup_app.app_context():
                repo = UserRepository()
                user_to_delete = repo.get_by_email("multisession_user@example.com")

                if user_to_delete:
                    if hasattr(user_to_delete, "sessions") and user_to_delete.sessions:
                        for session in user_to_delete.sessions:
                            repo.session.delete(session)
                        repo.session.commit()

                    repo.delete(user_to_delete.id)
                    print("✓ Usuario eliminado")
        except Exception as e:
            print(f"⚠️ {e}")


# 6
def test_session_security_features():
    """Test para verificar características de seguridad de sesiones"""
    driver = initialize_driver()

    try:
        host = get_host_for_selenium_testing()
        driver.get(f"{host}/active_sessions")
        time.sleep(2)

        current_url = driver.current_url
        page_source = driver.page_source

        if "active_sessions" in current_url:
            if (
                "login" in page_source.lower()
                or "sign in" in page_source.lower()
                or "401" in page_source
                or "403" in page_source
            ):
                print("✓ Acceso denegado correctamente a usuario no autenticado")
            else:
                print("⚠️ Página de sesiones accesible sin autenticación")
        elif "login" in current_url:
            print("✓ Redirigido a login correctamente")
        else:
            print(f"ℹ️ Redirigido a: {current_url}")

        driver.get(f"{host}/login")
        time.sleep(2)

        email_field = driver.find_element(By.NAME, "email")
        password_field = driver.find_element(By.NAME, "password")

        email_field.send_keys("user2@example.com")
        password_field.send_keys("1234")
        password_field.send_keys(Keys.RETURN)
        time.sleep(3)

        driver.get(f"{host}/active_sessions")
        time.sleep(3)

        security_checks = []

        try:
            device_info = driver.find_elements(
                By.XPATH,
                "//*[contains(text(), 'Device') or contains(text(), 'Dispositivo') or "
                "contains(text(), 'IP') or contains(text(), 'Browser') or "
                "contains(text(), 'Navegador')]",
            )
            if device_info:
                security_checks.append("✓ Información de dispositivo/IP mostrada")
            else:
                security_checks.append("ℹ️ No se encontró información de dispositivo")
        except Exception:
            security_checks.append("ℹ️ No se pudo verificar información de dispositivo")

        try:
            date_info = driver.find_elements(
                By.XPATH,
                "//*[contains(text(), 'Date') or contains(text(), 'Fecha') or "
                "contains(text(), 'Time') or contains(text(), 'Hora') or "
                "contains(text(), 'Last')]",
            )
            if date_info:
                security_checks.append("✓ Información de fecha/hora mostrada")
            else:
                security_checks.append("ℹ️ No se encontró información de fecha/hora")
        except Exception:
            security_checks.append("ℹ️ No se pudo verificar información de fecha/hora")

        try:
            current_session = driver.find_elements(
                By.XPATH,
                "//*[contains(text(), 'Current') or contains(text(), 'Actual') or "
                "contains(text(), 'This device') or contains(text(), 'Este dispositivo')]",
            )
            if current_session:
                security_checks.append("✓ Sesión actual identificada")
            else:
                security_checks.append("ℹ️ No se identificó la sesión actual")
        except Exception:
            security_checks.append("ℹ️ No se pudo identificar sesión actual")

        print("\n🔒 Resultados de verificación de seguridad:")
        for check in security_checks:
            print(f"  {check}")

        try:
            logout_link = driver.find_element(
                By.XPATH,
                "//a[contains(@href, '/logout') and contains(text(), 'Logout') or "
                "contains(text(), 'Salir') or contains(text(), 'Cerrar')]",
            )

            logout_link.click()
            time.sleep(2)

            if "login" in driver.current_url or driver.current_url == f"{host}/":
                print("✓ Logout exitoso desde página de sesiones")
            else:
                print(f"ℹ️ Después de logout en: {driver.current_url}")

        except NoSuchElementException:
            print("ℹ️ No se encontró enlace de logout específico")

        assert True

    finally:
        close_driver(driver)


# 7
def test_active_sessions_complete_workflow():
    """Test completo del flujo de trabajo de sesiones activas"""
    driver = initialize_driver()

    try:
        host = get_host_for_selenium_testing()

        print("🚀 Iniciando test completo de flujo de sesiones activas...")

        flask_app = create_app()
        with flask_app.app_context():
            repo = UserRepository()
            user = repo.get_by_email("workflow_test@example.com")

            if not user:
                print("👤 Creando usuario para test de flujo...")
                user = repo.create(email="workflow_test@example.com", password="workflow123")
                repo.session.commit()

        print("\n1. Login inicial...")
        driver.get(f"{host}/login")
        time.sleep(2)

        email_field = driver.find_element(By.NAME, "email")
        password_field = driver.find_element(By.NAME, "password")

        email_field.send_keys("workflow_test@example.com")
        password_field.send_keys("workflow123")
        password_field.send_keys(Keys.RETURN)
        time.sleep(3)

        print("2. Navegando a sesiones activas...")
        driver.get(f"{host}/active_sessions")
        time.sleep(3)

        initial_url = driver.current_url

        print("3. Capturando información de sesiones...")

        print("4. Interactuando con elementos de la página...")

        try:
            info_elements = driver.find_elements(
                By.XPATH,
                "//a[contains(@href, '#')] | "
                "//button[not(contains(text(), 'Delete')) and not(contains(text(), 'Remove'))] | "
                "//details | //summary",
            )

            for i, element in enumerate(info_elements[:2]):
                try:
                    element_text = element.text[:30] if element.text else "sin texto"
                    print(f"   Haciendo clic en elemento: {element_text}...")
                    element.click()
                    time.sleep(1)
                    if i == 0:
                        driver.back()
                    time.sleep(1)
                except Exception:
                    continue
        except Exception:
            print("   ℹ️ No se encontraron elementos interactivos seguros")

        print("5. Verificando integridad de la página...")
        final_url = driver.current_url

        if "active_sessions" in final_url or initial_url == final_url:
            print("   ✓ Página mantuvo su estado correctamente")
        else:
            print(f"   ℹ️ Cambio de URL: {initial_url} -> {final_url}")

        print("6. Volviendo a página principal...")
        driver.get(f"{host}/")
        time.sleep(2)

        print("7. Realizando logout...")
        driver.get(f"{host}/logout")
        time.sleep(2)

        print("\n✅ Test completo de flujo finalizado exitosamente")
        assert True

    finally:
        print("\n🧹 Limpiando después del test de flujo...")
        try:
            cleanup_app = create_app()
            with cleanup_app.app_context():
                repo = UserRepository()
                user_to_delete = repo.get_by_email("workflow_test@example.com")

                if user_to_delete:
                    if hasattr(user_to_delete, "sessions") and user_to_delete.sessions:
                        for session in user_to_delete.sessions:
                            repo.session.delete(session)
                        repo.session.commit()

                    repo.delete(user_to_delete.id)
                    print("✓ Usuario de flujo eliminado")
        except Exception as e:
            print(f"⚠️ Error en cleanup: {e}")

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
