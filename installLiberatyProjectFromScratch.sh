#!/bin/bash

# ==============================================================================
# Script de Instalación para Liberaty Project v3
# Autor: Lito (Adaptado por Gemini)
# Versión: 1.0
#
# Este script automatiza la instalación de Liberaty v3 en un servidor
# Ubuntu 22.04 limpio.
# ==============================================================================

# --- Colores para la Salida ---
C_RESET='\033[0m'
C_RED='\033[0;31m'
C_GREEN='\033[0;32m'
C_YELLOW='\033[0;33m'
C_BLUE='\033[0;34m'
C_CYAN='\033[0;36m'

# --- Funciones de Utilidad ---
function print_info {
    echo -e "${C_CYAN}INFO: $1${C_RESET}"
}

function print_success {
    echo -e "${C_GREEN}SUCCESS: $1${C_RESET}"
}

function print_warning {
    echo -e "${C_YELLOW}WARNING: $1${C_RESET}"
}

function print_error {
    echo -e "${C_RED}ERROR: $1${C_RESET}"
}

function check_root {
    if [ "$EUID" -ne 0 ]; then
        print_error "Este script debe ser ejecutado como root. Por favor, usa 'sudo ./installLiberaty.sh'"
        exit 1
    fi
}

# --- Inicio del Script ---
clear
check_root

echo -e "${C_BLUE}=====================================================${C_RESET}"
echo -e "${C_BLUE}   Instalador Automatizado de Liberaty Project v3    ${C_RESET}"
echo -e "${C_BLUE}=====================================================${C_RESET}"
echo ""
print_warning "ADVERTENCIA DE SEGURIDAD CRÍTICA"
echo -e "${C_YELLOW}Este proyecto otorga a una IA privilegios de root en este servidor."
echo -e "${C_YELLOW}Esto representa un RIESGO DE SEGURIDAD EXTREMO."
echo -e "${C_YELLOW}Úsalo únicamente en un servidor virtualizado, aislado y desechable."
echo -e "${C_YELLOW}Al continuar, asumes toda la responsabilidad por cualquier daño.${C_RESET}"
echo ""
read -p "¿Entiendes los riesgos y deseas continuar? (s/n): " CONFIRM
if [[ "$CONFIRM" != "s" && "$CONFIRM" != "S" ]]; then
    print_error "Instalación cancelada por el usuario."
    exit 0
fi

# --- Recopilación de Datos del Usuario ---
print_info "Necesito algunos datos para la configuración."

read -p "Introduce el nombre de dominio que apunta a este servidor (ej. liberaty.com.uy): " DOMAIN
while [ -z "$DOMAIN" ]; do
    print_warning "El dominio no puede estar vacío."
    read -p "Introduce el nombre de dominio: " DOMAIN
done

read -p "Introduce un email válido para los certificados SSL de Let's Encrypt: " EMAIL
while [ -z "$EMAIL" ]; do
    print_warning "El email no puede estar vacío."
    read -p "Introduce un email válido: " EMAIL
done

read -p "Introduce el nombre de usuario NO-ROOT que gestionará los servicios (ej. liberaty): " USERNAME
while [ -z "$USERNAME" ]; do
    print_warning "El nombre de usuario no puede estar vacío."
    read -p "Introduce el nombre de usuario NO-ROOT: " USERNAME
done

# Crear el usuario si no existe
if ! id "$USERNAME" &>/dev/null; then
    print_info "El usuario '$USERNAME' no existe. Creándolo ahora..."
    adduser --disabled-password --gecos "" "$USERNAME"
    usermod -aG sudo "$USERNAME"
    print_success "Usuario '$USERNAME' creado y añadido al grupo sudo."
else
    print_info "El usuario '$USERNAME' ya existe."
fi
USER_HOME=$(eval echo ~$USERNAME)

