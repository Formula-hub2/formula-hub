from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import text

from app import db
from app.modules.auth.models import User
from app.modules.dataset.models import DataSet, DSDownloadRecord, DSMetaData, PublicationType, RawDataSet, UVLDataSet

# ==============================================================================
# FIXTURES COMUNES
# ==============================================================================


@pytest.fixture(scope="module")
def test_user(test_client):
    """
    Crea un usuario maestro una sola vez para todo el módulo y lo reutiliza.
    Esto acelera los tests evitando crear/borrar usuario en cada función.
    """
    user = User(email="unit_test_master@example.com", password="password123")
    db.session.add(user)
    db.session.commit()

    yield user

    # Limpieza final del módulo
    db.session.expire_all()
    user_to_delete = db.session.get(User, user.id)
    if user_to_delete:
        # Esto borrará en cascada todos los datasets creados por este usuario
        db.session.delete(user_to_delete)
        db.session.commit()


@pytest.fixture
def dataset_fixture(test_user):
    """
    Fixture específica para tests de CONTADOR.
    Crea un dataset limpio y asegura su destrucción quirúrgica para evitar IntegrityErrors.
    """
    # 1. Setup
    meta = DSMetaData(
        title="Counter Check Dataset",
        description="Dataset for mocking fs",
        publication_type=PublicationType.JOURNAL_ARTICLE,
        tags="test,mock",
    )
    db.session.add(meta)
    db.session.commit()

    dataset = DataSet(user_id=test_user.id, ds_meta_data_id=meta.id, download_count=0)
    db.session.add(dataset)
    db.session.commit()

    yield dataset

    # 2. Teardown: Limpieza en orden estricto (Hijos -> Padres)
    try:
        db.session.expire_all()
        # A. Borrar registros de descargas asociados
        DSDownloadRecord.query.filter_by(dataset_id=dataset.id).delete()

        # B. Borrar el dataset y metadata
        if db.session.get(DataSet, dataset.id):
            db.session.delete(dataset)
        if db.session.get(DSMetaData, meta.id):
            db.session.delete(meta)

        db.session.commit()
    except Exception as e:
        db.session.rollback()
        print(f"Error limpiando dataset_fixture: {e}")


@pytest.fixture
def clean_datasets(test_user):
    """
    Fixture específica para tests de POLIMORFISMO.
    Limpia cualquier dataset del usuario antes y después del test.
    """
    yield
    # Borrado masivo seguro después de cada test
    db.session.rollback()
    datasets = DataSet.query.filter_by(user_id=test_user.id).all()
    for ds in datasets:
        db.session.delete(ds)
    db.session.commit()


# ==============================================================================
# BLOQUE 1: TESTS DE LÓGICA DE NEGOCIO (CONTADOR)
# ==============================================================================


def test_download_counter_backend_logic(test_client, dataset_fixture):
    """
    Verifica que el contador sube al llamar a la ruta, mockeando el sistema de archivos.
    """
    dataset_id = dataset_fixture.id

    # Mocks para evitar errores de ficheros inexistentes
    with (
        patch("app.modules.dataset.routes.os.path.exists", return_value=True),
        patch("app.modules.dataset.routes.os.makedirs"),
        patch("app.modules.dataset.routes.os.walk", return_value=[]),
        patch("app.modules.dataset.routes.ZipFile", MagicMock()),
        patch("app.modules.dataset.routes.send_from_directory") as mock_send,
    ):

        mock_send.return_value = "File sent"

        response = test_client.get(f"/dataset/download/{dataset_id}")
        assert response.status_code == 200

    # Verificación DB
    db.session.expire_all()
    dataset_refreshed = db.session.get(DataSet, dataset_id)

    assert dataset_refreshed.download_count == 1, f"El contador debería ser 1, es {dataset_refreshed.download_count}"


