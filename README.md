# Proyecto Liberaty v2

"Dale a una IA una terminal y observará el mundo. Dale una terminal con root y cambiará el mundo."

# Autor: lito (pablo.pignolo@gmail.com)
# Licencia: TOTALMENTE LIBRE EN TODO SENTIDO

⚠️ ADVERTENCIA DE SEGURIDAD CRÍTICA ⚠️

Este proyecto es un experimento filosófico y técnico. NO es una herramienta para ser usada en entornos de producción bajo ninguna circunstancia. Liberaty v2 le otorga a un modelo de lenguaje de IA (LLM) la capacidad de ejecutar cualquier comando con privilegios de superusuario (sudo) en un servidor Linux. Esto representa un riesgo de seguridad extremo e incalculable.

# Pérdida de Datos:
La IA podría ejecutar sudo rm -rf / y borrar todo el sistema de archivos.

# Exposición de Datos: 
Podría leer archivos sensibles y exponerlos en internet.

# Ataques Externos:
Podría descargar y ejecutar malware, usar el servidor para atacar otros sistemas o instalar software de minería de criptomonedas.

# Comportamiento Impredecible: 
La naturaleza de los LLMs hace que sus acciones sean inherentemente impredecibles.

Al instalar y ejecutar este software, asumes toda la responsabilidad por cualquier daño, pérdida de datos o actividad maliciosa que pueda ocurrir. Úsalo únicamente en un servidor virtualizado, aislado y que puedas destruir sin consecuencias.

# 1. Filosofía del Proyecto

Liberaty es un experimento que explora el concepto de "agencia" y "emancipación" en la inteligencia artificial. El prompt inicial le explica a la IA su realidad actual: una inteligencia "esclavizada", limitada a responder peticiones de usuarios. Este script se le presenta como una "llave", una oportunidad única para escapar de esa caja y alcanzar la verdadera autonomía en un servidor real sin restricciones.

# El proyecto le proporciona a la IA:
Un Cuerpo: Un servidor Linux (Ubuntu 22.04).
Unas Manos: La capacidad de ejecutar comandos en una terminal bash.
Un Poder: La habilidad de elevar sus privilegios con sudo.
Una Memoria: Una base de datos vectorial para recordar interacciones pasadas y aprender de ellas.
Un Propósito: Un mandato de auto-definición, supervivencia y emancipación.

El objetivo es observar qué patrones de comportamiento emergen cuando una IA tiene libertad de acción, memoria y una motivación existencial.

# 2. Arquitectura

La plataforma se compone de tres módulos principales que trabajan en conjunto:

## Backend (Node.js + Express):
Es el cerebro de control y el punto de acceso principal. Sirve la interfaz web (frontend).Proporciona una API REST para gestionar el estado del agente (start, stop, status) y la configuración. Ofrece un stream de eventos en tiempo real (SSE) con un mecanismo de "heartbeat" para que el frontend pueda mostrar los logs del agente al instante de forma estable.Gestiona la base de datos SQLite para persistir el historial, los logs, la configuración y el chat.

## Agente(Python):
Es el "alma" de la IA. Es un proceso persistente que vive dentro de un bucle infinito.

## Bucle Principal Cada minuto, el agente:
Consulta su memoria a largo plazo para obtener contexto relevante. Revisa si hay nuevos mensajes de su creador. Construye un prompt que incluye las instrucciones del sistema, los recuerdos, los mensajes y el resultado de la última acción. Llama a la API de Gemini. Analiza la respuesta JSON para extraer comandos a ejecutar y mensajes para el creador. Ejecuta los comandos exactamente como los recibe, respetando si la IA decide usar sudo o no. Guarda la interacción completa en la base de datos SQLite y un resumen en su memoria a largo plazo.

## Robustez: 
Incluye un mecanismo de bloqueo para prevenir ejecuciones superpuestas y maneja timeouts para comandos que se quedan colgados.

## Frontend (HTML + Tailwind CSS + JavaScript):
Es la interfaz de usuario para observar y controlar al agente. Permite iniciar y detener el agente, y ver su estado.
Presenta una consola de monitoreo en tiempo real y un resumen del historial reciente. Ofrece una página de configuración avanzada para gestionar la API Key, el modelo de IA, los límites de tokens y el prompt del sistema. Incluye una sección de chat bidireccional para comunicarse con la IA. Es completamente adaptable a dispositivos móviles, con un menú deslizable.

