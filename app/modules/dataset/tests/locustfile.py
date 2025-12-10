import random
import re
from html.parser import HTMLParser

from locust import HttpUser, TaskSet, between, task

try:
    from core.environment.host import get_host_for_locust_testing
except ImportError:

    def get_host_for_locust_testing():
        return "http://localhost:5000"


class CSRFTokenParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.csrf_token = None

    def handle_starttag(self, tag, attrs):
        if tag == "input":
            attrs_dict = dict(attrs)
            if attrs_dict.get("name") == "csrf_token":
                self.csrf_token = attrs_dict.get("value")


def get_csrf_token(html_content):
    parser = CSRFTokenParser()
    parser.feed(html_content)
    return parser.csrf_token


class DatasetBehavior(TaskSet):
    dataset_ids = []

    def on_start(self):
        """1. Loguearse. 2. Buscar Datasets."""
        if self.login():
            self.fetch_dataset_ids()
        else:
            self.interrupt(reschedule=False)

    def login(self):
        with self.client.get("/login", name="/login (GET)", catch_response=True) as response:
            if response.status_code != 200:
                print(f"⚠️ Error cargando login: {response.status_code}")
                return False

            csrf_token = get_csrf_token(response.text)

            if not csrf_token:
                print("❌ ERROR: No encuentro el CSRF token. Revisa el HTML de /login")
                return False

        res = self.client.post(
            "/login",
            data={
                "email": "user1@example.com",
                "password": "1234",
                "csrf_token": csrf_token,
            },
            name="/login (POST)",
        )

        return res.status_code < 400

    def fetch_dataset_ids(self):
        with self.client.get("/dataset/list", name="/dataset/list", catch_response=True) as response:
            found = re.findall(r'href=["\']/dataset/download/(\d+)["\']', response.text)

            if not found:
                print("⚠️ WARNING: Login OK, pero no veo enlaces de descarga en /dataset/list.")
                print("   -> ¿Has subido algún dataset con este usuario o es público?")
            else:
                self.dataset_ids = list(set(found))
                print(f"✅ INFO: Usuario listo. Encontrados {len(self.dataset_ids)} datasets.")

    @task(1)
    def view_list(self):
        self.client.get("/dataset/list", name="/dataset/list")

    @task(2)
    def view_dataset_detail(self):
        if not self.dataset_ids:
            return

        dataset_id = random.choice(self.dataset_ids)
        self.client.get(f"/dataset/view/{dataset_id}", name="/dataset/view/[id]")

    @task(4)
    def download_dataset(self):
        if not self.dataset_ids:
            return

        dataset_id = random.choice(self.dataset_ids)

        with self.client.get(
            f"/dataset/download/{dataset_id}", catch_response=True, name="/dataset/download/[id]"
        ) as response:
            if response.status_code == 200:
                response.success()
            elif response.status_code == 404:
                response.failure("Dataset not found (404)")
            elif response.status_code == 500:
                response.failure("Server Error (500)")
            else:
                response.failure(f"Error {response.status_code}")


class DatasetUser(HttpUser):
    tasks = [DatasetBehavior]
    wait_time = between(1, 3)
    host = get_host_for_locust_testing()
