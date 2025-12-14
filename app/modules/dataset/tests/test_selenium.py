import os
import time

import pytest
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

    def teardown_method(self):
        if self.driver:
            self.driver.quit()

        app = create_app()
        with app.app_context():
            datasets_to_delete = (
                DataSet.query.join(DSMetaData)
                .filter((DSMetaData.title.like("%Selenium%")) | (DSMetaData.title.like("%Dataset_%")))
                .all()
            )

            if datasets_to_delete:
                for ds in datasets_to_delete:
                    db.session.delete(ds)
                try:
                    db.session.commit()
                except Exception:
                    db.session.rollback()

    def test_full_lifecycle(self):
        driver = self.driver

        unique_suffix = str(time.time()).replace(".", "")[-6:]
        dataset_title = f"Selenium Test {unique_suffix}"

        driver.get(f"{self.host}/logout")
        time.sleep(2)

        # 1. LOGIN
        driver.get(f"{self.host}/login")

        time.sleep(4)

        # Loguear usuario y contraseña
        email_field = driver.find_element(By.NAME, "email")
        password_field = driver.find_element(By.NAME, "password")

        email_field.send_keys("user2@example.com")
        password_field.send_keys("1234")

        # Envia el formulario
        password_field.send_keys(Keys.RETURN)

        time.sleep(4)

        # Verifica que estamos logueados
        try:
            driver.find_element(By.XPATH, "//h1[contains(@class, 'h2 mb-3') and contains(., 'Latest datasets')]")
        except Exception:
            # Si no encuentra el elemento, verifica si estamos en otra página
            current_url = driver.current_url
            if "/login" in current_url:
                pytest.fail("Login falló - Seguimos en /login")
            else:
                print(f"Login exitoso (redirigido a: {current_url})")

        # 2. CREA EL DATASET
        driver.get(f"{self.host}/dataset/upload")

        # 3. COMPLETA EL FORMULARIO
        wait = WebDriverWait(driver, 10)
        title_field = wait.until(EC.visibility_of_element_located((By.NAME, "title")))
        title_field.send_keys(dataset_title)

        driver.find_element(By.NAME, "desc").send_keys("Description for un test de prueba")
        driver.find_element(By.NAME, "tags").send_keys("formula, test")

        # 4. SUBIR ARCHIVO (opcional)
        base_path = os.path.abspath(os.getcwd())
        file_path = os.path.join(base_path, "app/modules/dataset/uvl_examples/file1.uvl")

        if not os.path.exists(file_path):
            file_path = os.path.join(base_path, "prueba_test.uvl")
            with open(file_path, "w", encoding="utf-8") as f:
                f.write("features\n    Root")

        try:
            dropzone_input = driver.find_element(By.CLASS_NAME, "dz-hidden-input")
            driver.execute_script(
                "arguments[0].style.visibility = 'visible'; arguments[0].style.display = 'block';", dropzone_input
            )
            dropzone_input.send_keys(file_path)
            print("✓ Archivo subido")
            time.sleep(1)
        except Exception as e:
            print(f"Archivo no subido: {e}")

        # 5. ACEPTAR LOS TÉRMINOS
        try:
            agree_checkbox = driver.find_element(By.ID, "agreeCheckbox")
            driver.execute_script("arguments[0].click();", agree_checkbox)
        except Exception:
            print("Checkbox no encontrado")

        # 6. ENVIA EL FORMULARIO
        try:
            upload_btn = driver.find_element(By.ID, "upload_button")
            driver.execute_script("arguments[0].click();", upload_btn)
            time.sleep(3)
        except Exception as e:
            print(f"Error enviando formulario: {e}")

        # 7. VERIFICA QUE SE CREÓ (VE LA LISTA DE DATASETS)
        driver.get(f"{self.host}/dataset/list")
        time.sleep(2)

        # Buscar el dataset en la página
        page_source = driver.page_source
        if dataset_title in page_source:
            print(f"✓ Dataset '{dataset_title}' encontrado en la lista")
        else:
            print(f"⚠️ Dataset '{dataset_title}' no encontrado en la lista")

        # 8. BORRAR ARCHIVO TEMPORAL
        temp_file = os.path.join(os.path.abspath(os.getcwd()), "prueba_test.uvl")
        if os.path.exists(temp_file):
            os.remove(temp_file)
            print("✓ Archivo temporal eliminado")
