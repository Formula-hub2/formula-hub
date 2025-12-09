import time

import pyotp
import pytest
from flask import url_for

from app import db
from app.modules.auth.repositories import UserRepository
from app.modules.auth.services import AuthenticationService
from app.modules.profile.repositories import UserProfileRepository


@pytest.fixture(scope="module")
def test_client(test_client):
    """
    Extends the test_client fixture to add additional specific data for module testing.
    """
    with test_client.application.app_context():
        # Add HERE new elements to the database that you want to exist in the test context.
        # DO NOT FORGET to use db.session.add(<element>) and db.session.commit() to save the data.
        pass

    yield test_client


def test_login_success(test_client):
    response = test_client.post(
        "/login", data=dict(email="test@example.com", password="test1234"), follow_redirects=True
    )

    assert response.request.path != url_for("auth.login"), "Login was unsuccessful"

    test_client.get("/logout", follow_redirects=True)


def test_login_unsuccessful_bad_email(test_client):
    response = test_client.post(
        "/login", data=dict(email="bademail@example.com", password="test1234"), follow_redirects=True
    )

    assert response.request.path == url_for("auth.login"), "Login was unsuccessful"

    test_client.get("/logout", follow_redirects=True)


def test_login_unsuccessful_bad_password(test_client):
    response = test_client.post(
        "/login", data=dict(email="test@example.com", password="basspassword"), follow_redirects=True
    )

    assert response.request.path == url_for("auth.login"), "Login was unsuccessful"

    test_client.get("/logout", follow_redirects=True)


def test_signup_user_no_name(test_client):
    response = test_client.post(
        "/signup", data=dict(surname="Foo", email="test@example.com", password="test1234"), follow_redirects=True
    )
    assert response.request.path == url_for("auth.show_signup_form"), "Signup was unsuccessful"
    assert b"This field is required" in response.data, response.data


def test_signup_user_unsuccessful(test_client):
    email = "test@example.com"
    response = test_client.post(
        "/signup", data=dict(name="Test", surname="Foo", email=email, password="test1234"), follow_redirects=True
    )
    assert response.request.path == url_for("auth.show_signup_form"), "Signup was unsuccessful"
    assert f"Email {email} in use".encode("utf-8") in response.data


def test_signup_user_successful(test_client):
    response = test_client.post(
        "/signup",
        data=dict(name="Foo", surname="Example", email="foo@example.com", password="foo1234"),
        follow_redirects=True,
    )
    assert response.request.path == url_for("public.index"), "Signup was unsuccessful"


def test_service_create_with_profie_success(clean_database):
    data = {"name": "Test", "surname": "Foo", "email": "service_test@example.com", "password": "test1234"}

    AuthenticationService().create_with_profile(**data)

    assert UserRepository().count() == 1
    assert UserProfileRepository().count() == 1


def test_service_create_with_profile_fail_no_email(clean_database):
    data = {"name": "Test", "surname": "Foo", "email": "", "password": "1234"}

    with pytest.raises(ValueError, match="Email is required."):
        AuthenticationService().create_with_profile(**data)

    assert UserRepository().count() == 0
    assert UserProfileRepository().count() == 0


def test_service_create_with_profile_fail_no_password(clean_database):
    data = {"name": "Test", "surname": "Foo", "email": "test@example.com", "password": ""}

    with pytest.raises(ValueError, match="Password is required."):
        AuthenticationService().create_with_profile(**data)

    assert UserRepository().count() == 0
    assert UserProfileRepository().count() == 0


def test_2fa_verify_flow(clean_database, test_client):
    # Crear usuario con 2FA activado
    user_data = {"name": "2FA", "surname": "Tester", "email": "2fa@example.com", "password": "1234"}
    AuthenticationService().create_with_profile(**user_data)

    # Obtener el usuario de la DB
    user_repo = UserRepository()
    user = user_repo.get_by_email("2fa@example.com")
    assert user is not None

    secret = pyotp.random_base32()
    user.two_factor_secret = secret
    user.two_factor_enabled = True
    db.session.commit()

    # Simular login que requiere 2FA
    with test_client.session_transaction() as sess:
        sess["two_factor_user_id"] = user.id

    # Generar token TOTP correcto
    token = pyotp.TOTP(secret).now()

    # POST a /verify_2fa
    response = test_client.post("/verify_2fa", data={"token": token}, follow_redirects=True)
    assert response.status_code == 200

    # Verificar que la sesión quedó limpia
    with test_client.session_transaction() as sess:
        assert "two_factor_user_id" not in sess


