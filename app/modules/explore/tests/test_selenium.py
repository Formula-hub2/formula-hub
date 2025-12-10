import os
import time

from selenium import webdriver
from selenium.common.exceptions import NoAlertPresentException, TimeoutException
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.firefox.options import Options
from selenium.webdriver.firefox.service import Service
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait


class TestExploreSelenium:
    def setup_method(self, method):
        options = Options()
        options.binary_location = "/snap/firefox/current/usr/lib/firefox/firefox"

        log_path = os.path.join(os.getcwd(), "geckodriver.log")
        service = Service(log_output=log_path)
        self.driver = webdriver.Firefox(options=options, service=service)
        self.vars = {}

    def teardown_method(self, method):
        self.driver.quit()

    def test_exploreSelenium(self):
        self.driver.get("http://localhost:5000/")
        self.driver.set_window_size(1290, 741)

        self.driver.get("http://localhost:5000/login")

        email_input = WebDriverWait(self.driver, 10).until(EC.visibility_of_element_located((By.NAME, "email")))
        email_input.send_keys("user1@example.com")

        pass_input = self.driver.find_element(By.NAME, "password")
        pass_input.send_keys("1234")
        pass_input.send_keys(Keys.ENTER)

        WebDriverWait(self.driver, 10).until(EC.url_changes("http://localhost:5000/login"))

        self.driver.get("http://localhost:5000/explore")

        WebDriverWait(self.driver, 10).until(
            EC.element_to_be_clickable((By.CSS_SELECTOR, ".sidebar-item:nth-child(3) .align-middle:nth-child(2)"))
        ).click()

        add_btn = WebDriverWait(self.driver, 10).until(EC.element_to_be_clickable((By.ID, "add-btn-2")))
        add_btn.click()

        WebDriverWait(self.driver, 10).until(EC.text_to_be_present_in_element((By.ID, "cart-count-badge"), "1"))

        create_btn = WebDriverWait(self.driver, 10).until(EC.element_to_be_clickable((By.ID, "create-dataset-btn")))
        create_btn.click()

        unique_name = f"Dataset_{int(time.time())}"

        title_field = WebDriverWait(self.driver, 10).until(EC.visibility_of_element_located((By.ID, "dataset-title")))
        title_field.click()
        title_field.clear()
        title_field.send_keys(unique_name)

        self.driver.find_element(By.ID, "dataset-description").send_keys("Test description via Selenium")
        self.driver.find_element(By.ID, "dataset-tags").send_keys("tag2")

        save_btn = self.driver.find_element(By.CSS_SELECTOR, "#create-dataset-modal .btn-primary")
        self.driver.execute_script("arguments[0].click();", save_btn)

        try:
            WebDriverWait(self.driver, 10).until(EC.invisibility_of_element_located((By.ID, "create-dataset-modal")))
        except TimeoutException:
            try:
                alert = self.driver.switch_to.alert
                alert.accept()
            except NoAlertPresentException:
                pass
            self.driver.save_screenshot("login_failure.png")
            raise Exception("El modal sigue atascado. Verifica si el usuario y contraseña del script son correctos.")

        final_section = WebDriverWait(self.driver, 10).until(
            EC.element_to_be_clickable((By.ID, "my-selected-datasets-section"))
        )
        final_section.click()
