import pytest

from app import db

# Ajusta estas rutas si tus modelos están en otro sitio,
# pero basándome en tu estructura deberían ser estas:
from app.modules.auth.models import User
from app.modules.dataset.models import DataSet, DSMetaData, PublicationType


@pytest.fixture
def clean_dataset_setup(test_client):
    """
    Fixture quirúrgica: Crea los datos mínimos necesarios (User, MetaData, DataSet)
    para probar el contador, y limpia todo al terminar.
    """
    # 1. Crear un Usuario (Usando tu modelo User real)
    # Usamos un email raro para asegurar que no choque con datos existentes
    user = User.query.filter_by(email="unit_test_counter@example.com").first()
    if not user:
        user = User(email="unit_test_counter@example.com", password="password123")
        db.session.add(user)
        db.session.commit()

    # 2. Crear MetaData (Necesario para el Dataset)
    meta = DSMetaData(
        title="Counter Unit Test Dataset",
        description="Dataset created purely for unit testing the download counter",
        publication_type=PublicationType.JOURNAL_ARTICLE,
        tags="test,unit",
    )
    db.session.add(meta)
    db.session.commit()

    # 3. Crear el DataSet inicializado a 0
    dataset = DataSet(user_id=user.id, ds_meta_data_id=meta.id, download_count=0)  # Forzamos 0 explícitamente
    db.session.add(dataset)
    db.session.commit()

    dataset_id = dataset.id

    # Devolvemos el ID y el cliente para usarlo en el test
    yield dataset_id

    # --- TEARDOWN (Limpieza) ---
    # Borramos en orden inverso para respetar las Foreign Keys
    try:
        # Recuperamos los objetos de nuevo por si la sesión se cerró
        ds_to_del = DataSet.query.get(dataset_id)
        if ds_to_del:
            db.session.delete(ds_to_del)

        meta_to_del = DSMetaData.query.get(meta.id)
        if meta_to_del:
            db.session.delete(meta_to_del)

        # El usuario lo dejamos o lo borramos según prefieras.
        # Normalmente en tests unitarios se borra todo.
        user_to_del = User.query.get(user.id)
        if user_to_del:
            db.session.delete(user_to_del)

        db.session.commit()
    except Exception as e:
        print(f"Error en limpieza de test: {e}")
        db.session.rollback()


def test_download_counter_backend_logic(test_client, clean_dataset_setup):
    """
    Verifica que la llamada GET a /dataset/download/<id> incrementa
    el campo download_count en la base de datos.
    """
    dataset_id = clean_dataset_setup

    # 1. VERIFICACIÓN PREVIA
    # Recuperamos el dataset fresco de la BD
    dataset_before = DataSet.query.get(dataset_id)
    assert dataset_before.download_count == 0, "El dataset debería nacer con 0 descargas"

    # 2. EJECUCIÓN (Simulamos la petición HTTP)
    # Nota: Es probable que esto devuelva 500 o error si no existen los archivos físicos .uvl
    # para crear el ZIP. PERO NO IMPORTA.
    # Tu código hace el `db.session.commit()` ANTES de intentar comprimir archivos.
    # Por tanto, aunque falle la descarga del archivo, el contador debe subir.
    try:
        test_client.get(f"/dataset/download/{dataset_id}")
    except Exception:
        # Ignoramos errores de "File Not Found" o ZipFile, solo nos importa SQL
        pass

    # 3. MAGIA DE SQLALCHEMY (IMPORTANTE)
    # "Caducamos" la sesión actual. Esto obliga a SQLAlchemy a olvidar los datos
    # que tiene en memoria RAM y volver a leerlos del disco (Base de Datos Real)
    # la próxima vez que le pidamos algo. Sin esto, el test fallaría falsamente.
    db.session.expire_all()

    # 4. VERIFICACIÓN FINAL
    dataset_after = DataSet.query.get(dataset_id)

    print(f"Descargas antes: 0 | Descargas después: {dataset_after.download_count}")

    assert (
        dataset_after.download_count == 1
    ), f"Fallo crítico: El contador es {dataset_after.download_count}, debería ser 1."
