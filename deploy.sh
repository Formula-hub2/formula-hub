#!/bin/bash
set -e

echo "🚀 Iniciando script de entrada..."

# 1. Esperar a la base de datos (si usas el script wait-for-db)
# ./scripts/wait-for-db.sh

flask db downgrade

# 2. Aplicar migraciones (Estructurales)
echo "🔄 Ejecutando migraciones..."
flask db upgrade

# 3. Poblar la base de datos (Semillas)
# OJO: Asegúrate de que tu comando 'db:seed' sea idempotente
# (que no duplique datos si se ejecuta dos veces)
echo "🌱 Ejecutando semillas..."
rosemary db:seed

# 4. Iniciar Gunicorn
echo "🔥 Iniciando servidor..."
exec gunicorn app:app --bind 0.0.0.0:80
