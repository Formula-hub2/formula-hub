import os
import time

import pytest
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

from core.environment.host import get_host_for_selenium_testing
from core.selenium.common import close_driver, initialize_driver


class TestDatasetLifecycle:

    def setup_method(self):
        self.driver = initialize_driver()
        self.host = get_host_for_selenium_testing()
        self.wait = WebDriverWait(self.driver, 10)

    def teardown_method(self):
        close_driver(self.driver)

    def test_full_lifecycle(self):
        driver = self.driver
        wait = self.wait

        unique_suffix = str(time.time()).replace(".", "")[-6:]
        dataset_title = f"Selenium Test {unique_suffix}"

        print(f"\n🚀 Iniciando Test E2E: {dataset_title}")

        driver.get(f"{self.host}/login")
        try:
            email_field = wait.until(EC.visibility_of_element_located((By.NAME, "email")))
            email_field.clear()
            email_field.send_keys("user1@example.com")

            pass_field = driver.find_element(By.NAME, "password")
            pass_field.clear()
            pass_field.send_keys("1234")
            pass_field.send_keys(Keys.RETURN)

            wait.until(EC.url_changes(f"{self.host}/login"))
        except Exception as e:
            pytest.fail(f"Fallo en Login: {e}")

        driver.get(f"{self.host}/dataset/upload")

        wait.until(EC.visibility_of_element_located((By.NAME, "title"))).send_keys(dataset_title)
        driver.find_element(By.NAME, "desc").send_keys("Description for E2E test via Selenium")
        driver.find_element(By.NAME, "tags").send_keys("selenium, test")

        base_path = os.path.abspath(os.getcwd())
        file_path = os.path.join(base_path, "app/modules/dataset/uvl_examples/file1.uvl")

        if not os.path.exists(file_path):
            file_path = os.path.join(base_path, "dummy_test.uvl")
            with open(file_path, "w") as f:
                f.write("features\n    Root")

        try:
            dropzone_input = driver.find_element(By.CLASS_NAME, "dz-hidden-input")
            driver.execute_script(
                "arguments[0].style.visibility = 'visible'; arguments[0].style.display = 'block';", dropzone_input
            )
            dropzone_input.send_keys(file_path)

            wait.until(
                EC.visibility_of_element_located((By.XPATH, f"//h4[contains(text(), '{os.path.basename(file_path)}')]"))
            )

        except Exception as e:
            pytest.fail(f"Fallo subiendo archivo UVL: {e}")

        agree_checkbox = driver.find_element(By.ID, "agreeCheckbox")
        driver.execute_script("arguments[0].click();", agree_checkbox)

        upload_btn = driver.find_element(By.ID, "upload_button")
        wait.until(EC.element_to_be_clickable((By.ID, "upload_button")))
        driver.execute_script("arguments[0].click();", upload_btn)

        wait.until(EC.url_to_be(f"{self.host}/dataset/list"))

        try:
            dataset_link = wait.until(EC.element_to_be_clickable((By.LINK_TEXT, dataset_title)))
            dataset_link.click()
        except Exception:
            pytest.fail(f"No se encontró el dataset '{dataset_title}' en la lista mis datasets.")

        wait.until(EC.presence_of_element_located((By.ID, "download_count_text")))

        count_element = driver.find_element(By.ID, "download_count_text")
        initial_count = int(count_element.text.strip())
        print(f"   -> Contador Inicial: {initial_count}")

        download_btn = driver.find_element(By.ID, "download_btn")
        download_btn.click()

        wait.until(lambda d: int(d.find_element(By.ID, "download_count_text").text.strip()) == initial_count + 1)
        print("   -> Frontend JS Check: OK (El número subió visualmente)")

        try:
            wait.until(lambda d: d.get_cookie("download_cookie") is not None)
        except Exception:
            print("   Warning: No detecté la cookie 'download_cookie', continuando...")

        driver.refresh()

        count_element_after = wait.until(EC.visibility_of_element_located((By.ID, "download_count_text")))
        final_count = int(count_element_after.text.strip())

        print(f"   -> Contador tras Refresh (DB): {final_count}")

        assert (
            final_count == initial_count + 1
        ), f"ERROR: La base de datos no guardó el incremento. Inicio: {initial_count}, Final: {final_count}"
        download_btn = driver.find_element(By.ID, "download_btn")
        download_btn.click()
        driver.refresh()

        if "dummy_test.uvl" in file_path and os.path.exists(file_path):
            os.remove(file_path)

        print("✅ TEST COMPLETADO EXITOSAMENTE")
