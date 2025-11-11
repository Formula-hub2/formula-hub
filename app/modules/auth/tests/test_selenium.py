import time

import pyotp
from selenium.common.exceptions import NoSuchElementException
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys

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


# Call the test function
test_login_and_check_element()


def test_login_with_2fa_selenium():
    driver = initialize_driver()

    try:
        host = get_host_for_selenium_testing()

        # Abrir la página de login
        driver.get(f"{host}/login")
        time.sleep(2)

        # Encontrar campos de email y password
        email_field = driver.find_element(By.NAME, "email")
        password_field = driver.find_element(By.NAME, "password")

        # Datos de usuario con 2FA
        email_field.send_keys("user1@example.com")
        password_field.send_keys("1234")
        password_field.send_keys(Keys.RETURN)
        time.sleep(2)

        # Ahora debería redirigir a /verify_2fa
        assert "/verify_2fa" in driver.current_url

        # Obtener token TOTP desde la base de datos
        user = UserRepository().get_by_email("user1@example.com")
        totp = pyotp.TOTP(user.two_factor_secret).now()

        # Ingresar token en el formulario
        token_field = driver.find_element(By.NAME, "token")
        token_field.send_keys(totp)
        token_field.send_keys(Keys.RETURN)
        time.sleep(2)

        # Comprobar que se redirige a la página principal
        if "index" not in driver.current_url:
            raise AssertionError("2FA verification failed!")

    finally:
        close_driver(driver)
