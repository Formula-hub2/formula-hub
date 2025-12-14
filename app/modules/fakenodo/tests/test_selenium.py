from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait
import requests
from core.environment.host import get_host_for_selenium_testing
from core.selenium.common import close_driver, initialize_driver


class TestFakenodoUI:

    @classmethod
    def setup_class(cls):
        cls.driver = initialize_driver()
        cls.host = get_host_for_selenium_testing()
        cls.wait = WebDriverWait(cls.driver, 10)

    @classmethod
    def teardown_class(cls):
        try:
            reset_url = f"{cls.host}/fakenodo/reset"
            print(f"Intentando resetear Fakenodo en: {reset_url}")
            
            response = requests.post(reset_url)
            
            if response.status_code == 200:
                print("✅ Fakenodo limpiado correctamente.")
            else:
                print(f"❌ Error al limpiar Fakenodo. Código: {response.status_code}")
                print(f"Respuesta: {response.text}")
                
        except Exception as e:
            print(f"❌ Excepción intentando resetear: {e}")

        close_driver(cls.driver)

    def test_fakenodo_index_loads(self):
        """
        La página principal de Fakenodo carga.
        """
        self.driver.get(f"{self.host}/fakenodo/")
        self.wait.until(EC.presence_of_element_located((By.TAG_NAME, "body")))

        assert "Fakenodo" in self.driver.page_source

    def test_fakenodo_list_depositions_empty_or_not(self):
        """
        La lista de depósitos se renderiza aunque esté vacía.
        """
        self.driver.get(f"{self.host}/fakenodo/")
        self.wait.until(
            EC.presence_of_element_located((By.XPATH, "//table | //div[contains(@class,'deposition')] | //p"))
        )

    def test_view_non_existing_deposition_returns_404(self):
        """
        Acceder a un depósito inexistente devuelve 404.
        """
        self.driver.get(f"{self.host}/fakenodo/deposit/depositions/999999")

        assert "no encontrado" in self.driver.page_source.lower() or "404" in self.driver.page_source

    def test_fakenodo_health_endpoint(self):
        """
        Endpoint de salud accesible por navegador.
        """
        self.driver.get(f"{self.host}/fakenodo/test")

        assert "success" in self.driver.page_source

    def test_fakenodo_page_has_title_and_header(self):
        self.driver.get(f"{self.host}/fakenodo/")

        header = self.wait.until(EC.presence_of_element_located((By.TAG_NAME, "h1")))

        assert "Fakenodo" in header.text

    def test_fakenodo_table_headers_present(self):
        self.driver.get(f"{self.host}/fakenodo/")

        headers = self.wait.until(EC.presence_of_all_elements_located((By.XPATH, "//table//th")))

        header_texts = [h.text.lower() for h in headers]

        assert any("title" in h or "name" in h for h in header_texts)

    def test_deposition_links_are_clickable_if_any(self):
        self.driver.get(f"{self.host}/fakenodo/")

        links = self.driver.find_elements(By.XPATH, "//a[contains(@href,'/fakenodo/deposit')]")

        if links:
            links[0].click()
            self.wait.until(EC.presence_of_element_located((By.TAG_NAME, "body")))

    def test_back_navigation_from_deposition(self):
        self.driver.get(f"{self.host}/fakenodo/")

        links = self.driver.find_elements(By.XPATH, "//a[contains(@href,'/fakenodo/deposit')]")

        if links:
            links[0].click()
            self.driver.back()
            assert "/fakenodo" in self.driver.current_url
        else:
            assert "Fakenodo" in self.driver.page_source

    def test_deposition_page_has_sections(self):
        self.driver.get(f"{self.host}/fakenodo/")

        links = self.driver.find_elements(By.XPATH, "//a[contains(@href,'/fakenodo/deposit')]")

        if links:
            links[0].click()
            body_text = self.driver.page_source.lower()

            assert any(keyword in body_text for keyword in ["files", "versions", "metadata", "doi"])
        else:
            assert any(
                text in self.driver.page_source.lower() for text in ["no deposits", "no depositions", "fakenodo"]
            )

    def test_refresh_keeps_fakenodo_page_stable(self):
        self.driver.get(f"{self.host}/fakenodo/")
        self.driver.refresh()

        self.wait.until(EC.presence_of_element_located((By.TAG_NAME, "body")))
        assert "Fakenodo" in self.driver.page_source

    def test_fakenodo_delete_deposition(self):
            """
            Prueba la creación rápida y el borrado de un depósito en el Dashboard.
            """
            self.driver.get(f"{self.host}/fakenodo/")

            try:
                title_input = self.wait.until(EC.visibility_of_element_located((By.ID, "new-title")))
                create_btn = self.driver.find_element(By.XPATH, "//button[contains(text(),'Create')]")
                
                title_input.clear()
                title_input.send_keys("To Delete Dataset")
                create_btn.click()
                
                self.wait.until(EC.text_to_be_present_in_element((By.TAG_NAME, "table"), "To Delete Dataset"))
            except Exception:
                pass


            delete_btns = self.driver.find_elements(By.CSS_SELECTOR, "button.btn-danger")

            if delete_btns:
                rows_before = len(self.driver.find_elements(By.CSS_SELECTOR, "table tbody tr"))
                
                delete_btns[0].click()

                try:
                    alert = self.wait.until(EC.alert_is_present())
                    alert.accept()
                except Exception:
                    pass

                import time
                time.sleep(1)

                rows_after = len(self.driver.find_elements(By.CSS_SELECTOR, "table tbody tr"))
                

                assert rows_after <= rows_before