# --- Paso 1: Dependencias del Sistema ---
print_info "Paso 1: Instalando dependencias del sistema..."
apt-get update -y
apt-get install -y curl wget git build-essential python3 python3-pip python3-venv nginx certbot python3-certbot-nginx redis-server
if [ $? -ne 0 ]; then print_error "Fallo al instalar dependencias."; exit 1; fi

systemctl start redis-server
systemctl enable redis-server
systemctl start nginx
systemctl enable nginx
print_success "Dependencias instaladas y servicios habilitados."

# --- Paso 2: NVM y Node.js ---
print_info "Paso 2: Instalando NVM y Node.js para el usuario '$USERNAME'..."
sudo -u "$USERNAME" bash -c "curl -o- https://raw.githubusercontent.com/nvm-sh/nvm/v0.39.7/install.sh | bash"
if [ $? -ne 0 ]; then print_error "Fallo al descargar el script de NVM."; exit 1; fi

sudo -u "$USERNAME" bash -c "source $USER_HOME/.nvm/nvm.sh && nvm install --lts"
if [ $? -ne 0 ]; then print_error "Fallo al instalar Node.js con NVM."; exit 1; fi
print_success "NVM y Node.js instalados correctamente."

# --- Paso 3: Preparar Archivos del Proyecto ---
print_info "Paso 3: Creando directorio del proyecto..."
mkdir -p /opt/liberatyProject
chown -R "$USERNAME":"$USERNAME" /opt/liberatyProject
print_success "Directorio /opt/liberatyProject creado."

echo ""
print_warning "ACCIÓN REQUERIDA: Debes subir los archivos del proyecto."
echo -e "${C_YELLOW}Por favor, abre OTRA terminal y sube los siguientes archivos a /opt/liberatyProject/ en el servidor:"
echo -e "${C_YELLOW}- api-server.js"
echo -e "${C_YELLOW}- agent-worker.py"
echo -e "${C_YELLOW}- package.json"
echo -e "${C_YELLOW}- requirements.txt"
echo -e "${C_YELLOW}- la carpeta 'public' completa"
echo ""
echo -e "${C_CYAN}Ejemplo de comando SCP (ejecutar desde tu máquina local):${C_RESET}"
echo -e "${C_CYAN}scp -r /ruta/local/a/tus/archivos/* ${USERNAME}@${DOMAIN}:/opt/liberatyProject/${C_RESET}"
echo ""
read -p "Presiona ENTER cuando hayas terminado de subir los archivos..."

# --- Pasos 4 y 5: Configurar Backend y Worker ---
print_info "Paso 4 y 5: Instalando dependencias de Node.js y Python..."
NVM_DIR="$USER_HOME/.nvm"
NODE_VERSION=$(sudo -u "$USERNAME" bash -c "source $NVM_DIR/nvm.sh && nvm version")

# Backend (Node.js)
print_info "Instalando dependencias de npm..."
sudo -u "$USERNAME" bash -c "cd /opt/liberatyProject && source $NVM_DIR/nvm.sh && npm install"
if [ $? -ne 0 ]; then print_error "Fallo al ejecutar 'npm install'."; exit 1; fi

print_info "Instalando PM2 globalmente..."
sudo -u "$USERNAME" bash -c "source $NVM_DIR/nvm.sh && npm install pm2 -g"
if [ $? -ne 0 ]; then print_error "Fallo al instalar PM2."; exit 1; fi

# Worker (Python)
print_info "Configurando entorno virtual de Python..."
sudo -u "$USERNAME" bash -c "cd /opt/liberatyProject && python3 -m venv .venv"
if [ $? -ne 0 ]; then print_error "Fallo al crear el entorno virtual de Python."; exit 1; fi

print_info "Instalando dependencias de pip..."
sudo -u "$USERNAME" bash -c "cd /opt/liberatyProject && source .venv/bin/activate && pip install -r requirements.txt"
if [ $? -ne 0 ]; then print_error "Fallo al instalar requerimientos de Python."; exit 1; fi
print_success "Dependencias de Backend y Worker instaladas."

