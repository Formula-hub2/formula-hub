from locust import HttpUser, between, task


class ExploreUser(HttpUser):
    # Tiempo de espera entre tareas (simula comportamiento humano)
    wait_time = between(1, 5)

    def on_start(self):
        """
        Se ejecuta al iniciar el usuario. Aquí deberías hacer login si es necesario.
        Si tu UVLHUB requiere login para crear datasets, descomenta y ajusta:
        """
        # self.client.post("/login", data={"email": "user@example.com", "password": "password"})
        pass

    @task(3)
    def download_cart(self):
        """
        Simula la descarga de un zip con datasets (IDs 1 y 2).
        Peso 3: Se ejecutará más frecuentemente que crear dataset.
        """
        headers = {"Content-Type": "application/json"}
        payload = {"dataset_ids": [1, 2], "filename": "load_test_download"}

        with self.client.post("/explore/download_cart", json=payload, headers=headers, catch_response=True) as response:
            if response.status_code == 200:
                response.success()
            else:
                response.failure(f"Fallo descarga: {response.status_code}")

    @task(1)
    def create_dataset_from_cart(self):
        """
        Simula la creación de un dataset combinado.
        """
        # Endpoint espera form-data (no json) según routes.py (request.form.get)
        data = {
            "title": "Load Test Dataset",
            "description": "Created by Locust",
            "publication_type": "report",
            "tags": "load, test",
            "selected_datasets": "1, 2",
        }

        # Nota: Si el usuario no está logueado (on_start), esto dará 401 o redirigirá al login
        self.client.post("/explore/create-dataset-from-cart", data=data)
