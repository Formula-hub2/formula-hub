import random
import re

import gevent.monkey
from locust import HttpUser, TaskSet, between, task

# Ajusta estos imports según tu estructura real
from core.environment.host import get_host_for_locust_testing

# Asegúrate de que esta función get_csrf_token sepa extraer el token del HTML
from core.locust.common import get_csrf_token

gevent.monkey.patch_all()


class DatasetBehavior(TaskSet):
    dataset_ids = []

    def on_start(self):
        """
        Al arrancar el usuario:
        1. Se loguea.
        2. Escanea la lista para buscar IDs válidos.
        """
        self.login()
        self.fetch_dataset_ids()

    def login(self):
        # 1. GET al login para obtener la cookie de sesión y el CSRF token
        response = self.client.get("/login")
        csrf_token = get_csrf_token(response)

        # 2. POST con las credenciales (Usa un usuario que exista en tu BD)
        # Si usas el user1@example.com que creamos en Selenium, asegúrate de que exista aquí.
        self.client.post(
            "/login",
            data={
                "email": "user1@example.com",
                "password": "1234",  # O la password que tengas configurada
                "csrf_token": csrf_token,
            },
        )
        self.client.post(
            "/login",
            data={
                "email": "user1@example.com",
                "password": "1234",  # O la password que tengas configurada
                "csrf_token": csrf_token,
            },
        )

    def fetch_dataset_ids(self):
        # Ahora que estamos logueados, pedimos la lista
        response = self.client.get("/dataset/list")

        # Buscamos IDs. Tu URL puede ser /dataset/download/123 o /dataset/download/123/
        # Usamos una regex flexible
        self.dataset_ids = re.findall(r"/dataset/download/(\d+)", response.text)

        self.dataset_ids = re.findall(r"/dataset/download/(\d+)", response.text)

        if not self.dataset_ids:
            print("WARNING: Sigo sin encontrar datasets. ¿Has subido alguno manualmente antes de lanzar esto?")
        else:
            print(f"INFO: Encontrados {len(self.dataset_ids)} datasets para descargar.")

    @task(1)
    def view_upload_page(self):
        self.client.get("/dataset/upload")

    @task(3)
    @task(3)
    def download_dataset(self):
        if not self.dataset_ids:
            return

        dataset_id = random.choice(self.dataset_ids)
        # El name=... agrupa las estadísticas
        self.client.get(f"/dataset/download/{dataset_id}", name="/dataset/download/[id]")


class DatasetUser(HttpUser):
    tasks = [DatasetBehavior]
    wait_time = between(1, 3)  # Más caña
    wait_time = between(1, 3)  # Más caña
    host = get_host_for_locust_testing()
