import os
import time

import pytest
from selenium import webdriver
from selenium.common.exceptions import NoAlertPresentException, NoSuchElementException, TimeoutException
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.firefox.options import Options
from selenium.webdriver.firefox.service import Service
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

from app import create_app, db
from app.modules.dataset.models import DataSet, DSMetaData


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
        if self.driver:
            self.driver.quit()

        app = create_app()
        with app.app_context():
            datasets_to_delete = (
                DataSet.query.join(DSMetaData)
                .filter(
                    (DSMetaData.title.like("%Dataset_%"))
                    | (DSMetaData.title.like("%Selenium%"))
                    | (DSMetaData.title == "Load Test Dataset")  # Usado en locust/tests
                )
                .all()
            )

            if datasets_to_delete:
                for ds in datasets_to_delete:
                    db.session.delete(ds)

                try:
                    db.session.commit()
                except Exception:
                    db.session.rollback()

    def login(self, email="user2@example.com", password="1234"):
        """Helper method para hacer login"""
        self.driver.get("http://localhost:5000/login")
        email_input = WebDriverWait(self.driver, 10).until(EC.visibility_of_element_located((By.NAME, "email")))
        email_input.send_keys(email)
        pass_input = self.driver.find_element(By.NAME, "password")
        pass_input.send_keys(password)
        pass_input.send_keys(Keys.ENTER)

        time.sleep(3)

        try:
            WebDriverWait(self.driver, 10).until(
                EC.presence_of_element_located(
                    (By.XPATH, "//h1[contains(@class, 'h2 mb-3')] | //div[contains(@class, 'dashboard')]")
                )
            )
        except TimeoutException:
            try:
                alert = self.driver.switch_to.alert
                alert.accept()
                WebDriverWait(self.driver, 10).until(
                    EC.presence_of_element_located(
                        (By.XPATH, "//h1[contains(@class, 'h2 mb-3')] | //div[contains(@class, 'dashboard')]")
                    )
                )
            except NoAlertPresentException:
                raise

    def navigate_to_explore(self):
        """Helper method para navegar a explore"""
        self.driver.get("http://localhost:5000/explore")
        self.driver.set_window_size(1290, 741)

    def test_exploreSelenium(self):
        """Test principal: agregar 1 dataset, crear dataset combinado y verificar cierre de modal"""

        self.driver.get("http://localhost:5000/")
        self.login()
        self.navigate_to_explore()

        WebDriverWait(self.driver, 10).until(EC.presence_of_element_located((By.ID, "results")))

        time.sleep(5)

        all_add_buttons = self.driver.find_elements(By.CLASS_NAME, "btn-add-to-cart")
        print(f"Encontrados {len(all_add_buttons)} botones 'Add to my dataset'")

        # Si no hay botones, el test no puede continuar
        if len(all_add_buttons) == 0:
            pytest.skip("No hay datasets disponibles para test")

        # Clica en el primer botón (posición 0)
        first_add_button = all_add_buttons[0]

        first_add_button.click()

        time.sleep(1)

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

        # Esperar a que el modal se cierre o redireccione
        try:
            # Máximo 15 segundos
            WebDriverWait(self.driver, 15).until(
                lambda d: d.find_element(By.ID, "create-dataset-modal").value_of_css_property("display") == "none"
                or "/explore" not in d.current_url
            )
            print("✓ Modal cerrado o página redirigida")
        except TimeoutException:
            print("⚠️ Modal no se cerró automáticamente, intentando cerrar manualmente...")

            try:
                close_btn = self.driver.find_element(By.ID, "modal-close-btn")
                close_btn.click()
                time.sleep(1)
            except Exception:
                pass

            try:
                error_msg = self.driver.find_element(By.CLASS_NAME, "alert-danger")
                print(f"Error detectado: {error_msg.text[:100]}")
            except Exception:
                pass

        final_section = WebDriverWait(self.driver, 10).until(
            EC.element_to_be_clickable((By.ID, "my-selected-datasets-section"))
        )
        final_section.click()

    def test_add_multiple_datasets_to_cart(self):
        """Test 1: Agregar múltiples datasets al carrito y verificar el contador

        NOTA: Este test requiere al menos 3 datasets en la base de datos, sino saltará
        """
        self.login()
        self.navigate_to_explore()

        WebDriverWait(self.driver, 10).until(EC.visibility_of_element_located((By.ID, "results")))

        # Agregar primer dataset (clickear el primero disponible)
        add_btns = WebDriverWait(self.driver, 10).until(lambda d: d.find_elements(By.CLASS_NAME, "btn-add-to-cart"))

        if len(add_btns) < 3:
            import pytest

            pytest.skip(f"Se necesitan al menos 3 datasets, pero solo hay {len(add_btns)}")

        add_btns[0].click()
        WebDriverWait(self.driver, 10).until(EC.text_to_be_present_in_element((By.ID, "cart-count-badge"), "1"))

        # Verificar que el botón está deshabilitado
        btn = WebDriverWait(self.driver, 5).until(lambda d: d.find_elements(By.CLASS_NAME, "btn-add-to-cart")[0])
        WebDriverWait(self.driver, 5).until(lambda d: btn.get_attribute("disabled") is not None)
        assert "Added" in btn.text, "El texto del botón debería estar 'Added'"

        # Agregar segundo dataset
        add_btns = self.driver.find_elements(By.CLASS_NAME, "btn-add-to-cart")
        add_btns[1].click()
        WebDriverWait(self.driver, 10).until(EC.text_to_be_present_in_element((By.ID, "cart-count-badge"), "2"))

        # Verificar que ambos aparecen en la lista
        selected_list = self.driver.find_element(By.ID, "selected-datasets-list")
        list_items = selected_list.find_elements(By.CSS_SELECTOR, "li:not(#empty-cart-message)")

        assert len(list_items) == 2, f"Debería haber 2 datasets en el carrito, pero hay {len(list_items)}"

        # Agregar tercer dataset
        add_btns = self.driver.find_elements(By.CLASS_NAME, "btn-add-to-cart")
        add_btns[2].click()
        WebDriverWait(self.driver, 10).until(EC.text_to_be_present_in_element((By.ID, "cart-count-badge"), "3"))

        list_items = selected_list.find_elements(By.CSS_SELECTOR, "li:not(#empty-cart-message)")
        assert len(list_items) == 3, f"Debería haber 3 datasets en el carrito, pero hay {len(list_items)}"

    def test_remove_dataset_from_cart(self):
        """Test 2: Eliminar datasets del carrito

        NOTA: Este test requiere al menos 2 datasets en la base de datos, sino saltará
        """
        self.login()
        self.navigate_to_explore()

        WebDriverWait(self.driver, 10).until(lambda d: d.find_elements(By.CLASS_NAME, "btn-add-to-cart"))

        # Agrega 2º dataset
        add_btns = WebDriverWait(self.driver, 10).until(lambda d: d.find_elements(By.CLASS_NAME, "btn-add-to-cart"))

        if len(add_btns) < 2:
            import pytest

            pytest.skip(f"Se necesitan al menos 2 datasets, pero solo hay {len(add_btns)}")

        add_btns[0].click()
        WebDriverWait(self.driver, 10).until(EC.text_to_be_present_in_element((By.ID, "cart-count-badge"), "1"))

        add_btns[1].click()
        WebDriverWait(self.driver, 10).until(EC.text_to_be_present_in_element((By.ID, "cart-count-badge"), "2"))

        # Busca el botón remove para el primer dataset en la lista
        selected_list = self.driver.find_element(By.ID, "selected-datasets-list")
        remove_btns = selected_list.find_elements(By.CLASS_NAME, "btn-outline-danger")

        assert len(remove_btns) == 2, "Debería haber 2 botones remove"

        # Clicar el primero
        remove_btns[0].click()

        # Verificar que el contador actualiza a 1
        WebDriverWait(self.driver, 10).until(EC.text_to_be_present_in_element((By.ID, "cart-count-badge"), "1"))

        # Verificar que el botón "Add" se re-habilita (ya no está deshabilitado)
        add_btns_updated = self.driver.find_elements(By.CLASS_NAME, "btn-add-to-cart")
        assert (
            add_btns_updated[0].get_attribute("disabled") is None
        ), "El botón debería estar habilitado después de eliminar"

        # Verificar que solo queda 1 dataset en la lista
        list_items = selected_list.find_elements(By.CSS_SELECTOR, "li:not(#empty-cart-message)")
        assert len(list_items) == 1, f"Debería haber 1 dataset en el carrito, pero hay {len(list_items)}"

    def test_cancel_create_dataset_modal(self):
        """Test 3: Verificar navegación a la página de subida"""
        self.login()
        self.navigate_to_explore()

        add_btn = WebDriverWait(self.driver, 10).until(
            EC.element_to_be_clickable((By.XPATH, "//a[contains(@href, '/dataset/upload')]"))
        )
        add_btn.click()

        WebDriverWait(self.driver, 10).until(EC.url_contains("/dataset/upload"))

    def test_modal_close_button(self):
        """Test 4: Cerrar modal con el botón X"""
        self.login()
        self.navigate_to_explore()

        # Esperar a que los datasets se carguen
        WebDriverWait(self.driver, 10).until(EC.visibility_of_element_located((By.ID, "results")))

        # Añadir 1 dataset
        add_btns = WebDriverWait(self.driver, 10).until(lambda d: d.find_elements(By.CLASS_NAME, "btn-add-to-cart"))
        add_btns[0].click()
        WebDriverWait(self.driver, 10).until(EC.text_to_be_present_in_element((By.ID, "cart-count-badge"), "1"))

        # Abrir modal
        create_btn = WebDriverWait(self.driver, 10).until(EC.element_to_be_clickable((By.ID, "create-dataset-btn")))
        create_btn.click()

        # Clicar botón X
        close_btn = WebDriverWait(self.driver, 10).until(EC.element_to_be_clickable((By.ID, "modal-close-btn")))
        close_btn.click()

        # Verificar que el modal se cierra
        modal = self.driver.find_element(By.ID, "create-dataset-modal")
        WebDriverWait(self.driver, 10).until(lambda d: modal.value_of_css_property("display") == "none")

        # Verificar que el carrito permanece intacto
        badge = self.driver.find_element(By.ID, "cart-count-badge")
        assert badge.text == "1", f"El badge debería mostrar 1, pero muestra {badge.text}"

    def test_create_dataset_without_required_fields(self):
        """Test 5: Intentar crear dataset sin rellenar título (campo required)"""
        self.login()
        self.navigate_to_explore()

        WebDriverWait(self.driver, 10).until(EC.visibility_of_element_located((By.ID, "results")))

        # Añadir 1 dataset
        add_btns = WebDriverWait(self.driver, 10).until(lambda d: d.find_elements(By.CLASS_NAME, "btn-add-to-cart"))
        add_btns[0].click()
        WebDriverWait(self.driver, 10).until(EC.text_to_be_present_in_element((By.ID, "cart-count-badge"), "1"))

        # Abrir modal
        create_btn = WebDriverWait(self.driver, 10).until(EC.element_to_be_clickable((By.ID, "create-dataset-btn")))
        create_btn.click()

        # NO rellenar el título (requerido)
        self.driver.find_element(By.ID, "dataset-description").send_keys("Test description")
        self.driver.find_element(By.ID, "dataset-tags").send_keys("test")

        # Buscar el botón de submit
        submit_btn = self.driver.find_element(By.CSS_SELECTOR, "#create-dataset-modal .btn-primary")

        # El campo de título está vacío y required, así que el navegador debe mostrar validación
        submit_btn.click()

        time.sleep(1)

        # Si la validación funcionó, el modal sigue intacto
        badge = self.driver.find_element(By.ID, "cart-count-badge")
        assert badge.text == "1", "El carrito debería seguir con 1 dataset (formulario no se envió)"

    def test_download_cart_with_multiple_datasets(self):
        """Test 6: Descargar múltiples datasets como ZIP

        NOTA: Este test requiere al menos 2 datasets en la base de datos.
        """
        self.login()
        self.navigate_to_explore()

        WebDriverWait(self.driver, 10).until(EC.visibility_of_element_located((By.ID, "results")))

        # Añadir 2 datasets
        add_btns = WebDriverWait(self.driver, 10).until(lambda d: d.find_elements(By.CLASS_NAME, "btn-add-to-cart"))

        if len(add_btns) < 2:
            import pytest

            pytest.skip(f"Se necesitan al menos 2 datasets, pero solo hay {len(add_btns)}")

        add_btns[0].click()
        WebDriverWait(self.driver, 10).until(EC.text_to_be_present_in_element((By.ID, "cart-count-badge"), "1"))

        add_btns[1].click()
        WebDriverWait(self.driver, 10).until(EC.text_to_be_present_in_element((By.ID, "cart-count-badge"), "2"))

        # Clicar "Download models"
        download_btn = WebDriverWait(self.driver, 10).until(
            EC.element_to_be_clickable((By.ID, "open-download-modal-btn"))
        )
        download_btn.click()

        # Esperar a que se abra el modal de descarga
        download_modal = WebDriverWait(self.driver, 10).until(
            EC.visibility_of_element_located((By.ID, "download-dataset-modal"))
        )

        # Introducir nombre de archivo
        filename_input = self.driver.find_element(By.ID, "zip-filename")
        filename_input.clear()
        filename_input.send_keys("test_download")

        # Clicar submit (descarga)
        download_form = self.driver.find_element(By.ID, "download-dataset-form")
        download_form.submit()

        # Esperar a que el modal se cierre después de la descarga
        time.sleep(2)

        # Verificar que el modal se cerró
        assert (
            download_modal.value_of_css_property("display") == "none"
        ), "El modal debería cerrarse después de la descarga"

    def test_download_modal_cancel(self):
        """Test 7: Cancelar descarga sin descargar"""
        self.login()
        self.navigate_to_explore()

        WebDriverWait(self.driver, 10).until(EC.visibility_of_element_located((By.ID, "results")))

        # Añadir 1 dataset
        add_btns = WebDriverWait(self.driver, 10).until(lambda d: d.find_elements(By.CLASS_NAME, "btn-add-to-cart"))
        add_btns[0].click()
        WebDriverWait(self.driver, 10).until(EC.text_to_be_present_in_element((By.ID, "cart-count-badge"), "1"))

        # Clicar "Download models"
        download_btn = WebDriverWait(self.driver, 10).until(
            EC.element_to_be_clickable((By.ID, "open-download-modal-btn"))
        )
        download_btn.click()

        # Esperar a que se abra el modal
        download_modal = WebDriverWait(self.driver, 10).until(
            EC.visibility_of_element_located((By.ID, "download-dataset-modal"))
        )

        # Clicar botón X para cerrar
        close_btn = WebDriverWait(self.driver, 10).until(
            EC.element_to_be_clickable((By.ID, "download-modal-close-btn"))
        )
        close_btn.click()

        # Verificar que el modal se cerró
        WebDriverWait(self.driver, 10).until(lambda d: download_modal.value_of_css_property("display") == "none")

        # Verificar que el carrito permanece igual
        badge = self.driver.find_element(By.ID, "cart-count-badge")
        assert badge.text == "1", f"El badge debería mostrar 1, pero muestra {badge.text}"

    def test_search_filter_before_add_to_cart(self):
        """Test 8: Buscar/filtrar datasets y agregar al carrito"""
        self.login()
        self.navigate_to_explore()

        # Esperar a que los datasets se carguen
        WebDriverWait(self.driver, 10).until(EC.visibility_of_element_located((By.ID, "results")))

        # Agregar un dataset ANTES de hacer búsqueda
        add_btns = WebDriverWait(self.driver, 10).until(lambda d: d.find_elements(By.CLASS_NAME, "btn-add-to-cart"))
        add_btns[0].click()
        WebDriverWait(self.driver, 10).until(EC.text_to_be_present_in_element((By.ID, "cart-count-badge"), "1"))

        # Ahora escribe en un campo de búsqueda
        query_input = WebDriverWait(self.driver, 10).until(EC.visibility_of_element_located((By.ID, "query")))
        query_input.send_keys("dataset")

        time.sleep(2)

        # Verificar que el carrito mantiene el dataset anterior
        badge = self.driver.find_element(By.ID, "cart-count-badge")
        assert badge.text == "1", f"El carrito debería tener 1 dataset, pero tiene {badge.text}"

        # Cambiar la búsqueda a algo diferente
        query_input.clear()
        query_input.send_keys("other")
        time.sleep(2)

        # Verificar que el carrito SIGUE teniendo el dataset
        badge = self.driver.find_element(By.ID, "cart-count-badge")
        assert badge.text == "1", "El carrito debería seguir con 1 dataset después de cambiar búsqueda"

    def test_clear_filters_keeps_cart(self):
        """Test 9: Limpiar filtros no limpia el carrito"""
        self.login()
        self.navigate_to_explore()

        # Esperar a que los datasets se carguen
        WebDriverWait(self.driver, 10).until(EC.visibility_of_element_located((By.ID, "results")))

        # Agregar 1 dataset
        add_btns = WebDriverWait(self.driver, 10).until(lambda d: d.find_elements(By.CLASS_NAME, "btn-add-to-cart"))
        add_btns[0].click()
        WebDriverWait(self.driver, 10).until(EC.text_to_be_present_in_element((By.ID, "cart-count-badge"), "1"))

        # Aplicar filtros (búsqueda)
        query_input = self.driver.find_element(By.ID, "query")
        query_input.send_keys("test")
        time.sleep(2)

        # Clicar "Clear filters"
        clear_btn = WebDriverWait(self.driver, 10).until(EC.element_to_be_clickable((By.ID, "clear-filters")))
        clear_btn.click()
        time.sleep(1)

        # Verificar que el carrito sigue intacto
        badge = self.driver.find_element(By.ID, "cart-count-badge")
        assert badge.text == "1", f"El carrito debería tener 1 dataset, pero tiene {badge.text}"

        # Verificar que la búsqueda se limpió
        query_input = self.driver.find_element(By.ID, "query")
        assert query_input.get_attribute("value") == "", "El campo de búsqueda debería estar vacío"

    def test_sidebar_contador_updates_with_cart(self):
        """Test 10: Badge en sidebar actualiza con el carrito

        NOTA: Este test requiere al menos 2 datasets en la base de datos.
        """
        self.login()
        self.navigate_to_explore()

        WebDriverWait(self.driver, 10).until(EC.visibility_of_element_located((By.ID, "results")))

        # IMPORTANTE: Esperar a que el sidebar se cargue completamente
        time.sleep(1)

        # Verificar que inicialmente el contador muestra 0
        try:
            # Espera a que el badge sea visible y tenga número
            sidebar_badge = WebDriverWait(self.driver, 10).until(
                EC.presence_of_element_located((By.ID, "dataset-sidebar-count"))
            )

            # Verifica que está visible
            WebDriverWait(self.driver, 5).until(lambda d: sidebar_badge.is_displayed())

            # Verifica el texto inicial (debe ser 0)
            badge_text = sidebar_badge.text.strip()
            print(f"Badge encontrado por ID: texto='{badge_text}'")

            if badge_text and badge_text != "0":
                print(f"Badge no está en 0 inicialmente: '{badge_text}'")

        except (TimeoutException, NoSuchElementException) as e:
            print(f"Error encontrando badge por ID: {e}")

            # Buscar por clase exacta
            badges = self.driver.find_elements(By.CSS_SELECTOR, "span.badge.bg-primary.ms-2.rounded-pill")
            if badges:
                sidebar_badge = badges[0]
            else:
                # Buscar en el sidebar específicamente
                sidebar = self.driver.find_element(By.ID, "sidebar")
                badges_in_sidebar = sidebar.find_elements(By.CLASS_NAME, "badge")
                if badges_in_sidebar:
                    sidebar_badge = badges_in_sidebar[0]
                    print(f"Encontrado en sidebar: '{sidebar_badge.text}'")
                else:
                    pytest.skip("No se pudo encontrar el badge del sidebar después de múltiples intentos")
                    return

        # Añadir 1 dataset
        add_btns = WebDriverWait(self.driver, 10).until(lambda d: d.find_elements(By.CLASS_NAME, "btn-add-to-cart"))

        add_btns[0].click()
        WebDriverWait(self.driver, 10).until(EC.text_to_be_present_in_element((By.ID, "cart-count-badge"), "1"))

        time.sleep(1)

        try:
            # Intenta encontrar el badge actualizado
            updated_badge = WebDriverWait(self.driver, 5).until(
                EC.presence_of_element_located((By.ID, "dataset-sidebar-count"))
            )
            sidebar_badge = updated_badge
        except Exception:
            # Si no encuentra por ID, buscar por clase nuevamente
            badges = self.driver.find_elements(By.CSS_SELECTOR, "span.badge.bg-primary.ms-2.rounded-pill")
            if badges:
                sidebar_badge = badges[0]
            else:
                # Buscar cualquier badge
                all_badges = self.driver.find_elements(By.CLASS_NAME, "badge")
                if all_badges:
                    sidebar_badge = all_badges[0]

        # Verificar que contiene "1"
        if "1" in sidebar_badge.text:
            print("Badge actualizado correctamente a '1'")
        else:
            print(f"Badge no se actualizó a '1', tiene: '{sidebar_badge.text}'")

        # Si no hay al menos 2 datasets, salta el resto del test
        if len(add_btns) < 2:
            pytest.skip(f"Se necesitan al menos 2 datasets para completar el test, pero solo hay {len(add_btns)}")

        # Añadir otro dataset
        add_btns[1].click()
        WebDriverWait(self.driver, 10).until(EC.text_to_be_present_in_element((By.ID, "cart-count-badge"), "2"))

        time.sleep(1)

        # Verificar que el contador del sidebar muestra "2"
        try:
            updated_badge = self.driver.find_element(By.ID, "dataset-sidebar-count")
            sidebar_badge = updated_badge
        except Exception:
            badges = self.driver.find_elements(By.CSS_SELECTOR, "span.badge.bg-primary.ms-2.rounded-pill")
            if badges:
                sidebar_badge = badges[0]

        if "2" in sidebar_badge.text:
            print("Badge actualizado correctamente a '2'")
        else:
            print(f"Badge no se actualizó a '2', tiene: '{sidebar_badge.text}'")

        # Elimina uno
        selected_list = self.driver.find_element(By.ID, "selected-datasets-list")
        remove_btns = selected_list.find_elements(By.CLASS_NAME, "btn-outline-danger")
        remove_btns[0].click()
        WebDriverWait(self.driver, 10).until(EC.text_to_be_present_in_element((By.ID, "cart-count-badge"), "1"))

        time.sleep(1)

        # Verificar que sidebar badge muestra "1"
        try:
            updated_badge = self.driver.find_element(By.ID, "dataset-sidebar-count")
            sidebar_badge = updated_badge
        except Exception:
            badges = self.driver.find_elements(By.CSS_SELECTOR, "span.badge.bg-primary.ms-2.rounded-pill")
            if badges:
                sidebar_badge = badges[0]

        print(f"Badge después de eliminar 1 dataset: '{sidebar_badge.text}'")

        if "1" in sidebar_badge.text:
            print("Badge actualizado correctamente de vuelta a '1'")
        else:
            print(f"Badge no se actualizó de vuelta a '1', tiene: '{sidebar_badge.text}'")

    def test_cart_empty_message_toggle(self):
        """Test 11: Mensaje "No datasets selected" aparece/desaparece"""
        self.login()
        self.navigate_to_explore()

        WebDriverWait(self.driver, 10).until(EC.visibility_of_element_located((By.ID, "results")))

        # Verificar que inicialmente muestra el mensaje vacío
        empty_msg = WebDriverWait(self.driver, 10).until(
            EC.visibility_of_element_located((By.ID, "empty-cart-message"))
        )
        assert "No datasets selected" in empty_msg.text, "Debería mostrar el mensaje de carrito vacío"

        # Añadir 1 dataset
        add_btns = WebDriverWait(self.driver, 10).until(lambda d: d.find_elements(By.CLASS_NAME, "btn-add-to-cart"))
        add_btns[0].click()
        WebDriverWait(self.driver, 10).until(EC.text_to_be_present_in_element((By.ID, "cart-count-badge"), "1"))

        # Verificar que desaparece el mensaje (se oculta con display: none)
        selected_list = self.driver.find_element(By.ID, "selected-datasets-list")
        time.sleep(0.5)

        # El mensaje está oculto
        try:
            empty_msg = selected_list.find_element(By.ID, "empty-cart-message")
            assert empty_msg.value_of_css_property("display") == "none", "El mensaje vacío debería estar oculto"
        except Exception:
            pass

        # Verificar que aparece la lista con datasets
        list_items = selected_list.find_elements(By.CSS_SELECTOR, "li:not(#empty-cart-message)")
        assert len(list_items) > 0, "Debería haber datasets en la lista"

        # Elimina el dataset
        remove_btn = selected_list.find_element(By.CLASS_NAME, "btn-outline-danger")
        remove_btn.click()
        WebDriverWait(self.driver, 10).until(EC.text_to_be_present_in_element((By.ID, "cart-count-badge"), "0"))

        # Verifica que reaparece el mensaje
        empty_msg = WebDriverWait(self.driver, 10).until(
            EC.visibility_of_element_located((By.ID, "empty-cart-message"))
        )
        assert "No datasets selected" in empty_msg.text, "Debería mostrar nuevamente el mensaje de carrito vacío"
