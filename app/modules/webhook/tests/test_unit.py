import subprocess
from unittest.mock import MagicMock, patch

import pytest
from werkzeug.exceptions import InternalServerError, NotFound

from app.modules.webhook.forms import WebhookForm
from app.modules.webhook.models import Webhook
from app.modules.webhook.repositories import WebhookRepository
from app.modules.webhook.services import WebhookService


@pytest.fixture(scope="module")
def test_client(test_client):
    """
    Fixture extendido.
    Forzamos el registro manual del blueprint aquí para asegurar que los tests
    funcionan independientemente de si el ModuleManager lo cargó o no.
    """
    with test_client.application.app_context():
        # 1. Importamos las rutas y el blueprint manualmente
        # Esto es vital: al importar 'routes', se ejecutan los decoradores y se llena el blueprint
        from app.modules.webhook import routes  # noqa: F401
        from app.modules.webhook import webhook_bp

        # 2. Registramos el blueprint si no está ya cargado en la app
        if "webhook" not in test_client.application.blueprints:
            test_client.application.register_blueprint(webhook_bp)

    yield test_client


# --- 1. TESTS DE FORMULARIOS ---
def test_webhook_form(test_client):
    with test_client.session_transaction():
        form = WebhookForm()
        assert form.submit is not None


# --- 2. TESTS DE MODELOS Y REPOSITORIOS ---
def test_webhook_model_and_repo(test_client):
    webhook = Webhook()
    assert webhook.id is None
    repo = WebhookRepository()
    assert repo.model == Webhook


# --- 3. TESTS DE RUTAS (ROUTES) ---
def test_deploy_route_unauthorized(test_client):
    """Prueba que la ruta rechaza peticiones sin token correcto"""

    # DEBUG: Imprimir rutas para confirmar registro
    print("\n=== RUTAS REGISTRADAS ===")
    for rule in test_client.application.url_map.iter_rules():
        if "deploy" in str(rule):
            print(f"Ruta encontrada: {rule}")
    print("=========================\n")

    # URL Duplicada: Prefijo del módulo (/webhook) + Ruta en archivo (/webhook/deploy)
    target_url = "webhook/deploy"

    with patch("app.modules.webhook.routes.WEBHOOK_TOKEN", "SECRET"):
        # Intento sin header
        response = test_client.post(target_url)
        assert response.status_code == 403

        # Intento con token incorrecto
        response = test_client.post(target_url, headers={"Authorization": "Bearer WRONG"})
        assert response.status_code == 403


def test_deploy_route_success(test_client):
    """Prueba el flujo completo exitoso"""
    target_url = "webhook/deploy"

    # Mockeamos el servicio para no ejecutar comandos reales
    with patch("app.modules.webhook.routes.WebhookService") as MockServiceClass:
        mock_instance = MockServiceClass.return_value
        mock_container = MagicMock()
        mock_instance.get_web_container.return_value = mock_container

        with patch("app.modules.webhook.routes.WEBHOOK_TOKEN", "SUPER_SECRET"):
            response = test_client.post(target_url, headers={"Authorization": "Bearer SUPER_SECRET"})

            assert response.status_code == 200
            assert b"Deployment successful" in response.data

            mock_instance.get_web_container.assert_called_once()
            assert mock_instance.execute_container_command.call_count >= 3


# --- 4. TESTS DE SERVICIOS (SERVICES) ---
def test_service_get_web_container_success():
    """Prueba obtener el contenedor (parcheando la variable global 'client')"""
    # IMPORTANTE: Parcheamos 'client' porque NO usas lazy loading
    with patch("app.modules.webhook.services.client") as mock_client:
        mock_container = MagicMock()
        mock_client.containers.get.return_value = mock_container

        service = WebhookService()
        result = service.get_web_container()

        assert result == mock_container
        mock_client.containers.get.assert_called_with("web_app_container")


def test_service_get_web_container_not_found():
    """Prueba error 404 si no existe el contenedor"""
    import docker

    with patch("app.modules.webhook.services.client") as mock_client:
        mock_client.containers.get.side_effect = docker.errors.NotFound("Not found")

        service = WebhookService()

        with pytest.raises(NotFound):
            service.get_web_container()


def test_service_execute_container_command_success():
    service = WebhookService()
    mock_container = MagicMock()
    mock_container.exec_run.return_value = (0, b"Success output")

    output = service.execute_container_command(mock_container, "echo test")
    assert output == "Success output"


def test_service_execute_container_command_failure():
    service = WebhookService()
    mock_container = MagicMock()
    mock_container.exec_run.return_value = (1, b"Error output")

    with pytest.raises(InternalServerError):
        service.execute_container_command(mock_container, "bad command")


def test_service_get_volume_name():
    service = WebhookService()
    mock_container = MagicMock()
    mock_container.attrs = {"Mounts": [{"Destination": "/app", "Name": "correct_vol"}]}
    vol_name = service.get_volume_name(mock_container)
    assert vol_name == "correct_vol"

    mock_container_bad = MagicMock()
    mock_container_bad.attrs = {"Mounts": [{"Destination": "/db"}]}
    with pytest.raises(ValueError):
        service.get_volume_name(mock_container_bad)


def test_service_restart_container():
    service = WebhookService()
    mock_container = MagicMock()
    mock_container.id = "12345"

    with patch("app.modules.webhook.services.subprocess.Popen") as mock_popen:
        service.restart_container(mock_container)

        mock_popen.assert_called_once()
        args = mock_popen.call_args[0][0]
        assert args[0] == "/bin/sh"
        assert "/app/scripts/restart_container.sh" in args


def test_service_execute_host_command_success():
    """Prueba el método execute_host_command (que usa subprocess en el host)"""
    service = WebhookService()

    # Simulamos subprocess.run
    with patch("app.modules.webhook.services.subprocess.run") as mock_run:
        service.execute_host_command("my_volume", ["echo", "hello"])

        mock_run.assert_called_once()
        args = mock_run.call_args[0][0]
        # Verificamos que construye bien el comando docker run
        assert args[0] == "docker"
        assert "my_volume:/app" in args


def test_service_execute_host_command_failure():
    """Prueba el fallo de execute_host_command"""
    service = WebhookService()

    # Simulamos que subprocess lanza un error
    with patch("app.modules.webhook.services.subprocess.run") as mock_run:
        mock_run.side_effect = subprocess.CalledProcessError(1, "cmd")

        with pytest.raises(InternalServerError):
            service.execute_host_command("my_volume", ["echo", "fail"])


def test_service_log_deployment():
    """Prueba que log_deployment construye y envía el comando de log correctamente"""
    service = WebhookService()
    mock_container = MagicMock()
    # Simulamos que el comando interno del contenedor funciona bien (exit code 0)
    mock_container.exec_run.return_value = (0, b"Log appended")

    service.log_deployment(mock_container)

    # Verificamos que se llamó al comando 'echo' dentro del contenedor
    mock_container.exec_run.assert_called_once()
    args = mock_container.exec_run.call_args[0][0]

    assert "echo" in args
    assert "deployments.log" in args
    assert "Deployment successful" in args
