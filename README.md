# Fórmula Hub

![Python Version](https://img.shields.io/badge/python-3.9%2B-blue?style=for-the-badge&logo=python)
![Framework](https://img.shields.io/badge/flask-2.0%2B-green?style=for-the-badge&logo=flask)
![Database](https://img.shields.io/badge/MariaDB-10.5%2B-orange?style=for-the-badge&logo=mariadb)
![License](https://img.shields.io/badge/license-MIT-lightgrey?style=for-the-badge)
![CI/CD](https://img.shields.io/badge/CI%2FCD-Active-success?style=for-the-badge&logo=github-actions)

<p align="center">
  </p>

## 📋 Tabla de Contenidos

- [✨ Características](#-características)
- [🔧 Requisitos Previos](#-requisitos-previos)
- [🚀 Instalación y Configuración](#-instalación-y-configuración)
- [📁 Estructura del Proyecto](#-estructura-del-proyecto)
- [📚 Documentación Adicional](#-documentación-adicional)
- [🤝 Contribuir](#-contribuir)
- [👥 Equipo y Licencia](#-equipo)

---

## ✨ Características

- 📊 **Gestión de Datasets**: Almacenamiento estructurado datasets (UVL, CSV).
- 👥 **Gestión de Usuarios**: Sistema completo de autenticación y perfiles de usuario.
- 🌐 **Integración Zenodo**: Publicación directa de datasets con generación de DOI.
- 🧪 **Testing Completo**: Suite robusta de tests unitarios, de integración y E2E.
- 🎨 **UI Moderna**: Interfaz responsive y accesible.

---

## 🔧 Requisitos Previos

Asegúrate de tener instalado lo siguiente antes de empezar:

* **Lenguajes:** Python 3.9+
* **Base de Datos:** MariaDB (10.5+).
* **Control de Versiones:** Git.

### Opcional
* **Docker:** Para despliegue contenerizado.

---

## 🚀 Instalación y Configuración

Sigue estos pasos para levantar el entorno de desarrollo local.

### 1. Clonar el Repositorio

```bash
git clone [https://github.com/Formula-hub2/formula-hub.git](https://github.com/Formula-hub2/formula-hub.git)
cd formula-hub
````

### 2\. Configurar Entorno Virtual

```bash
# Crear entorno
python -m venv venv

# Activar (Linux/Mac)
source venv/bin/activate

# Activar (Windows)
venv\Scripts\activate
```

### 3\. Instalar Dependencias

```bash
pip install -r requirements.txt
pip install -e .
```

### 4\. Configurar Variables de Entorno

Crea un archivo `.env` en la raíz y configura:

```ini
# Configuración de la Aplicación
FLASK_APP_NAME="UVLHUB.IO(dev)"
FLASK_ENV=development
DOMAIN=localhost:5000

#Configuración de la base de datos
MARIADB_HOSTNAME=localhost
MARIADB_PORT=3306
MARIADB_DATABASE=uvlhubdb
MARIADB_TEST_DATABASE=uvlhubdb_test
MARIADB_USER=uvlhubdb_user
MARIADB_PASSWORD=tu-password
MARIADB_ROOT_PASSWORD=tu-password

# Directorio de trabajo
WORKING_DIR=

```

### 5\. Inicializar Base de Datos

Primero, crea la base de datos en tu servidor SQL:
SQL

```bash
CREATE DATABASE uvlhubdb CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
```

Luego, utiliza nuestro CLI Rosemary para configurar las tablas y poblar datos:

```bash
flask db upgrade
rosemary db:seed
```

### 6\. Ejecutar la Aplicación

```bash
flask run
```

-----

## 🎮 Comandos Principales (Rosemary CLI)

Utilizamos `rosemary`, nuestro CLI personalizado, para gestionar el proyecto.

### 🗄️ Base de Datos

| Comando | Descripción |
| :--- | :--- |
| `rosemary db:setup` | Instalación completa (migraciones + seeds). |
| `rosemary db:status` | Verifica la conexión y estado de migraciones. |
| `rosemary db:migrate "msg"` | Crea una nueva migración tras cambios en modelos. |
| `rosemary db:upgrade` | Aplica cambios pendientes a la BD (Backup auto). |
| `rosemary db:seed` | Puebla la BD con datos falsos. |
| `rosemary db:reset -y` | **¡Peligro\!** Borra y recrea la base de datos. |
| `rosemary db:console` | Abre una consola SQL conectada a la BD. |

### 🧪 Testing & Calidad

```bash
# Tests por tipo
rosemary test       # Unitarios
rosemary selenium   # Interfaz
rosemary locust     # Carga

# Reporte de cobertura
rosemary coverage
```

### 🛠️ Generadores y Utilidades

```bash
# Crear un nuevo módulo (scaffolding completo)
rosemary make:module nombre_modulo

# Listar rutas disponibles
rosemary route:list

# Limpiar caché y logs
rosemary clear:cache
```

-----

## 📁 Estructura del Proyecto

```text
formula-hub/
├── app/                  # Núcleo de la aplicación Flask
│   ├── modules/          # Arquitectura modular
│   │   ├── auth/         # Login, Registro, Perfil
│   │   ├── dataset/      # Lógica principal de datasets
│   │   │   ├── models.py
│   │   │   ├── routes.py
│   │   │   ├── services.py
│   │   │   └── ...
│   │   └── ...
│   ├── static/           # Assets (CSS, JS, Img)
│   └── templates/        # Jinja2 Templates globales
├── core/                 # Configuración, Managers y Seeders base
├── backups/              # Backups automáticos de BD
├── migrations/           # Historial de cambios de BD (Alembic)
├── rosemary/             # Código fuente del CLI
├── uploads/              # Archivos subidos por usuarios
├── docs/                 # Documentación técnica
└── README.md             # Este archivo
```

-----

## 📚 Documentación Adicional

Documentación técnica detallada para desarrolladores:

  - 🎣 **[Guía de Pre-commit Hooks](docs/pre-commit-hooks-guide.md)**
  - 🧪 **[Guía de ciclo CI/CD](docs/cicd-guide.md)**

-----

## 🤝 Contribuir

¡Las contribuciones son bienvenidas\! Por favor, sigue este flujo de trabajo:

1.  Crea una rama para tu feature (`git checkout -b feature/mi-feature`).
2.  **Importante:** Asegúrate de cumplir los estándares (los hooks te avisarán):
      * **Python:** PEP 8 (flake8).
      * **Formato:** Black (120 chars).
      * **Commits:** [Conventional Commits](https://www.conventionalcommits.org/) (ej: `feat: add new filter`).
3.  Ejecuta los tests (`pytest`) y el linter (`rosemary linter:fix`).
4.  Haz **Push**.

-----

## 👥 Equipo

  * [GitHub Profile](https://github.com/Formula-hub2/formula-hub)
  * [Issues](https://github.com/Formula-hub2/formula-hub/issues)
  * [KANBAN](https://github.com/orgs/Formula-hub2/projects/1)

## 📝 Documentación oficial

You can consult the official documentation of the project at [docs.uvlhub.io](https://docs.uvlhub.io/).
