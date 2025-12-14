from unittest.mock import MagicMock, patch

import pytest

from app import db
from app.modules.auth.models import User, UserSession
from app.modules.dataset.models import DataSet, DSMetaData, PublicationType


def force_login(client, user_id):
    """
    Helper para forzar el login simulando la sesión de usuario.
    """
    session_id = f"test-session-{user_id}"
    session_token = f"test-token-{user_id}"

    # Upsert de sesión en DB
    existing = UserSession.query.filter_by(session_id=session_id).first()
    if existing:
        existing.flask_session_token = session_token
    else:
        user_session = UserSession(user_id=user_id, session_id=session_id, flask_session_token=session_token)
        db.session.add(user_session)

    db.session.commit()

    # Inyección en la cookie de sesión de Flask
    with client.session_transaction() as sess:
        sess["_user_id"] = str(user_id)
        sess["session_id"] = session_id
        sess["session_token"] = session_token


@pytest.fixture
def sample_data(test_client):
    """Fixture que prepara 1 Usuario y 2 Datasets."""
    # 1. Setup
    user = User(email="userprueba@example.com", password="1234")
    db.session.add(user)
    db.session.commit()

    meta1 = DSMetaData(
        title="DS A", description="Desc A", publication_type=PublicationType.JOURNAL_ARTICLE, tags="tag1"
    )
    meta2 = DSMetaData(title="DS B", description="Desc B", publication_type=PublicationType.REPORT, tags="tag2")
    db.session.add_all([meta1, meta2])
    db.session.commit()

    ds1 = DataSet(user_id=user.id, ds_meta_data_id=meta1.id)
    ds2 = DataSet(user_id=user.id, ds_meta_data_id=meta2.id)
    db.session.add_all([ds1, ds2])
    db.session.commit()

    ids = {"user_id": user.id, "ds1_id": ds1.id, "ds2_id": ds2.id}

    yield ids

    # 2. Teardown
    try:
        UserSession.query.filter(UserSession.user_id == user.id).delete()
        DataSet.query.filter(DataSet.user_id == user.id).delete()
        DSMetaData.query.filter(DSMetaData.id.in_([meta1.id, meta2.id])).delete()
        User.query.filter(User.id == user.id).delete()
        db.session.commit()
    except Exception:
        db.session.rollback()


def test_create_combined_dataset_success(test_client, sample_data):
    """Prueba el flujo exitoso."""
    ids = sample_data
    force_login(test_client, ids["user_id"])

    with patch("app.modules.explore.routes.dataset_service") as mock_service:
        mock_new_ds = MagicMock()
        mock_new_ds.id = 999
        mock_service.create_combined_dataset.return_value = mock_new_ds

        payload = {
            "title": "Combined Dataset",
            "description": "Combined Desc",
            "publication_type": "book",
            "tags": "tagA, tagB",
            "selected_datasets": f"{ids['ds1_id']},{ids['ds2_id']}",
        }

        response = test_client.post("/explore/create-dataset-from-cart", data=payload)

        assert response.status_code == 200
        assert response.json["success"] is True

        mock_service.create_combined_dataset.assert_called_once()
        call_kwargs = mock_service.create_combined_dataset.call_args[1]

        sent_ids = sorted([int(x) for x in call_kwargs["source_dataset_ids"]])
        expected_ids = sorted([ids["ds1_id"], ids["ds2_id"]])
        assert sent_ids == expected_ids


def test_create_dataset_with_empty_cart(test_client, sample_data):
    """
    Prueba fallo con carrito vacío.
    Debe detectar si la app responde con error (400) o redirección (302).
    """
    force_login(test_client, sample_data["user_id"])

    payload = {"title": "Fail Dataset", "selected_datasets": ""}

    response = test_client.post("/explore/create-dataset-from-cart", data=payload)

    # Aceptamos 302 (Found/Redirect) o 400 (Bad Request)
    assert response.status_code in [
        302,
        400,
    ], f"Se esperaba redirección (302) o error (400), se recibió {response.status_code}"


def test_session_cart_persistence(test_client):
    """
    Verifica persistencia de sesión.
    """
    # 1. Modificar sesión inicial
    with test_client.session_transaction() as sess:
        sess["cart"] = [101, 102]

    # 2. Leer y modificar en nueva transacción (simulando nueva petición)
    with test_client.session_transaction() as sess:
        assert "cart" in sess
        assert sess["cart"] == [101, 102]

        current_cart = sess["cart"]
        current_cart.append(103)
        sess["cart"] = current_cart

    # 3. Verificar persistencia final
    with test_client.session_transaction() as sess:
        assert 103 in sess["cart"]
        assert len(sess["cart"]) == 3
