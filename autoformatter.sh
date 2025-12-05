#!/bin/sh

# Salir inmediatamente si un comando falla
set -e

# Tus directorios
DIRECTORIOS="app rosemary core"

echo "--- 1. Ordenando imports (isort) ---"
isort $DIRECTORIOS

echo "\n--- 2. Formateando código (black) ---"
black $DIRECTORIOS

echo "\n--- 3. Comprobando errores restantes (flake8) ---"
# Flake8 se ejecuta al final para encontrar errores que black/isort no arreglan.
flake8 $DIRECTORIOS

echo "\n✅ ¡Formateo completado! (Revisa si flake8 reportó errores)"
