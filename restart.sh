#!/bin/bash

# ==============================================================================
# Script de Reseteo para Liberaty Project v2
# ==============================================================================
# Este script detiene el servicio, borra todas las bases de datos (historial
# y memoria vectorial) y reinicia el sistema para forzar un comienzo desde cero.
#
# Debe ejecutarse con privilegios de superusuario (sudo).
# ==============================================================================

# --- Verificación de Privilegios ---
if [ "$EUID" -ne 0 ]; then 
  echo "Por favor, ejecuta este script como root o con sudo."
  exit 1
fi

# --- Variables de Configuración ---
PROJECT_DIR="/opt/liberatyProject"

print_header() {
  echo ""
  echo "============================================================"
  echo "  $1"
  echo "============================================================"
  echo ""
}

print_header "Iniciando reseteo completo de Liberaty v2"

# --- Paso 1: Detener el servicio ---
echo "Deteniendo el servicio de Liberaty..."
systemctl stop liberaty.service
if [ $? -ne 0 ]; then
    echo "ADVERTENCIA: No se pudo detener el servicio. Puede que no estuviera en ejecución."
fi
sleep 2

# --- Paso 2: Borrar las bases de datos ---
echo "Borrando la base de datos de historial (SQLite)..."
rm -f "${PROJECT_DIR}/liberaty_v2.db"
if [ $? -eq 0 ]; then
    echo "Base de datos de historial eliminada."
else
    echo "ERROR: No se pudo eliminar la base de datos de historial."
fi

echo "Borrando la base de datos de memoria a largo plazo (ChromaDB)..."
rm -rf "${PROJECT_DIR}/memory_db"
if [ $? -eq 0 ]; then
    echo "Memoria a largo plazo eliminada."
else
    echo "ERROR: No se pudo eliminar la memoria a largo plazo."
fi

# --- Paso 3: Reiniciar el servicio ---
echo "Reiniciando el servicio de Liberaty..."
systemctl start liberaty.service
if [ $? -ne 0 ]; then
    echo "ERROR: No se pudo iniciar el servicio. Revisa el estado con 'sudo systemctl status liberaty'"
    exit 1
fi
sleep 2

# --- Paso 4: Verificación ---
print_header "Reseteo completado"
echo "El servicio ha sido reiniciado y el agente comenzará desde cero."
echo "Puedes ver el estado y los logs con los siguientes comandos:"
echo "  - Estado: sudo systemctl status liberaty"
echo "  - Logs:   sudo journalctl -u liberaty -f"
echo ""

