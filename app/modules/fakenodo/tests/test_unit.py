from unittest.mock import MagicMock, patch

import pytest

from app.modules.fakenodo.services import FakenodoService


@pytest.fixture
def fakenodo_service(tmp_path):
    """
    Crea una instancia aislada del servicio usando un JSON temporal.
    """
    with patch("app.modules.fakenodo.services.DB_FILE", tmp_path / "fakenodo.json"):
        service = FakenodoService()
        service._save_db = MagicMock()
        return service


def test_create_deposition_basic(fakenodo_service):
    """
    Verifica creación básica de un depósito.
    """
    record = fakenodo_service.create_deposition(metadata={"title": "Test Deposit"})

    assert record["id"] >= 1000
    assert record["title"] == "Test Deposit"
    assert record["submitted"] is False
    assert record["state"] == "unsubmitted"
    assert record["files"] == []
    fakenodo_service._save_db.assert_called_once()


def test_get_deposition_existing(fakenodo_service):
    dep = fakenodo_service.create_deposition()
    fetched = fakenodo_service.get_deposition(dep["id"])

    assert fetched is dep


def test_get_deposition_not_found(fakenodo_service):
    assert fakenodo_service.get_deposition(99999) is None


def test_list_depositions_order(fakenodo_service):
    d1 = fakenodo_service.create_deposition()
    d2 = fakenodo_service.create_deposition()

    deps = fakenodo_service.list_depositions()

    assert deps[0]["id"] == d2["id"]
    assert deps[1]["id"] == d1["id"]


def test_delete_deposition_success(fakenodo_service):
    dep = fakenodo_service.create_deposition()

    result = fakenodo_service.delete_deposition(dep["id"])

    assert result is True
    assert fakenodo_service.get_deposition(dep["id"]) is None
    fakenodo_service._save_db.assert_called()


def test_delete_deposition_not_found(fakenodo_service):
    assert fakenodo_service.delete_deposition(12345) is False


def test_update_metadata_updates_title_and_metadata(fakenodo_service):
    dep = fakenodo_service.create_deposition(metadata={"title": "Old"})
    updated = fakenodo_service.update_metadata(dep["id"], {"title": "New", "tags": "a,b"})

    assert updated["title"] == "New"
    assert updated["metadata"]["tags"] == "a,b"
    fakenodo_service._save_db.assert_called()


def test_update_metadata_not_found(fakenodo_service):
    assert fakenodo_service.update_metadata(123, {"title": "X"}) is None


def test_upload_file_new_file(fakenodo_service):
    dep = fakenodo_service.create_deposition()
    file_info = fakenodo_service.upload_file(dep["id"], "test.txt", b"hello")

    assert file_info["filename"] == "test.txt"
    assert file_info["filesize"] == 5
    assert dep["dirty_files"] is True
    assert len(dep["files"]) == 1


def test_upload_file_overwrite_existing(fakenodo_service):
    dep = fakenodo_service.create_deposition()
    fakenodo_service.upload_file(dep["id"], "test.txt", b"hello")
    fakenodo_service.upload_file(dep["id"], "test.txt", b"hello world")

    assert len(dep["files"]) == 1
    assert dep["files"][0]["filesize"] == 11


def test_upload_file_deposition_not_found(fakenodo_service):
    assert fakenodo_service.upload_file(999, "x", b"y") is None


def test_publish_first_time_generates_doi(fakenodo_service):
    dep = fakenodo_service.create_deposition()
    result = fakenodo_service.publish_deposition(dep["id"])

    assert result["submitted"] is True
    assert result["state"] == "done"
    assert result["version_count"] == 1
    assert result["doi"].endswith(str(dep["id"]))


def test_publish_new_version_when_dirty(fakenodo_service):
    dep = fakenodo_service.create_deposition()
    fakenodo_service.publish_deposition(dep["id"])

    fakenodo_service.upload_file(dep["id"], "file.txt", b"x")
    result = fakenodo_service.publish_deposition(dep["id"])

    assert result["version_count"] == 2
    assert result["doi"].endswith(".2")


def test_publish_deposition_not_found(fakenodo_service):
    assert fakenodo_service.publish_deposition(9999) is None


def test_get_doi(fakenodo_service):
    dep = fakenodo_service.create_deposition()
    fakenodo_service.publish_deposition(dep["id"])

    doi = fakenodo_service.get_doi(dep["id"])
    assert doi.startswith("10.5072/zenodo.")


def test_list_versions_empty(fakenodo_service):
    dep = fakenodo_service.create_deposition()
    versions = fakenodo_service.list_versions(dep["id"])

    assert versions == []


def test_list_versions_multiple(fakenodo_service):
    dep = fakenodo_service.create_deposition()
    fakenodo_service.publish_deposition(dep["id"])
    fakenodo_service.upload_file(dep["id"], "f.txt", b"x")
    fakenodo_service.publish_deposition(dep["id"])

    versions = fakenodo_service.list_versions(dep["id"])

    assert len(versions) == 2
    assert versions[-1]["is_latest"] is True


def test_full_connection():
    """
    Verifica el endpoint de health-check lógico sin depender de Flask.
    """
    service = FakenodoService()

    with patch("app.modules.fakenodo.services.jsonify") as mock_jsonify:
        mock_jsonify.return_value = {"success": True}

        resp = service.test_full_connection()

        mock_jsonify.assert_called_once_with({"success": True, "message": "Fakenodo persistent service is running."})
        assert resp == {"success": True}
