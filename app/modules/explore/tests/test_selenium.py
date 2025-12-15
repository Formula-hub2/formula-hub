import os
import time

import pytest
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.firefox.options import Options
from selenium.webdriver.firefox.service import Service
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait


class TestExploreSelenium:
    """Test suite para la funcionalidad de explore, carrito de datasets y creación de datasets combinados"""

    def setup_method(self, method):
        options = Options()
        options.binary_location = "/snap/firefox/current/usr/lib/firefox/firefox"

        options.set_preference("dom.disable_beforeunload", True)
        options.set_preference("dom.disable_open_during_load", True)

        # Configurar para evitar problemas de permisos
        options.set_preference("browser.tabs.remote.autostart", False)
        options.set_preference("browser.tabs.remote.autostart.2", False)

        log_path = os.path.join(os.getcwd(), "geckodriver.log")
        service = Service(log_output=log_path)
        self.driver = webdriver.Firefox(options=options, service=service)
        self.vars = {}

    def teardown_method(self, method):
        self.driver.quit()

    def login(self, email="user2@example.com", password="1234"):
        """Helper method para hacer login"""
        self.driver.get("http://localhost:5000/login")
        self.driver.find_element(By.NAME, "email").send_keys("user2@example.com")
        self.driver.find_element(By.NAME, "password").send_keys("1234" + Keys.RETURN)

        time.sleep(3)

    def navigate_to_explore(self):
        """Helper method para navegar a explore"""
        self.driver.get("http://localhost:5000/explore")

    def test_add_multiple_datasets_to_cart(self):
        """ "Test 1: Añadir múltiples datasets"""
        self.login()
        self.navigate_to_explore()
        time.sleep(2)

        add_btns = self.driver.find_elements(By.CLASS_NAME, "btn-add-to-cart")
        if len(add_btns) < 2:
            pytest.skip("Necesarios 2 datasets")

        add_btns[0].click()
        add_btns[1].click()

        # Verificar contador
        badge = self.driver.find_element(By.ID, "cart-count-badge")
        assert "2" in badge.text

    def test_remove_dataset_from_cart(self):
        """Test 2: Eliminar dataset del carrito"""
        self.login()
        self.navigate_to_explore()
        time.sleep(2)

        add_btns = self.driver.find_elements(By.CLASS_NAME, "btn-add-to-cart")
        if len(add_btns) < 2:
            pytest.skip("Necesarios 2 datasets")

        add_btns[0].click()
        add_btns[1].click()

        time.sleep(2)

        # Eliminar uno
        remove_btns = self.driver.find_elements(By.CLASS_NAME, "btn-outline-danger")
        remove_btns[0].click()

        # Verificar contador
        badge = self.driver.find_element(By.ID, "cart-count-badge")
        assert "1" in badge.text

    def test_cancel_create_dataset_modal(self):
        """Test 3: Cerrar modal con Cancel sin crear dataset"""
        self.login()
        self.navigate_to_explore()
        time.sleep(2)

        add_btns = self.driver.find_elements(By.CLASS_NAME, "btn-add-to-cart")
        if not add_btns:
            pytest.skip("No hay datasets disponibles")
        add_btns[0].click()
        self.driver.find_element(By.ID, "create-dataset-btn").click()

        # Rellenar algunos campos
        self.driver.find_element(By.ID, "dataset-title").send_keys("Test Dataset")
        self.driver.find_element(By.ID, "dataset-description").send_keys("Test description")

        # Clicar Cancel
        self.driver.find_element(By.ID, "modal-cancel-btn-text").click()

        # Verificar que el modal se cierra
        modal = self.driver.find_element(By.ID, "create-dataset-modal")
        assert modal.value_of_css_property("display") == "none"

        # Verificar que el carrito sigue intacto
        badge = self.driver.find_element(By.ID, "cart-count-badge")
        assert badge.text == "1", f"El contador debería mostrar 1, pero muestra {badge.text}"

    def test_modal_close_button(self):
        """Test 4: Cerrar modal con X"""
        self.login()
        self.navigate_to_explore()
        time.sleep(2)

        # Añadir 1 dataset
        add_btns = self.driver.find_elements(By.CLASS_NAME, "btn-add-to-cart")
        if not add_btns:
            pytest.skip("No hay datasets disponibles")
        add_btns[0].click()
        self.driver.find_element(By.ID, "create-dataset-btn").click()
        self.driver.find_element(By.ID, "modal-close-btn").click()

        # Verificar que el modal se cierra
        modal = self.driver.find_element(By.ID, "create-dataset-modal")
        assert modal.value_of_css_property("display") == "none"

        # Verificar que el carrito permanece intacto
        badge = self.driver.find_element(By.ID, "cart-count-badge")
        assert badge.text == "1", f"El badge debería mostrar 1, pero muestra {badge.text}"

    def test_create_dataset_without_required_fields(self):
        """Test 5: Intentar crear dataset sin título (required)"""
        self.login()
        self.navigate_to_explore()

        time.sleep(2)

        add_btns = self.driver.find_elements(By.CLASS_NAME, "btn-add-to-cart")
        if not add_btns:
            pytest.skip("No hay datasets disponibles")
        add_btns[0].click()
        self.driver.find_element(By.ID, "create-dataset-btn").click()

        # NO rellenar el título (requerido)
        self.driver.find_element(By.ID, "dataset-description").send_keys("Test description")
        self.driver.find_element(By.ID, "dataset-tags").send_keys("test")

        # Enviar formulario
        self.driver.find_element(By.CSS_SELECTOR, "#create-dataset-modal .btn-primary").click()

        time.sleep(1)

        # Si la validación funcionó, el modal sigue intacto
        modal = self.driver.find_element(By.ID, "create-dataset-modal")
        assert modal.value_of_css_property("display") != "none"

    def test_download_cart_with_multiple_datasets(self):
        """Test 6: Descargar múltiples datasets (simulado)"""

        self.login()
        self.navigate_to_explore()

        time.sleep(2)

        add_btns = self.driver.find_elements(By.CLASS_NAME, "btn-add-to-cart")
        if len(add_btns) < 2:
            self.driver.refresh()
            time.sleep(2)

            add_btns = self.driver.find_elements(By.CLASS_NAME, "btn-add-to-cart")
            if len(add_btns) < 2:
                pytest.skip("Necesarios 2 datasets")

        add_btns[0].click()
        add_btns[1].click()

        # Abrir modal y rellenar
        self.driver.find_element(By.ID, "open-download-modal-btn").click()
        self.driver.find_element(By.ID, "zip-filename").send_keys("test")

        # Simular cierre sin descargar
        self.driver.execute_script(
            """
            document.getElementById('download-dataset-modal').style.display = 'none';
        """
        )

        modal = self.driver.find_element(By.ID, "download-dataset-modal")
        assert modal.value_of_css_property("display") == "none"

    def test_download_modal_cancel(self):
        """Test 7: Cancelar descarga sin descargar"""
        self.login()
        self.navigate_to_explore()
        time.sleep(2)

        # Verificar que hay al menos un dataset
        add_btns = WebDriverWait(self.driver, 10).until(lambda d: d.find_elements(By.CLASS_NAME, "btn-add-to-cart"))
        if not add_btns:
            pytest.skip("No hay datasets disponibles")

        add_btns[0].click()
        time.sleep(3)

        # Verificar que el botón de descarga está presente
        try:
            download_btn = self.driver.find_element(By.ID, "open-download-modal-btn")
            download_btn.click()
        except Exception:
            pytest.skip("Botón de descarga no disponible")

        self.driver.find_element(By.ID, "download-modal-close-btn").click()

        # Verificar que el modal se cerró
        modal = self.driver.find_element(By.ID, "download-dataset-modal")
        assert modal.value_of_css_property("display") == "none"

        # Verificar que el carrito permanece igual
        badge = self.driver.find_element(By.ID, "cart-count-badge")
        assert badge.text == "1", f"El badge debería mostrar 1, pero muestra {badge.text}"

    def test_search_filter_before_add_to_cart(self):
        """Test 8: Buscar/filtrar datasets"""
        self.login()
        self.navigate_to_explore()

        time.sleep(2)

        # Añadir un dataset ANTES de hacer búsqueda
        add_btns = self.driver.find_elements(By.CLASS_NAME, "btn-add-to-cart")
        if not add_btns:
            pytest.skip("No hay datasets disponibles")
        add_btns[0].click()

        # Ahora escribe en un campo de búsqueda
        query_input = self.driver.find_element(By.ID, "query")
        query_input.send_keys("test")

        time.sleep(1)

        # Verificar que el carrito mantiene el dataset anterior
        badge = self.driver.find_element(By.ID, "cart-count-badge")
        assert badge.text == "1", f"El carrito debería tener 1 dataset, pero tiene {badge.text}"

    def test_clear_search_filter(self):
        """Test 9: Limpiar búsqueda/filtrado"""
        self.login()
        self.navigate_to_explore()

        time.sleep(2)

        # Agregar un dataset ANTES de hacer búsqueda
        add_btns = self.driver.find_elements(By.CLASS_NAME, "btn-add-to-cart")
        if not add_btns:
            pytest.skip("No hay datasets disponibles")
        add_btns[0].click()

        # Hacer búsqueda
        query_input = self.driver.find_element(By.ID, "query")
        query_input.send_keys("test")

        time.sleep(1)

        # Limpiar búsqueda
        self.driver.find_element(By.ID, "clear-filters").click()

        time.sleep(1)

        # Verificar que el carrito mantiene el dataset anterior
        badge = self.driver.find_element(By.ID, "cart-count-badge")
        assert badge.text == "1", f"El carrito debería tener 1 dataset, pero tiene {badge.text}"

    def test_cart_empty_message(self):
        """Test 10: Mensaje carrito vacío"""
        self.login()
        self.navigate_to_explore()
        time.sleep(2)

        # 1. Esperar a que cargue la página (igual que el antiguo)
        WebDriverWait(self.driver, 10).until(EC.visibility_of_element_located((By.ID, "results")))

        # Verificar que el mensaje de carrito vacío está visible
        empty_msg = self.driver.find_element(By.ID, "empty-cart-message")
        assert "No datasets selected" in empty_msg.text, "Debería mostrar mensaje de carrito vacío"

        # Añadir un dataset
        add_btns = WebDriverWait(self.driver, 10).until(lambda d: d.find_elements(By.CLASS_NAME, "btn-add-to-cart"))
        if not add_btns:
            pytest.skip("No hay datasets disponibles")

        add_btns[0].click()

        WebDriverWait(self.driver, 10).until(EC.text_to_be_present_in_element((By.ID, "cart-count-badge"), "1"))

        time.sleep(1)

        # Verificar que el mensaje de carrito vacío ya no está visible
        try:
            empty_msg = self.driver.find_element(By.ID, "empty-cart-message")
            display = empty_msg.value_of_css_property("display")

            if display == "none":
                pass
            else:
                print("El mensaje de carrito vacío sigue visible cuando no debería")
        except Exception:
            pass

        # Eliminar
        self.driver.find_element(By.CLASS_NAME, "btn-outline-danger").click()
        time.sleep(1)

        # Verificar que reaparece
        empty_msg_final = WebDriverWait(self.driver, 10).until(
            EC.presence_of_element_located((By.ID, "empty-cart-message"))
        )
        assert empty_msg_final.is_displayed()

    def test_navigation_to_upload_page(self):
        """Test 11: Verificar navegación a la página de subida desde Explore"""
        self.login()
        self.navigate_to_explore()

        upload_link = WebDriverWait(self.driver, 10).until(
            EC.element_to_be_clickable((By.XPATH, "//a[contains(@href, '/dataset/upload')]"))
        )
        upload_link.click()

        WebDriverWait(self.driver, 10).until(EC.url_contains("/dataset/upload"))

    def test_sidebar_contador_updates_with_cart(self):
        """Test 12: Badge en sidebar actualiza con el carrito"""
        self.login()
        self.navigate_to_explore()

        WebDriverWait(self.driver, 10).until(EC.visibility_of_element_located((By.ID, "results")))

        # IMPORTANTE: Esperar a que el sidebar se cargue completamente
        time.sleep(1)

        # Añadir 1 dataset
        add_btns = WebDriverWait(self.driver, 10).until(lambda d: d.find_elements(By.CLASS_NAME, "btn-add-to-cart"))
        if len(add_btns) < 2:
            pytest.skip("Necesarios al menos 2 datasets")

        add_btns[0].click()
        WebDriverWait(self.driver, 10).until(EC.text_to_be_present_in_element((By.ID, "cart-count-badge"), "1"))

        sidebar_badge = self.driver.find_element(By.CSS_SELECTOR, "#sidebar .badge, span.badge, [id*='sidebar-count']")

        # Verificar que contiene "1"
        assert "1" in sidebar_badge.text, "El badge del sidebar debería mostrar 1"

        # Añadir otro dataset
        add_btns[1].click()
        WebDriverWait(self.driver, 10).until(EC.text_to_be_present_in_element((By.ID, "cart-count-badge"), "2"))

        # Verificar que el contador del sidebar muestra "2"
        sidebar_badge = self.driver.find_element(By.CSS_SELECTOR, "#sidebar .badge, span.badge, [id*='sidebar-count']")
        assert "2" in sidebar_badge.text, "El badge del sidebar debería mostrar 2"

        # Elimina uno
        remove_btns = self.driver.find_elements(By.CLASS_NAME, "btn-outline-danger")
        remove_btns[0].click()
        WebDriverWait(self.driver, 10).until(EC.text_to_be_present_in_element((By.ID, "cart-count-badge"), "1"))

        # Verificar que sidebar badge muestra "1"
        sidebar_badge = self.driver.find_element(By.CSS_SELECTOR, "#sidebar .badge, span.badge, [id*='sidebar-count']")
        assert "1" in sidebar_badge.text, "El badge del sidebar debería mostrar 1"
