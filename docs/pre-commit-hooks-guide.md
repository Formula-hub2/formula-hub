# 🎣 Guía de Pre-commit Hooks

Esta guía explica el sistema de automatización implementado en **Formula Hub** para asegurar la calidad, seguridad y consistencia del código antes de que llegue al repositorio.

## ❓ ¿Qué son los Pre-commit Hooks?

Los pre-commit hooks son scripts que se ejecutan automáticamente en tu máquina local cada vez que intentas hacer un commit (`git commit`). Actúan como un "filtro de calidad" inmediato.

**Beneficios:**
- 🛡️ **Seguridad:** Detecta vulnerabilidades antes de subir el código.
- 🎨 **Estilo:** Formatea el código automáticamente (Python).
- 🧹 **Limpieza:** Ordena importaciones y elimina espacios innecesarios.
- 📝 **Estandarización:** Obliga a usar mensajes de commit semánticos.

---

## 🚀 Instalación

Si acabas de clonar el repositorio, necesitas activar los hooks en tu entorno local.

1. **Asegúrate de estar en tu entorno virtual:**

```bash
source venv/bin/activate
```

2.  **Instala la librería `pre-commit`:**
*(Ya debería estar instalada si ejecutaste `pip install -r requirements.txt`)*

```bash
pip install pre-commit
```

3.  **Instala los hooks en Git:**
Este es el paso más importante. Debes ejecutar ambos comandos:

```bash
# 1. Instala los hooks de código (Black, Flake8, Bandit...)
pre-commit install

# 2. Instala el hook de mensajes de commit (Conventional Commits)
pre-commit install --hook-type commit-msg
```

✅ **¡Listo\!** Ahora, cada vez que hagas un commit, los análisis se ejecutarán solos.

-----

## 🛠️ Herramientas Incluidas

Tu configuración actual (`.pre-commit-config.yaml`) incluye las siguientes herramientas:

### 1\. Limpieza Básica

  * **Trailing Whitespace:** Elimina espacios en blanco al final de las líneas.
  * **End of File Fixer:** Asegura que los archivos terminen con una línea vacía.
  * **Check YAML:** Verifica que tus archivos `.yml` / `.yaml` no tengan errores de sintaxis.
  * **Large Files:** Evita subir archivos gigantes por error.

### 2\. Formato de Código (Python)

  * **Black:** El formateador de código intransigente. Reescribe tu código para que cumpla PEP 8.
      * *Versión:* Python 3.12
  * **Isort:** Ordena tus `import` alfabéticamente y por tipo (librería estándar, terceros, local).
      * *Perfil:* Compatible con Black.

### 3\. Calidad y Linter

  * **Flake8:** Analiza el código buscando errores lógicos y de estilo.
      * *Reglas:* Longitud máxima 88 caracteres.
      * *Ignora:* E203, E501 (línea larga), W503, E226 (espacios en operadores).

### 4\. Seguridad (Bandit) 🛡️

Analiza tu código en busca de vulnerabilidades de seguridad comunes en Python.

  * **Configuración:** Reporta confianza media/alta y severidad media/alta (`-iii`, `-ll`).
  * **Exclusiones:** No analiza tests, seeders ni comandos internos (`rosemary/commands/`), ya que suelen dar falsos positivos.

### 5\. Mensajes de Commit

  * **Conventional Pre-commit:** Valida que tu mensaje de commit siga el estándar **Conventional Commits**.

-----

## 📝 Conventional Commits

Para mantener un historial limpio, todos los mensajes de commit deben seguir esta estructura:

```text
tipo: descripción breve en minúsculas
```

### Tipos Permitidos

| Tipo | Uso | Ejemplo |
| :--- | :--- | :--- |
| **`feat`** | Nueva funcionalidad | `feat: add new dataset filter` |
| **`fix`** | Corrección de error | `fix: resolve login crash` |
| **`docs`** | Documentación | `docs: update readme instructions` |
| **`style`** | Formato (espacios, comas) | `style: apply black formatting` |
| **`refactor`** | Cambios de código sin features nuevas | `refactor: simplify auth service` |
| **`test`** | Añadir o corregir tests | `test: add unit test for user model` |
| **`chore`** | Tareas de mantenimiento | `chore: update dependencies` |
| **`ci`** | Cambios en CI/CD | `ci: update github actions workflow` |
| **`build`** | Cambios en sistema de build | `build: update dockerfile` |
| **`perf`** | Mejora de rendimiento | `perf: optimize database query` |
| **`revert`** | Revertir un commit anterior | `revert: undo commit ab12cd` |

-----

## 🔄 Flujo de Trabajo Diario

### 1\. Hacer el Commit

```bash
git add .
git commit -m "feat: add user profile page"
git push
```

### 2\. Si todo está bien (✅ Passed)

Verás una lista verde y el commit se creará.

### 3\. Si hay errores de formato (❌ Failed)

Si Black o Isort modifican archivos, el commit fallará y verás:

> `Files were modified by this hook`

**Solución:** Simplemente vuelve a añadir los archivos (que ahora están corregidos automáticamente) y repite el commit.

```bash
git add .
git commit -m "feat: add user profile page"
```

### 4\. Si hay errores de Linter/Seguridad

Si Flake8 o Bandit fallan, te dirán el archivo y la línea. **Debes corregir el error manualmente** y volver a intentar el commit.

-----

## ⚡ Comandos Útiles

### Ejecutar manualmente en todos los archivos

Útil cuando acabas de configurar el repo o quieres hacer una limpieza general.

```bash
pre-commit run --all-files
```

### Actualizar las herramientas

Para actualizar Black, Flake8, etc. a sus últimas versiones compatibles.

```bash
pre-commit autoupdate
```

### Saltar los hooks (¡Emergencia\!)

Solo úsalo si es estrictamente necesario y sabes lo que haces.

```bash
git commit -m "fix: quick hotfix" --no-verify
```
