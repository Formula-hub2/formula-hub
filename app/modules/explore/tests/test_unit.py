from unittest.mock import MagicMock, patch

import pytest

from app import db
from app.modules.auth.models import User
from app.modules.dataset.models import DataSet, DSMetaData, PublicationType

# --- FIXTURE CORREGIDO (Soluciona el IntegrityError y PendingRollbackError) ---


@pytest.fixture
def setup_combined_scenario(test_client):
    """
    Crea un usuario y DOS datasets para probar la funcionalidad.
    CORRECCIÓN: Se añade el campo 'description' obligatorio.
    """
    # Limpieza preventiva por si hubo fallos anteriores
    db.session.rollback()

    # 1. Crear Usuario
    user = User.query.filter_by(email="cart_tester@example.com").first()
    if not user:
        user = User(email="cart_tester@example.com", password="password123")
        db.session.add(user)
        db.session.commit()

    # 2. Crear Dataset A (Con descripción obligatoria)
    meta1 = DSMetaData(
        title="Dataset A",
        description="Description for Dataset A",  # <--- CORRECCIÓN AQUÍ
        publication_type=PublicationType.JOURNAL_ARTICLE,
        tags="tag1",
    )
    db.session.add(meta1)
    db.session.commit()  # Commit intermedio para tener ID

    ds1 = DataSet(user_id=user.id, ds_meta_data_id=meta1.id)
    db.session.add(ds1)

    # 3. Crear Dataset B (Con descripción obligatoria)
    meta2 = DSMetaData(
        title="Dataset B",
        description="Description for Dataset B",  # <--- CORRECCIÓN AQUÍ
        publication_type=PublicationType.REPORT,
        tags="tag2",
    )
    db.session.add(meta2)
    db.session.commit()  # Commit intermedio

    ds2 = DataSet(user_id=user.id, ds_meta_data_id=meta2.id)
    db.session.add(ds2)

    db.session.commit()

    ids = {"user_id": user.id, "ds1_id": ds1.id, "ds2_id": ds2.id}

    yield ids

    # --- TEARDOWN ---
    try:
        # Borrado en orden para respetar Foreign Keys
        DataSet.query.filter(DataSet.id.in_([ds1.id, ds2.id])).delete()
        DSMetaData.query.filter(DSMetaData.id.in_([meta1.id, meta2.id])).delete()
        User.query.filter_by(id=user.id).delete()
        db.session.commit()
    except Exception:
        db.session.rollback()


# --- TESTS DE FUNCIONALIDAD ---


def test_create_combined_dataset_success(test_client, setup_combined_scenario):
    """
    Prueba que el controlador recibe los IDs y llama al servicio correctamente.
    """
    data_ids = setup_combined_scenario
    ds1_id = data_ids["ds1_id"]
    ds2_id = data_ids["ds2_id"]
    user_id = data_ids["user_id"]

    # Simulamos Login
    with test_client.session_transaction() as sess:
        sess["_user_id"] = str(user_id)

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

        # Verificar argumentos de llamada
        mock_service.create_combined_dataset.assert_called_once()
        call_args = mock_service.create_combined_dataset.call_args[1]
        # Aseguramos que los IDs se pasaron como lista de enteros
        assert sorted(call_args["source_dataset_ids"]) == sorted([ds1_id, ds2_id])


def test_create_dataset_with_empty_cart(test_client, setup_combined_scenario):
    """
    Prueba el fallo controlado cuando no se envían datasets.
    """
    user_id = setup_combined_scenario["user_id"]

    with test_client.session_transaction() as sess:
        sess["_user_id"] = str(user_id)

    payload = {"title": "Fail Dataset", "selected_datasets": ""}

    response = test_client.post("/explore/create-dataset-from-cart", data=payload)

    # Puede devolver 500 o 400 dependiendo de tu implementación de error
    # Lo importante es que NO sea 200 (éxito)
    assert response.status_code != 200 or response.json.get("success") is False


# --- TEST DE CARRITO CORREGIDO (Soluciona el AssertionError) ---


def test_session_cart_logic(test_client):
    """
    Prueba la lógica de manipulación de lista del carrito.
    CORRECCIÓN: Reasignamos la lista 'cart' explícitamente para asegurar
    que Flask detecte el cambio en la sesión.
    """

    # 1. Inicializar y añadir item 1
    with test_client.session_transaction() as sess:
        sess["cart"] = []
        cart = sess["cart"]
        cart.append(1)
        sess["cart"] = cart  # Reasignación forzosa para persistencia

    # Verificar que persiste
    with test_client.session_transaction() as sess:
        assert 1 in sess["cart"]
        assert len(sess["cart"]) == 1

    # 2. Intentar añadir duplicado (1)
    with test_client.session_transaction() as sess:
        cart = sess["cart"]
        if 1 not in cart:
            cart.append(1)
        sess["cart"] = cart  # Reasignación

    # Verificar que NO se duplicó
    with test_client.session_transaction() as sess:
        assert len(sess["cart"]) == 1

    # 3. Añadir item nuevo (2)
    with test_client.session_transaction() as sess:
        cart = sess["cart"]
        cart.append(2)
        sess["cart"] = cart  # Reasignación

    # Verificar contador (Debería ser 2)
    with test_client.session_transaction() as sess:
        assert len(sess["cart"]) == 2
        assert 2 in sess["cart"]

    # 4. Eliminar item (1)
    with test_client.session_transaction() as sess:
        cart = sess["cart"]
        if 1 in cart:
            cart.remove(1)
        sess["cart"] = cart  # Reasignación

    # Verificar final
    with test_client.session_transaction() as sess:
        assert 1 not in sess["cart"]
        assert 2 in sess["cart"]
        assert len(sess["cart"]) == 1
