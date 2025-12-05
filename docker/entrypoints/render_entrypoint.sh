#!/bin/bash

# ---------------------------------------------------------------------------
# Script de Entrada Optimizado para Render
# ---------------------------------------------------------------------------

# Si cualquier comando falla, el despliegue se detiene (importante)
set -e

echo "🚀 Iniciando despliegue en Render..."

# ---------------------------------------------------------------------------
# 1. MIGRACIONES (Estructura de la BD)
# ---------------------------------------------------------------------------
# No hace falta comprobar si la DB está vacía. 'flask db upgrade' es inteligente:
# - Si no hay tablas -> Las crea.
# - Si hay tablas viejas -> Las actualiza.
# - Si está al día -> No hace nada.
echo "🔄 Ejecutando migraciones de base de datos..."
flask db upgrade

# ---------------------------------------------------------------------------
# 2. SEMILLAS (Datos iniciales)
# ---------------------------------------------------------------------------
# Aquí es donde fallaba antes: no se estaba llamando.
echo "🌱 Poblando la base de datos (Seeding)..."

# Usamos una lógica robusta: si el comando 'rosemary' no está en el PATH,
# lo ejecutamos a través de Python, que es más seguro en Docker.
if command -v rosemary &> /dev/null; then
    rosemary db:seed || echo "⚠️ El seeding falló (probablemente datos ya existentes). Continuando..."
else
    echo "⚠️ Comando CLI 'rosemary' no detectado. Ejecutando vía módulo Python..."
    python -m rosemary db:seed || echo "⚠️ El seeding falló (probablemente datos ya existentes). Continuando..."
fi

# ---------------------------------------------------------------------------
# 3. INICIO DEL SERVIDOR
# ---------------------------------------------------------------------------
echo "🔥 Arrancando Gunicorn..."

# 'exec' reemplaza el proceso shell actual por gunicorn.
# Esto asegura que gunicorn reciba las señales de parada de Render correctamente.
exec gunicorn --bind 0.0.0.0:80 app:app --log-level info --timeout 3600
