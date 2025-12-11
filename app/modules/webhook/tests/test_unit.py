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


# --- 3. TESTS DE SERVICIOS (SERVICES) ---
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