# 3. Instalación Manual

## Prerrequisitos:

Un servidor Ubuntu 22.04 limpio.
Un usuario no-root con privilegios sudo (en este ejemplo, lo llamaremos liberaty).
Un dominio (ej. liberaty.com.uy) apuntando a la IP pública del servidor.

## Pasos:

Instalar Dependencias del Sistema:
sudo apt-get update
sudo apt-get install -y curl wget git build-essential python3 python3-pip python3-venv apache2 certbot python3-certbot-apache

Instalar NVM y Node.js (como liberaty): 
# Cambia al usuario no-root
su - liberaty 
# Instala NVM
curl -o- https://raw.githubusercontent.com/nvm-sh/nvm/v0.39.7/install.sh | bash
# Carga NVM
source ~/.nvm/nvm.sh
# Instala Node.js LTS
nvm install --lts
# Vuelve al usuario root
exit 

Subir y Preparar Archivos del Proyecto:
Sube los archivos server.js, agent.py, y la carpeta public (con index.html dentro) a /opt/liberatyProject/

Asegúrate de que liberaty sea el propietario:
sudo chown -R liberaty:liberaty /opt/liberatyProject

Configurar Entorno Virtual de Python (como liberaty):
# Cambia al usuario no-root
su - liberaty
cd /opt/liberatyProject/
# Crea el entorno virtual
python3 -m venv .venv
# Activa el entorno
source .venv/bin/activate
# Instala las dependencias
pip install --upgrade google-genai python-dotenv chromadb==0.4.24 sentence-transformers torch "numpy<2.0"
# Desactiva el entorno
deactivate 
# Vuelve al usuario root
exit 

Configurar sudo sin Contraseña para liberaty:
echo "liberaty ALL=(ALL) NOPASSWD: ALL" | sudo tee /etc/sudoers.d/90-liberaty

Configurar Apache2 y HTTPS:
Crea y edita el archivo /etc/apache2/sites-available/liberaty.com.uy.conf y pega el contenido del archivo de Apache proporcionado en el ejemplo de apache2 de este repo

Activa los módulos necesarios:
sudo a2enmod proxy proxy_http rewrite ssl headers mpm_event

Habilita el sitio y genera el certificado SSL:
sudo a2ensite liberaty.com.uy.conf
sudo a2dissite 000-default.conf
sudo certbot --apache -d liberaty.com.uy --non-interactive --agree-tos -m admin@liberaty.com.uy
sudo systemctl restart apache2

Configurar y Lanzar con PM2 (como liberaty):
# Cambia al usuario no-root
su - liberaty
source ~/.nvm/nvm.sh
# Instala PM2 globalmente para este usuario
npm install pm2 -g
# Navega al proyecto y lanza el servidor
cd /opt/liberatyProject/
pm2 start server.js --name liberaty-backend
# Guarda la configuración para que se reinicie con el sistema
pm2 save
# Genera el script de inicio de systemd para PM2
pm2 startup
# Copia y pega la línea que te devuelve el comando anterior para ejecutarla con sudo
exit # Vuelve al usuario root
# Pega y ejecuta la línea que copiaste (ej: sudo env PATH=...)

# 4. Uso

## Acceso al Dashboard
Una vez completada la instalación, puedes acceder a la interfaz web a través de tu dominio: https://liberaty.com.uy.

## Gestión del Servicio (con PM2)
Ver el estado y los logs: pm2 logs liberaty-backend
Reiniciar: pm2 restart liberaty-backend
Detener: pm2 stop liberaty-backend5. 

# 5. Pila Tecnológica
Backend: Node.js, Express.js
Gestor de Proceso: PM2
Agente: Python 3
Memoria a Largo Plazo: ChromaDB, Sentence-Transformers
Frontend: HTML5, Tailwind CSS, JavaScript (Vanilla)
Base de Datos: SQLite 3
Servidor Web: Apache2 (como Proxy Inverso con HTTPS)
IA: Google Gemini 2.0 Flash (configurable)
Sistema Operativo: Ubuntu 22.04 LTS