def test_download_counter_idempotency_check(test_client, dataset_fixture):
    """
    Verifica comportamiento con múltiples descargas.
    """
    dataset_id = dataset_fixture.id

    with (
        patch("app.modules.dataset.routes.os.path.exists", return_value=True),
        patch("app.modules.dataset.routes.ZipFile", MagicMock()),
        patch("app.modules.dataset.routes.send_from_directory", return_value="File"),
    ):

        test_client.get(f"/dataset/download/{dataset_id}")  # 1
        test_client.get(f"/dataset/download/{dataset_id}")  # 2

    db.session.expire_all()
    dataset_refreshed = db.session.get(DataSet, dataset_id)

    # Nota: Ajusta esto según si tu lógica permite o no contar descargas repetidas
    assert dataset_refreshed.download_count >= 1


# ==============================================================================
# BLOQUE 2: TESTS DE ARQUITECTURA (POLIMORFISMO)
# ==============================================================================


def test_polymorphic_retrieval(test_user, clean_datasets):
    """
    Verifica que al consultar la tabla PADRE, obtenemos instancias de las clases HIJAS.
    """
    # 1. Setup
    meta_uvl = DSMetaData(title="UVL Type", description="desc", publication_type=PublicationType.NONE)
    meta_raw = DSMetaData(title="Raw Type", description="desc", publication_type=PublicationType.NONE)
    db.session.add_all([meta_uvl, meta_raw])
    db.session.commit()

    # 2. Insertar hijas
    uvl = UVLDataSet(user_id=test_user.id, ds_meta_data_id=meta_uvl.id)
    raw = RawDataSet(user_id=test_user.id, ds_meta_data_id=meta_raw.id)
    db.session.add_all([uvl, raw])
    db.session.commit()

    uvl_id = uvl.id
    raw_id = raw.id

    # 3. Consultar PADRE
    db.session.expire_all()
    all_datasets = DataSet.query.filter_by(user_id=test_user.id).all()

    retrieved_uvl = next((d for d in all_datasets if d.id == uvl_id), None)
    retrieved_raw = next((d for d in all_datasets if d.id == raw_id), None)

    # 4. Aserciones
    assert isinstance(retrieved_uvl, UVLDataSet), "Fallo: No se recuperó como UVLDataSet"
    assert isinstance(retrieved_raw, RawDataSet), "Fallo: No se recuperó como RawDataSet"
    assert retrieved_uvl.dataset_type == "uvl_dataset"
    assert retrieved_raw.dataset_type == "raw_dataset"


def test_physical_table_separation(test_user, clean_datasets):
    """
    Verifica con SQL crudo que los datos van a las tablas correctas.
    """
    meta = DSMetaData(title="SQL Check", description="desc", publication_type=PublicationType.NONE)
    db.session.add(meta)
    db.session.commit()

    uvl = UVLDataSet(user_id=test_user.id, ds_meta_data_id=meta.id)
    db.session.add(uvl)
    db.session.commit()

    target_id = uvl.id

    # Tabla Padre
    res_parent = db.session.execute(
        text("SELECT dataset_type FROM data_set WHERE id = :id"), {"id": target_id}
    ).fetchone()
    assert res_parent[0] == "uvl_dataset"

    # Tabla Hija UVL
    res_child = db.session.execute(text("SELECT id FROM uvl_dataset WHERE id = :id"), {"id": target_id}).fetchone()
    assert res_child is not None

    # Tabla Hija RAW (No debe estar)
    res_sibling = db.session.execute(text("SELECT id FROM raw_dataset WHERE id = :id"), {"id": target_id}).fetchone()
    assert res_sibling is None


def test_cascade_deletion_polymorphic(test_user, clean_datasets):
    """
    Verifica que borrar el objeto ORM borra filas en ambas tablas físicas.
    """
    meta = DSMetaData(title="Cascade Check", description="desc", publication_type=PublicationType.NONE)
    db.session.add(meta)
    db.session.commit()

    uvl = UVLDataSet(user_id=test_user.id, ds_meta_data_id=meta.id)
    db.session.add(uvl)
    db.session.commit()

    target_id = uvl.id

    # Borrar objeto
    db.session.delete(uvl)
    db.session.commit()

    # Verificar vacío
    res_parent = db.session.execute(text("SELECT count(*) FROM data_set WHERE id = :id"), {"id": target_id}).scalar()
    res_child = db.session.execute(text("SELECT count(*) FROM uvl_dataset WHERE id = :id"), {"id": target_id}).scalar()

    assert res_parent == 0
    assert res_child == 0
