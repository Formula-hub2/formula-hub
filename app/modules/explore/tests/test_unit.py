from unittest.mock import MagicMock, patch

import pytest

from app import db
from app.modules.auth.models import User, UserSession
from app.modules.dataset.models import DataSet, DSMetaData, PublicationType


@pytest.fixture
def setup_combined_scenario(test_client):
    """
    Crea un usuario y 2 datasets para probar la funcionalidad.
    """
    # Limpieza por si habían fallos anteriores
    db.session.rollback()

    # Limpiar sesiones antiguas
    UserSession.query.filter(UserSession.user.has(email="userprueba@example.com")).delete()

    # 1. Crea el usuario
    user = User.query.filter_by(email="userprueba@example.com").first()
    if not user:
        user = User(email="userprueba@example.com", password="1234")
        db.session.add(user)
        db.session.commit()

    # 2. Crear Dataset A (Con descripción obligatoria)
    meta1 = DSMetaData(
        title="Dataset A",
        description="Description for Dataset A",
        publication_type=PublicationType.JOURNAL_ARTICLE,
        tags="tag1",
    )
    db.session.add(meta1)
    db.session.commit()

    ds1 = DataSet(user_id=user.id, ds_meta_data_id=meta1.id)
    db.session.add(ds1)

    # 3. Crear Dataset B (Con descripción obligatoria)
    meta2 = DSMetaData(
        title="Dataset B",
        description="Description for Dataset B",
        publication_type=PublicationType.REPORT,
        tags="tag2",
    )
    db.session.add(meta2)
    db.session.commit()

    ds2 = DataSet(user_id=user.id, ds_meta_data_id=meta2.id)
    db.session.add(ds2)

    db.session.commit()

    ids = {"user_id": user.id, "ds1_id": ds1.id, "ds2_id": ds2.id}

    yield ids

    try:
        # Limpiar sesiones primero
        UserSession.query.filter(UserSession.user_id == user.id).delete()

        # Borrado en orden
        DataSet.query.filter(DataSet.id.in_([ds1.id, ds2.id])).delete()
        DSMetaData.query.filter(DSMetaData.id.in_([meta1.id, meta2.id])).delete()
        User.query.filter_by(id=user.id).delete()
        db.session.commit()
    except Exception:
        db.session.rollback()


# TEST 1: CREAR DATASET COMBINADO EXITOSO
def test_create_combined_dataset_success(test_client, setup_combined_scenario):
    """
    Prueba que el controlador recibe los IDs y llama al servicio correctamente.
    """
    data_ids = setup_combined_scenario
    ds1_id = data_ids["ds1_id"]
    ds2_id = data_ids["ds2_id"]
    user_id = data_ids["user_id"]

    # Simulamos Login: creamos una UserSession válida
    session_id = f"test-session-{user_id}"
    session_token = f"test-token-{user_id}"

    # Evita insertar duplicados si otro test ya creó esta sesión.
    existing = UserSession.query.filter_by(session_id=session_id).first()
    if existing:
        # Actualiza el token
        existing.flask_session_token = session_token
        db.session.add(existing)
        db.session.commit()
    else:
        user_session = UserSession(user_id=user_id, session_id=session_id, flask_session_token=session_token)
        db.session.add(user_session)
        db.session.commit()

    with test_client.session_transaction() as sess:
        sess["_user_id"] = str(user_id)
        sess["session_id"] = session_id
        sess["session_token"] = session_token

    # Mock del servicio para evitar operaciones de ficheros reales
    with patch("app.modules.explore.routes.dataset_service") as mock_service:
        mock_new_ds = MagicMock()
        mock_new_ds.id = 999
        mock_service.create_combined_dataset.return_value = mock_new_ds

        payload = {
            "title": "Combined Dataset Title",
            "description": "Description combined",
            "publication_type": "book",
            "tags": "tagA, tagB",
            "selected_datasets": f"{ds1_id},{ds2_id}",
        }

        response = test_client.post("/explore/create-dataset-from-cart", data=payload)

        assert response.status_code == 200
        assert response.json["success"] is True

        mock_service.create_combined_dataset.assert_called_once()
        call_args = mock_service.create_combined_dataset.call_args[1]
        # Aseguramos que los IDs se pasaron como una lista
        assert sorted(call_args["source_dataset_ids"]) == sorted([ds1_id, ds2_id])


# TEST 2: CREAR DATASET ESTANDO EL CARRITO VACÍO
def test_create_dataset_with_empty_cart(test_client, setup_combined_scenario):
    """
    Prueba el fallo cuando no se añaden datasets.
    """
    user_id = setup_combined_scenario["user_id"]

    # Simulamos login
    session_id = f"test-session-{user_id}"
    session_token = f"test-token-{user_id}"

    # Verificamos si ya existe la sesión
    existing_session = UserSession.query.filter_by(session_id=session_id).first()
    if existing_session:
        # Usar la sesión existente
        user_session = existing_session
        user_session.flask_session_token = session_token
    else:
        # Crear nueva sesión
        user_session = UserSession(user_id=user_id, session_id=session_id, flask_session_token=session_token)
        db.session.add(user_session)

    try:
        db.session.commit()
    except Exception:
        db.session.rollback()
        # Si hay error de duplicado, usar la anterior
        existing_session = UserSession.query.filter_by(session_id=session_id).first()
        if existing_session:
            user_session = existing_session
        else:
            raise

    with test_client.session_transaction() as sess:
        sess["_user_id"] = str(user_id)
        sess["session_id"] = session_id
        sess["session_token"] = session_token

    payload = {"title": "Fail Dataset", "selected_datasets": ""}

    response = test_client.post("/explore/create-dataset-from-cart", data=payload)

    assert response.status_code != 200 or response.json.get("success") is False


# TEST 3: LÓGICA DEL CARRITO
def test_session_cart_logic(test_client):
    """
    Prueba la lógica de manipulación de lista del carrito.
    """

    # 1. Inicia y añade dataset 1
    with test_client.session_transaction() as sess:
        sess["cart"] = []
        cart = sess["cart"]
        cart.append(1)
        sess["cart"] = cart

    # Verifica que se mantiene
    with test_client.session_transaction() as sess:
        assert 1 in sess["cart"]
        assert len(sess["cart"]) == 1

    # 2. Intenta añadir duplicado (dataset 1)
    with test_client.session_transaction() as sess:
        cart = sess["cart"]
        if 1 not in cart:
            cart.append(1)
        sess["cart"] = cart

    # Verifica que NO se duplicó
    with test_client.session_transaction() as sess:
        assert len(sess["cart"]) == 1

    # 3. Añade dataset nuevo (2)
    with test_client.session_transaction() as sess:
        cart = sess["cart"]
        cart.append(2)
        sess["cart"] = cart

    # Verifica el contador (Debería haber 2)
    with test_client.session_transaction() as sess:
        assert len(sess["cart"]) == 2
        assert 2 in sess["cart"]

    # 4. Elimina dataset 1
    with test_client.session_transaction() as sess:
        cart = sess["cart"]
        if 1 in cart:
            cart.remove(1)
        sess["cart"] = cart

    # Verifica el final
    with test_client.session_transaction() as sess:
        assert 1 not in sess["cart"]
        assert 2 in sess["cart"]
        assert len(sess["cart"]) == 1
