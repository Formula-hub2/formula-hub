import os
import time

from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

from app import create_app, db
from app.modules.dataset.models import DataSet, DSMetaData
from core.environment.host import get_host_for_selenium_testing
from core.selenium.common import initialize_driver


class TestDatasetLifecycle:

    def setup_method(self):
        self.driver = initialize_driver()
        self.host = get_host_for_selenium_testing()
        self.wait = WebDriverWait(self.driver, 10)

    def teardown_method(self):
        if self.driver:
            self.driver.quit()

        app = create_app()
        with app.app_context():
            # Limpieza de base de datos
            datasets = DataSet.query.join(DSMetaData).filter(DSMetaData.title.like("%Selenium Test%")).all()
            for ds in datasets:
                db.session.delete(ds)
            db.session.commit()

    def test_upload_uvl_dataset(self):
        driver = self.driver
        dataset_title = "Selenium Test Dataset UVL"

        base_path = os.path.abspath(os.getcwd())
        file_path = os.path.join(base_path, "prueba_test.uvl")

        try:
            # Crear archivo dummy
            with open(file_path, "w", encoding="utf-8") as f:
                f.write("features\n    Root")

            # 1. LOGIN
            driver.get(f"{self.host}/login")
            time.sleep(2)

            driver.find_element(By.NAME, "email").send_keys("user2@example.com")
            driver.find_element(By.NAME, "password").send_keys("1234" + Keys.RETURN)
            time.sleep(2)

            assert "/login" not in driver.current_url, "Login falló"

            time.sleep(2)

            # 2. CREA EL DATASET
            driver.get(f"{self.host}/dataset/upload")
            time.sleep(2)

            # 3. COMPLETA EL FORMULARIO
            title_field = self.wait.until(EC.element_to_be_clickable((By.NAME, "title")))
            title_field.send_keys(dataset_title)
            driver.find_element(By.NAME, "desc").send_keys("Test description")
            driver.find_element(By.NAME, "tags").send_keys("test")

            # 4. SUBIR ARCHIVO
            dropzone_input = driver.find_element(By.CLASS_NAME, "dz-hidden-input")
            driver.execute_script(
                "arguments[0].style.visibility = 'visible'; arguments[0].style.display = 'block';", dropzone_input
            )
            dropzone_input.send_keys(file_path)

            self.wait.until(EC.visibility_of_element_located((By.CLASS_NAME, "dz-details")))

            # 5. ACEPTAR LOS TÉRMINOS
            agree_checkbox = driver.find_element(By.ID, "agreeCheckbox")
            driver.execute_script("arguments[0].click();", agree_checkbox)

            # 6. ENVIA EL FORMULARIO
            driver.execute_script("document.getElementById('upload_button').click();")
            time.sleep(2)

            # 7. VERIFICA QUE SE CREÓ
            driver.get(f"{self.host}/dataset/list")
            time.sleep(2)
            assert dataset_title in driver.page_source, "El dataset no fue creado correctamente."

        finally:
            if os.path.exists(file_path):
                os.remove(file_path)

    def test_upload_formula_dataset(self):
        driver = self.driver
        dataset_title = "Selenium Test Dataset Formula"

        base_path = os.path.abspath(os.getcwd())
        file_path = os.path.join(base_path, "prueba_test.csv")

        try:
            # Crear archivo dummy
            with open(file_path, "w", encoding="utf-8") as f:
                f.write("speed,rpm,gear\n200,11000,7\n210,11500,7")

            # 1. LOGIN
            driver.get(f"{self.host}/login")

            email_field = self.wait.until(EC.visibility_of_element_located((By.NAME, "email")))
            password_field = driver.find_element(By.NAME, "password")

            email_field.send_keys("user2@example.com")
            password_field.send_keys("1234")
            password_field.send_keys(Keys.RETURN)

            self.wait.until(EC.presence_of_element_located((By.XPATH, "//h1[contains(., 'Latest datasets')]")))

            # 2. IR A SUBIDA FORMULA
            driver.get(f"{self.host}/dataset/upload/formula")

            # 3. RELLENAR FORMULARIO
            title_field = self.wait.until(EC.visibility_of_element_located((By.NAME, "title")))
            title_field.send_keys(dataset_title)

            driver.find_element(By.NAME, "desc").send_keys("Description formula test")
            driver.find_element(By.NAME, "tags").send_keys("selenium, formula")

            # 4. SUBIR CSV
            file_input = driver.find_element(By.ID, "csv_file")
            file_input.send_keys(file_path)

            # 5. CHECKBOX Y SUBMIT
            agree_checkbox = driver.find_element(By.ID, "agreeCheckbox")
            driver.execute_script("arguments[0].click();", agree_checkbox)

            upload_btn = driver.find_element(By.ID, "upload_button")
            driver.execute_script("arguments[0].click();", upload_btn)

            # 6. VERIFICAR REDIRECCIÓN Y CREACIÓN
            self.wait.until(EC.url_contains("/dataset/list"))

        finally:
            if os.path.exists(file_path):
                os.remove(file_path)
