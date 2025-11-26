import os
import time

from selenium.common.exceptions import NoSuchElementException, TimeoutException
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

from core.environment.host import get_host_for_selenium_testing
from core.selenium.common import close_driver, initialize_driver


def wait_for_page_to_load(driver, timeout=4):
    try:
        WebDriverWait(driver, timeout).until(
            lambda driver: driver.execute_script("return document.readyState") == "complete"
        )
    except TimeoutException:
        pass


def count_datasets(driver, host):
    driver.get(f"{host}/dataset/list")
    wait_for_page_to_load(driver)
    try:
        # Contamos filas en cualquier cuerpo de tabla presente
        rows = driver.find_elements(By.XPATH, "//table//tbody//tr")
        return len(rows)
    except Exception:
        return 0


def test_full_lifecycle():
    print(">>> INICIANDO TEST E2E COMPLETO (Upload -> Download -> Counter)...")
    driver = initialize_driver()
    wait = WebDriverWait(driver, 10)
    dataset_title = "Selenium Lifecycle Test"

    try:
        host = get_host_for_selenium_testing()

        # -----------------------------------------------------------------------
        # FASE 1: LOGIN
        # -----------------------------------------------------------------------
        print("[1/4] Login...")
        driver.get(f"{host}/login")
        wait_for_page_to_load(driver)

        driver.find_element(By.NAME, "email").send_keys("user1@example.com")
        driver.find_element(By.NAME, "password").send_keys("1234")
        driver.find_element(By.NAME, "password").send_keys(Keys.RETURN)

        # Esperar a que redirija al dashboard o home
        wait.until(EC.url_changes(f"{host}/login"))
        wait_for_page_to_load(driver)

        initial_datasets = count_datasets(driver, host)

        # -----------------------------------------------------------------------
        # FASE 2: UPLOAD (SUBIDA)
        # -----------------------------------------------------------------------
        print("[2/4] Subiendo dataset...")
        driver.get(f"{host}/dataset/upload")
        wait_for_page_to_load(driver)

        # Datos básicos
        driver.find_element(By.NAME, "title").send_keys(dataset_title)
        driver.find_element(By.NAME, "desc").send_keys("Description for E2E test")
        driver.find_element(By.NAME, "tags").send_keys("selenium,e2e")

        # Autores (Esperas explícitas para evitar fallos de JS)
        add_author_btn = driver.find_element(By.ID, "add_author")
        add_author_btn.click()
        wait.until(EC.visibility_of_element_located((By.NAME, "authors-0-name")))
        driver.find_element(By.NAME, "authors-0-name").send_keys("Author Zero")
        driver.find_element(By.NAME, "authors-0-affiliation").send_keys("Test Lab")

        # Archivos (Rutas absolutas + Fix Dropzone)
        # Asumimos que el script se ejecuta desde la raíz del proyecto
        base_path = os.getcwd()
        file1_path = os.path.join(base_path, "app/modules/dataset/uvl_examples/file1.uvl")
        file2_path = os.path.join(base_path, "app/modules/dataset/uvl_examples/file2.uvl")

        if not os.path.exists(file1_path):
            raise Exception(f"CRÍTICO: No encuentro archivo en {file1_path}")

        # Subir Archivo 1
        dropzone_input = driver.find_element(By.CLASS_NAME, "dz-hidden-input")
        driver.execute_script(
            "arguments[0].style.visibility = 'visible'; arguments[0].style.height = '1px'; arguments[0].style.width = '1px'; arguments[0].style.opacity = 1",
            dropzone_input,
        )
        dropzone_input.send_keys(file1_path)
        time.sleep(1)  # Esperar miniatura

        # Subir Archivo 2 (RE-QUERY IMPORTANTE)
        dropzone_input = driver.find_element(By.CLASS_NAME, "dz-hidden-input")
        driver.execute_script(
            "arguments[0].style.visibility = 'visible'; arguments[0].style.height = '1px'; arguments[0].style.width = '1px'; arguments[0].style.opacity = 1",
            dropzone_input,
        )
        dropzone_input.send_keys(file2_path)
        time.sleep(1)

        # Checkbox y Enviar
        check = driver.find_element(By.ID, "agreeCheckbox")
        driver.execute_script("arguments[0].click();", check)

        submit_btn = driver.find_element(By.ID, "upload_button")
        driver.execute_script("arguments[0].click();", submit_btn)

        # Esperar redirección a la lista
        wait.until(EC.url_to_be(f"{host}/dataset/list"))

        # Validar subida
        final_datasets = count_datasets(driver, host)
        assert final_datasets == initial_datasets + 1, "El dataset no aparece en la lista tras subirlo."

        # -----------------------------------------------------------------------
        # FASE 3: NAVEGACIÓN (ENCONTRAR EL DATASET)
        # -----------------------------------------------------------------------
        print("[3/4] Buscando dataset en la tabla...")

        # ESTRATEGIA INDESTRUCTIBLE:
        # 1. Buscar la fila (tr) que contiene el título que acabamos de escribir.
        # 2. Dentro de esa fila, ir a la última celda (td).
        # 3. Dentro de esa celda, hacer clic en el primer enlace (a).
        try:
            # XPath: Busca un TR que contenga el texto del título
            row_xpath = f"//tr[contains(., '{dataset_title}')]"
            dataset_row = driver.find_element(By.XPATH, row_xpath)

            # Dentro de esa fila, busca la última celda y el primer enlace (View)
            # Según tu HTML: <td> <a ... eye></a> <a ... download></a> </td>
            view_btn = dataset_row.find_element(By.XPATH, ".//td[last()]//a[1]")

            # Hacemos scroll y click JS para asegurar
            driver.execute_script("arguments[0].scrollIntoView(true);", view_btn)
            driver.execute_script("arguments[0].click();", view_btn)

            wait_for_page_to_load(driver)

        except NoSuchElementException:
            print("DEBUG HTML: ", driver.page_source[:1000])
            raise Exception(f"No encontré la fila con el título '{dataset_title}' o el botón de ver.")

        # -----------------------------------------------------------------------
        # FASE 4: CONTADOR (VERIFICACIÓN)
        # -----------------------------------------------------------------------
        print("[4/4] Verificando contador...")

        # 1. Leer contador inicial
        try:
            initial_count_elem = wait.until(EC.visibility_of_element_located((By.ID, "download_count_text")))
            initial_count = int(initial_count_elem.text.strip())
            print(f"   -> Contador inicial: {initial_count}")
        except:
            raise Exception("No encuentro el ID 'download_count_text'. Revisa view_dataset.html")

        # 2. Pulsar botón descarga
        download_btn = driver.find_element(By.ID, "download_btn")
        download_btn.click()

        # Esperamos un poco a que el JS actúe
        time.sleep(1.5)

        # 3. Validar JS (Frontend)
        new_count = int(driver.find_element(By.ID, "download_count_text").text.strip())
        assert new_count == initial_count + 1, f"JS Falló: {initial_count} -> {new_count}"
        print("   -> JS Frontend: OK")

        # 4. Validar BD (Backend - Recarga)
        driver.refresh()
        wait_for_page_to_load(driver)

        db_count_elem = wait.until(EC.visibility_of_element_located((By.ID, "download_count_text")))
        db_count = int(db_count_elem.text.strip())

        assert db_count == initial_count + 1, f"BD Falló: Esperaba {initial_count + 1}, tengo {db_count}"
        print("   -> BD Backend: OK")

        print(">>> ✅ TEST COMPLETADO CON ÉXITO")

    except Exception as e:
        print(f"❌ ERROR: {e}")
        raise e

    finally:
        close_driver(driver)


test_full_lifecycle()
