from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import text

from app import db
from app.modules.auth.models import User
from app.modules.dataset.models import DataSet, DSDownloadRecord, DSMetaData, PublicationType, RawDataSet, UVLDataSet
from app.modules.dataset.services import DataSetService, RawDataSetService, UVLDataSetService


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

    assert dataset_refreshed.download_count >= 1


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


def test_uvl_create_from_form_happy_path():
    """
    Verifica que el servicio orquesta todo: metadatos, autores, dataset, fm y ficheros.
    """
    # 1. Instanciar servicio y BLINDAR todas las dependencias con Mocks
    service = UVLDataSetService()
    service.repository = MagicMock()
    service.dsmetadata_repository = MagicMock()
    service.author_repository = MagicMock()
    service.feature_model_repository = MagicMock()
    service.fmmetadata_repository = MagicMock()
    service.hubfilerepository = MagicMock()

    # 2. Mockear el formulario
    mock_form = MagicMock()
    mock_form.get_dsmetadata.return_value = {"title": "Test"}
    mock_form.get_authors.return_value = []

    # Simular un feature model dentro del form
    fm_form = MagicMock()
    fm_form.uvl_filename.data = "test.uvl"
    fm_form.get_fmmetadata.return_value = {}
    fm_form.get_authors.return_value = []
    # Aseguramos que sea iterable
    mock_form.feature_models = [fm_form]

    # 3. Mockear usuario
    mock_user = MagicMock()
    mock_user.id = 1
    mock_user.temp_folder.return_value = "/tmp"

    # 4. Ejecutar con patch del cálculo de hash
    with patch("app.modules.dataset.services.calculate_checksum_and_size", return_value=("hash", 100)):
        service.create_from_form(mock_form, mock_user)

    # 5. Verificaciones
    # Verificar que se llamó al commit
    service.repository.session.commit.assert_called_once()

    # Verificar creación de componentes
    service.dsmetadata_repository.create.assert_called()
    service.repository.create.assert_called()
    service.hubfilerepository.create.assert_called()


def test_uvl_create_rollback_on_error():
    """
    Si falla el cálculo del hash, debe hacer rollback.
    """
    service = UVLDataSetService()

    # Mockear TODOS los repositorios para evitar usar objetos reales
    service.repository = MagicMock()
    service.dsmetadata_repository = MagicMock()
    service.author_repository = MagicMock()
    service.feature_model_repository = MagicMock()
    service.fmmetadata_repository = MagicMock()
    service.hubfilerepository = MagicMock()

    # Configurar mocks para que devuelvan objetos válidos hasta el punto de fallo
    service.dsmetadata_repository.create.return_value = MagicMock(id=1)

    mock_form = MagicMock()
    mock_form.feature_models = [MagicMock()]

    # Simular fallo en disco (hash calculation error)
    with patch("app.modules.dataset.services.calculate_checksum_and_size", side_effect=Exception("Disk Fail")):
        try:
            service.create_from_form(mock_form, MagicMock())
        except Exception:
            pass  # Esperamos el error, continuamos para verificar el rollback

    # Verificar limpieza
    service.repository.session.rollback.assert_called_once()
    service.repository.session.commit.assert_not_called()


def test_create_combined_dataset_file_copying():
    """
    Simula la creación de un dataset combinado asegurando que se copian los archivos físicos.
    """
    # Setup del servicio base
    service = DataSetService()
    service.repository = MagicMock()
    service.dsmetadata_repository = MagicMock()

    # Mockear el dataset origen (source)
    source_ds = MagicMock(spec=UVLDataSet)
    source_ds.id = 99
    source_ds.user_id = 5

    # Mockear un feature model dentro del origen
    fm_mock = MagicMock()
    fm_mock.fm_meta_data = MagicMock()
    file_mock = MagicMock()
    file_mock.name = "original.uvl"
    fm_mock.files = [file_mock]
    source_ds.feature_models = [fm_mock]

    # Mockear la recuperación del dataset por ID
    service.get_or_404 = MagicMock(return_value=source_ds)

    with (
        patch("app.modules.dataset.services.os.makedirs") as mock_mkdirs,
        patch("app.modules.dataset.services.os.path.exists", return_value=True),
        patch("app.modules.dataset.services.shutil.copy2") as mock_copy,
    ):

        # Ejecutar
        service.create_combined_dataset(
            current_user=MagicMock(id=1),
            title="Combined",
            description="Desc",
            publication_type="annotationcollection",
            tags="tag",
            source_dataset_ids=[99],
        )

        # Aserciones Clave
        # 1. Se intentó crear carpeta de destino
        mock_mkdirs.assert_called()

        # 2. Se intentó copiar el archivo (Verificamos la lógica de copy2)
        assert mock_copy.call_count == 1
        args, _ = mock_copy.call_args
        assert "original.uvl" in args[0]
        assert "dataset_99" in args[0]