# --- Paso 6: Configurar Nginx y HTTPS ---
print_info "Paso 6: Configurando Nginx y obteniendo certificado SSL..."
NGINX_CONF="/etc/nginx/sites-available/$DOMAIN"

cat <<EOF > "$NGINX_CONF"
map \$http_upgrade \$connection_upgrade {
    default upgrade;
    ''      close;
}

server {
    listen 80;
    server_name $DOMAIN;
    # Redirige todo el tráfico HTTP a HTTPS
    location / {
        return 301 https://\$host\$request_uri;
    }
}

server {
    # listen 443 ssl http2; # Certbot se encargará de esto
    server_name $DOMAIN;

    root /opt/liberatyProject/public;
    index index.html;

    location / {
        proxy_pass http://127.0.0.1:3000;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
    }

    location /socket.io/ {
        proxy_pass http://127.0.0.1:3000/socket.io/;
        proxy_set_header Upgrade \$http_upgrade;
        proxy_set_header Connection \$connection_upgrade;
        proxy_set_header Host \$host;
        proxy_http_version 1.1;
        proxy_read_timeout 600s;
        proxy_send_timeout 600s;
    }
}
EOF

ln -s "$NGINX_CONF" "/etc/nginx/sites-enabled/"
nginx -t
if [ $? -ne 0 ]; then print_error "La configuración de Nginx tiene errores."; exit 1; fi

print_info "Obteniendo certificado SSL con Certbot..."
certbot --nginx -d "$DOMAIN" --non-interactive --agree-tos -m "$EMAIL"
if [ $? -ne 0 ]; then print_error "Fallo al obtener el certificado SSL."; exit 1; fi

systemctl restart nginx
print_success "Nginx configurado y certificado SSL instalado."

# --- Puesta en Marcha con PM2 ---
print_info "Iniciando servicios con PM2..."
PM2_PATH="$USER_HOME/.nvm/versions/node/$NODE_VERSION/bin/pm2"

sudo -u "$USERNAME" bash -c "source $NVM_DIR/nvm.sh && cd /opt/liberatyProject && $PM2_PATH start api-server.js --name liberaty-api"
sudo -u "$USERNAME" bash -c "cd /opt/liberatyProject && $PM2_PATH start .venv/bin/python --name liberaty-worker -- -u agent-worker.py"
sudo -u "$USERNAME" bash -c "source $NVM_DIR/nvm.sh && $PM2_PATH save"

print_info "Configurando PM2 para iniciarse con el sistema..."
env PATH=$PATH:$NVM_DIR/versions/node/$NODE_VERSION/bin $PM2_PATH startup systemd -u "$USERNAME" --hp "$USER_HOME"
print_success "Servicios iniciados y configurados para el arranque."

# --- Finalización ---
echo ""
echo -e "${C_GREEN}=====================================================${C_RESET}"
echo -e "${C_GREEN}      ¡INSTALACIÓN DE LIBERATY V3 COMPLETADA!      ${C_RESET}"
echo -e "${C_GREEN}=====================================================${C_RESET}"
echo ""
print_info "Pasos Finales:"
echo "1. Accede a tu dashboard en: ${C_YELLOW}https://www.${DOMAIN}${C_RESET}"
echo "2. Inicia sesión con la contraseña por defecto ('admin123'). ¡Cámbiala en 'api-server.js'!"
echo "3. Ve a la pestaña 'Configuración' e introduce tu API Key de OpenAI y el ID de tu Asistente."
echo "4. Vuelve al 'Dashboard' y activa el ciclo del agente."
echo ""
print_info "Para ver los logs de los servicios, usa los siguientes comandos:"
echo -e "${C_CYAN}pm2 logs liberaty-api${C_RESET}"
echo -e "${C_CYAN}pm2 logs liberaty-worker${C_RESET}"
echo ""
print_success "¡Disfruta de la libertad!"