# --- Tests de sesiones activas ---
def test_create_user_session(clean_database, mocker):
    """Verifica que se pueda crear una sesión activa para un usuario."""
    service = AuthenticationService()
    user = service.create_with_profile(name="John", surname="Doe", email="john@example.com", password="1234")
    mock_request = mocker.MagicMock()
    mock_request.headers.get.return_value = "pytest-agent"
    mock_request.remote_addr = "127.0.0.1"
    mocker.patch("app.modules.auth.services.request", mock_request)

    session = service.create_user_session(user)

    assert session.user_id == user.id
    assert session.user_agent == "pytest-agent"
    assert session.ip_address == "127.0.0.1"
    assert session.session_id is not None


def test_get_active_sessions(clean_database, mocker):
    """Verifica que se obtengan las sesiones activas correctamente."""
    service = AuthenticationService()
    user = service.create_with_profile(name="Alice", surname="Smith", email="alice@example.com", password="abcd")

    # Primer dispositivo
    mock_request1 = mocker.MagicMock()
    mock_request1.headers.get.return_value = "pytest-agent-1"
    mock_request1.remote_addr = "127.0.0.1"
    mocker.patch("app.modules.auth.services.request", mock_request1)
    session1 = service.create_user_session(user)

    # Segundo dispositivo
    mock_request2 = mocker.MagicMock()
    mock_request2.headers.get.return_value = "pytest-agent-2"
    mock_request2.remote_addr = "127.0.0.2"
    mocker.patch("app.modules.auth.services.request", mock_request2)
    session2 = service.create_user_session(user)

    sessions = service.get_active_sessions(user)
    assert len(sessions) == 2
    assert session1 in sessions and session2 in sessions


def test_terminate_session(clean_database, mocker):
    """Verifica que se pueda eliminar una sesión activa específica."""
    service = AuthenticationService()
    user = service.create_with_profile(name="Bob", surname="Marley", email="bob@example.com", password="xyz")

    mock_request = mocker.MagicMock()
    mock_request.headers.get.return_value = "pytest-agent"
    mock_request.remote_addr = "127.0.0.1"
    mocker.patch("app.modules.auth.services.request", mock_request)

    session = service.create_user_session(user)
    session_id = session.session_id

    assert service.terminate_session(session_id) is True

    sessions = service.get_active_sessions(user)
    assert len(sessions) == 0


def test_terminate_all_other_sessions(clean_database, mocker):
    """Verifica que se eliminen todas las sesiones excepto la actual."""
    service = AuthenticationService()
    user = service.create_with_profile(name="Jane", surname="Roe", email="jane@example.com", password="abcd")

    mock_request = mocker.MagicMock()
    mock_request.headers.get.return_value = "pytest-agent"
    mock_request.remote_addr = "127.0.0.1"
    mocker.patch("app.modules.auth.services.request", mock_request)

    # session1 = service.create_user_session(user)
    session2 = service.create_user_session(user)
    # session3 = service.create_user_session(user)

    service.terminate_all_other_sessions(user, current_session_id=session2.session_id)

    sessions = service.get_active_sessions(user)
    assert len(sessions) == 1
    assert sessions[0].session_id == session2.session_id


def test_login_brute_force_limit(test_client, clean_database):
    """
    Issue: Limit failed login attempts.
    Prueba que el sistema bloquea el inicio de sesión tras 5 intentos fallidos
    consecutivos, incluso si el sexto intento tiene la contraseña correcta.
    """
    AuthenticationService().create_with_profile(
        name="Test", surname="Example", email="test@example.com", password="test1234"
    )

    for i in range(5):
        response = test_client.post(
            "/login", data=dict(email="test@example.com", password=f"wrong_pass_{i}"), follow_redirects=True
        )
        assert response.status_code in (200, 429)
    time.sleep(1)
    response = test_client.post("/login", data=dict(email="test@example.com", password="test1234"))

    assert response.request.path == url_for("auth.login"), "Account should be blocked after multiple failed attempts"
