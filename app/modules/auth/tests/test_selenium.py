import time

import pyotp
from selenium.common.exceptions import NoSuchElementException
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys

from app import create_app  # <--- IMPORTANTE: Necesitas esto
from app.modules.auth.repositories import UserRepository, User
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


# VUELVE A EJECUTAR LA MISMA FUNCION
# Call the test function
# test_login_and_check_element()


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
        close_driver(driver)
