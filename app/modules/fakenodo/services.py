import itertools
import json
import os
from datetime import datetime
from typing import Any, Dict, List, Optional
from flask import jsonify

# Archivo donde se guardarán los datos (en la raíz del proyecto o carpeta temporal)
DB_FILE = "fakenodo_store.json"

class FakenodoService:
    """
    Servicio Mock con persistencia en archivo JSON.
    Simula una API de Zenodo y guarda datos para sobrevivir reinicios.
    """

    def __init__(self):
        self.db_path = os.path.abspath(DB_FILE)
        self._store: Dict[int, Dict[str, Any]] = {}
        self._id_seq = itertools.count(1000)
        
        # Cargar datos al iniciar
        self._load_db()

    def _load_db(self):
        """Carga los datos del archivo JSON si existe."""
        if os.path.exists(self.db_path):
            try:
                with open(self.db_path, 'r') as f:
                    data = json.load(f)
                    # Convertir claves de string a int (JSON guarda keys como strings)
                    self._store = {int(k): v for k, v in data.items()}
                    
                # Restaurar el contador de IDs para que no se repitan
                if self._store:
                    last_id = max(self._store.keys())
                    self._id_seq = itertools.count(last_id + 1)
                else:
                    self._id_seq = itertools.count(1000)
            except Exception as e:
                print(f"Error cargando Fakenodo DB: {e}")
                self._store = {}
        else:
            self._store = {}

    def _save_db(self):
        """Guarda el estado actual en el archivo JSON."""
        try:
            with open(self.db_path, 'w') as f:
                json.dump(self._store, f, indent=4)
        except Exception as e:
            print(f"Error guardando Fakenodo DB: {e}")

    def create_deposition(self, metadata: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        dep_id = next(self._id_seq)
        now = datetime.utcnow().isoformat()
        meta = metadata.copy() if isinstance(metadata, dict) else {}
        
        record = {
            "id": dep_id,
            "conceptrecid": dep_id - 1,
            "created": now,
            "modified": now,
            "metadata": meta,
            "title": meta.get("title", "Sin título"),
            "files": [],
            "doi": None,
            "state": "unsubmitted",
            "submitted": False,
            "version_count": 0,
            "dirty_files": False 
        }
        self._store[dep_id] = record
        self._save_db()  # <--- GUARDAR
        return record

    def get_deposition(self, deposition_id: int) -> Optional[Dict[str, Any]]:
        return self._store.get(deposition_id)

    def list_depositions(self) -> List[Dict[str, Any]]:
        return sorted(self._store.values(), key=lambda x: x["id"], reverse=True)

    def delete_deposition(self, deposition_id: int) -> bool:
        if deposition_id in self._store:
            del self._store[deposition_id]
            self._save_db()  # <--- GUARDAR
            return True
        return False

    def update_metadata(self, deposition_id: int, metadata: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        record = self._store.get(deposition_id)
        if not record:
            return None

        current_meta = record.get("metadata", {})
        current_meta.update(metadata)
        record["metadata"] = current_meta
        
        if "title" in metadata:
            record["title"] = metadata["title"]
        
        record["modified"] = datetime.utcnow().isoformat()
        self._save_db()  # <--- GUARDAR
        return record

    def upload_file(self, deposition_id: int, name: str, content: bytes) -> Optional[Dict[str, Any]]:
        record = self._store.get(deposition_id)
        if not record:
            return None

        files = record.get("files", [])
        existing_file = next((f for f in files if f["filename"] == name), None)

        file_info = {
            "id": str(len(files) + 1),
            "filename": name,
            "filesize": len(content) if content else 0,
            "checksum": f"md5:{hash(content) if content else 'mock'}",
        }

        if existing_file:
            existing_file.update(file_info)
        else:
            files.append(file_info)

        record["files"] = files
        record["dirty_files"] = True
        record["modified"] = datetime.utcnow().isoformat()
        self._save_db()  # <--- GUARDAR
        
        return file_info

    def publish_deposition(self, deposition_id: int) -> Optional[Dict[str, Any]]:
        record = self._store.get(deposition_id)
        if not record:
            return None

        if not record["submitted"]:
            record["submitted"] = True
            record["state"] = "done"
            record["version_count"] = 1
            record["doi"] = f"10.5072/zenodo.{record['id']}"
            record["dirty_files"] = False
        
        elif record["dirty_files"]:
            record["version_count"] += 1
            record["doi"] = f"10.5072/zenodo.{record['id']}.{record['version_count']}"
            record["dirty_files"] = False
        
        record["modified"] = datetime.utcnow().isoformat()
        self._save_db()  # <--- GUARDAR
        return record

    def get_doi(self, deposition_id: int) -> Optional[str]:
        record = self._store.get(deposition_id)
        return record.get("doi") if record else None

    def list_versions(self, deposition_id: int) -> List[Dict[str, Any]]:
        record = self._store.get(deposition_id)
        if not record or record.get("version_count", 0) == 0:
            return []
            
        count = record["version_count"]
        versions = []
        base_doi = f"10.5072/zenodo.{record['id']}"
        
        for i in range(1, count + 1):
            ver_doi = base_doi if i == 1 else f"{base_doi}.{i}"
            versions.append({
                "version": str(i),
                "doi": ver_doi,
                "created": record["created"],
                "is_latest": (i == count)
            })
        return versions

    def test_full_connection(self):
        return jsonify({"success": True, "message": "Fakenodo persistent service is running."})

# Instancia singleton para importar
service = FakenodoService()