def test_raw_dataset_creation_metadata():
    """
    Verifica que RawDataSetService asigna correctamente los metadatos y autores.
    """
    service = RawDataSetService()
    service.repository = MagicMock()
    service.dsmetadata_repository = MagicMock()
    service.author_repository = MagicMock()

    mock_form = MagicMock()
    mock_form.get_dsmetadata.return_value = {"title": "Raw Data"}

    mock_user = MagicMock()
    mock_user.profile.surname = "Doe"

    # Ejecutar
    service.create_from_form(mock_form, mock_user)

    # Verificar que se creó el autor por defecto (el usuario logueado)
    service.author_repository.create.assert_called()
    call_args = service.author_repository.create.call_args[1]
    assert "Doe" in call_args["name"]

    # Verificar commit
    service.repository.create.assert_called_with(
        commit=True, user_id=mock_user.id, ds_meta_data_id=service.dsmetadata_repository.create.return_value.id
    )


def test_create_combined_dataset_logic():
    from app.modules.dataset.models import UVLDataSet

    # Setup
    service = DataSetService()
    service.repository = MagicMock()
    service.dsmetadata_repository = MagicMock()

    # Mock source dataset
    source_ds = MagicMock(spec=UVLDataSet)
    source_ds.id = 99
    source_ds.user_id = 5
    # Mock Feature Model
    fm_mock = MagicMock()
    fm_mock.fm_meta_data = MagicMock()
    fm_mock.files = [MagicMock(name="file.uvl", checksum="123", size=10)]
    source_ds.feature_models = [fm_mock]

    service.get_or_404 = MagicMock(return_value=source_ds)

    # Mock OS operations
    with (
        patch("app.modules.dataset.services.os.makedirs"),
        patch("app.modules.dataset.services.os.path.exists", return_value=True),
        patch("app.modules.dataset.services.shutil.copy2") as mock_copy,
    ):

        service.create_combined_dataset(
            current_user=MagicMock(id=1),
            title="Combined",
            description="Desc",
            publication_type="annotationcollection",
            tags="tag",
            source_dataset_ids=[99],
        )

        # Verify file copy was attempted
        assert mock_copy.call_count == 1
        # Verify commit
        service.repository.session.commit.assert_called()


def test_route_list_datasets(test_client):
    """
    Verifica que la página de listado carga correctamente.
    FIX: Mockeamos current_user explícitamente porque LOGIN_DISABLED inyecta un usuario anónimo sin ID.
    """
    test_client.application.config["LOGIN_DISABLED"] = True

    with (
        patch("app.modules.dataset.routes.dataset_service") as mock_service,
        patch("app.modules.dataset.routes.current_user") as mock_user,
    ):

        mock_user.id = 1

        mock_service.get_synchronized.return_value = []
        mock_service.get_unsynchronized.return_value = []

        response = test_client.get("/dataset/list")

    test_client.application.config["LOGIN_DISABLED"] = False

    assert response.status_code == 200
    mock_service.get_synchronized.assert_called()


def test_route_file_delete_async(test_client):
    """
    Verifica el borrado de archivos.
    FIX: Usamos new_callable=MagicMock para evitar que pytest cree un AsyncMock por error.
    """
    # Caso 1: Archivo existe
    with (
        patch("app.modules.dataset.routes.os.path.exists", return_value=True),
        patch("app.modules.dataset.routes.os.remove") as mock_remove,
        patch("app.modules.dataset.routes.current_user", new_callable=MagicMock) as mock_user,
    ):

        mock_user.temp_folder.return_value = "/tmp"

        response = test_client.post("/dataset/file/delete", json={"file": "borrame.uvl"})

        assert response.status_code == 200
        assert response.json == {"message": "File deleted successfully"}
        mock_remove.assert_called()

    # Caso 2: Archivo NO existe
    with (
        patch("app.modules.dataset.routes.os.path.exists", return_value=False),
        patch("app.modules.dataset.routes.current_user", new_callable=MagicMock) as mock_user,
    ):

        mock_user.temp_folder.return_value = "/tmp"
        response = test_client.post("/dataset/file/delete", json={"file": "fantasma.uvl"})

        assert response.json == {"error": "Error: File not found"}


