import random

from locust import HttpUser, TaskSet, between, task


class FakenodoBehavior(TaskSet):
    deposition_ids = []

    def on_start(self):
        self.client.get("/fakenodo/test", name="/test_endpoint")

    @task
    def create_deposition(self):
        payload = {"metadata": {"title": f"Depo-{random.randint(1000, 9999)}"}}
        with self.client.post(
            "/fakenodo/deposit/depositions", json=payload, catch_response=True, name="create_deposition"
        ) as resp:
            if resp.status_code == 201:
                data = resp.json()
                self.deposition_ids.append(data["id"])

    @task
    def list_depositions(self):
        self.client.get("/fakenodo/deposit/depositions", name="list_depositions")

    @task
    def get_deposition(self):
        if not self.deposition_ids:
            return
        dep_id = random.choice(self.deposition_ids)
        self.client.get(f"/fakenodo/deposit/depositions/{dep_id}", name="get_deposition")

    @task
    def update_metadata(self):
        if not self.deposition_ids:
            return
        dep_id = random.choice(self.deposition_ids)
        payload = {"metadata": {"description": "Updated via Locust"}}
        self.client.patch(f"/fakenodo/deposit/depositions/{dep_id}/metadata", json=payload, name="update_metadata")

    @task
    def upload_file(self):
        if not self.deposition_ids:
            return
        dep_id = random.choice(self.deposition_ids)
        files = {"file": ("test.txt", b"Hello Locust!")}
        self.client.post(
            f"/fakenodo/deposit/depositions/{dep_id}/files", files=files, data={"name": "test.txt"}, name="upload_file"
        )

    @task
    def publish_deposition(self):
        if not self.deposition_ids:
            return
        dep_id = random.choice(self.deposition_ids)
        self.client.post(f"/fakenodo/deposit/depositions/{dep_id}/actions/publish", name="publish_deposition")

    @task
    def delete_deposition(self):
        if not self.deposition_ids:
            return
        dep_id = self.deposition_ids.pop(0)
        self.client.delete(f"/fakenodo/deposit/depositions/{dep_id}", name="delete_deposition")

    @task
    def dataset_sync_proxy(self):
        dataset_id = random.randint(1, 10)
        self.client.get(f"/fakenodo/dataset/{dataset_id}/sync", name="dataset_sync_proxy_GET")

    @task
    def dataset_publish_or_create(self):
        dataset_id = random.randint(1, 10)
        self.client.post(f"/fakenodo/dataset/{dataset_id}/publish_or_create", name="publish_or_create_dataset")


class FakenodoUser(HttpUser):
    tasks = [FakenodoBehavior]
    wait_time = between(1, 3)
    host = "http://localhost:5000"