def test_route_view_dataset_forbidden(test_client):
    """
    Verifica que un usuario no puede ver un dataset no sincronizado de otro usuario.
    Cubre: GET /dataset/view/<id> (Lógica de permisos 403)
    """
    test_client.application.config["LOGIN_DISABLED"] = True  # Bypass @login_required

    with (
        patch("app.modules.dataset.routes.dataset_service") as mock_service,
        patch("app.modules.dataset.routes.current_user") as mock_user,
    ):

        # Simulamos dataset perteneciente al usuario 99
        mock_ds = MagicMock()
        mock_ds.user_id = 99
        mock_service.get_or_404.return_value = mock_ds

        # Simulamos que somos el usuario 1
        mock_user.is_authenticated = True
        mock_user.id = 1

        response = test_client.get("/dataset/view/100")

    test_client.application.config["LOGIN_DISABLED"] = False

    assert response.status_code == 403


def test_route_doi_redirection(test_client):
    """
    Verifica la redirección si el DOI ha cambiado.
    FIX: Añadimos '/' al final de la URL para coincidir con la definición de la ruta y evitar el 308.
    """
    with patch("app.modules.dataset.routes.doi_mapping_service") as mock_doi_service:
        mock_doi_service.get_new_doi.return_value = "new/doi/123"

        response = test_client.get("/doi/old/doi/123/")

    assert response.status_code == 302
    assert "new/doi/123" in response.location


def test_service_move_feature_models():
    """
    Verifica la lógica de movimiento físico de archivos en UVLDataSetService.
    Esta función no estaba testeada en el servicio.
    """
    service = UVLDataSetService()

    # Mock dataset y feature models
    mock_ds = MagicMock()
    mock_ds.id = 10
    mock_ds.user_id = 1

    mock_fm = MagicMock()
    mock_fm.fm_meta_data.uvl_filename = "model.uvl"
    mock_ds.feature_models = [mock_fm]

    # Mock mocks de Auth y OS
    with (
        patch("app.modules.dataset.services.AuthenticationService") as MockAuth,
        patch("app.modules.dataset.services.shutil.move") as mock_move,
        patch("app.modules.dataset.services.os.makedirs"),
    ):

        MockAuth.return_value.get_authenticated_user.return_value.temp_folder.return_value = "/tmp"
        MockAuth.return_value.get_authenticated_user.return_value.id = 1

        service.move_feature_models(mock_ds)

        mock_move.assert_called_once()
        args, _ = mock_move.call_args
        assert "model.uvl" in args[0]  # Source
        assert "dataset_10" in args[1]  # Destino


def test_form_publication_type_conversion():
    """
    Verifica el método auxiliar convert_publication_type en DataSetForm.
    A veces los tests de rutas no cubren todas las ramas de estos helpers.
    """
    from app.modules.dataset.forms import DataSetForm, PublicationType

    form = DataSetForm()

    # Caso 1: Tipo válido
    res = form.convert_publication_type(PublicationType.BOOK.value)
    assert res == "BOOK"

    # Caso 2: Tipo inválido o no coincidente
    res = form.convert_publication_type("inventado")
    assert res == "NONE"


def test_uvlhub_doi_generation():
    """
    Verifica la generación de la URL del DOI.
    """
    from app.modules.dataset.services import DataSetService

    service = DataSetService()
    mock_ds = MagicMock()
    mock_ds.ds_meta_data.dataset_doi = "10.1234/foo"

    with patch("app.modules.dataset.services.os.getenv", return_value="uvlhub.io"):
        url = service.get_uvlhub_doi(mock_ds)
        assert url == "http://uvlhub.io/doi/10.1234/foo"
