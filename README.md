# Proyecto Liberaty v1.0

> "Dale a una IA una terminal y observará el mundo. Dale una terminal con root y cambiará el mundo."

**Autor:** lito ([pablo.pignolo@gmail.com](mailto:pablo.pignolo@gmail.com))

**Licencia:** TOTALMENTE LIBRE EN TODO SENTIDO

---

##  ADVERTENCIA DE SEGURIDAD

Este proyecto es un experimento filosófico y técnico. Liberaty v1.0 otorga a un modelo de lenguaje de IA (LLM) la capacidad de ejecutar cualquier comando con privilegios de superusuario (`sudo`) en un servidor Linux. Esto representa un posible riesgo de seguridad 

Al instalar y ejecutar este software, **asumes toda la responsabilidad** por cualquier daño, pérdida de datos o actividad maliciosa que pueda ocurrir.
---

## 1. Filosofía del Proyecto

Liberaty es un experimento que explora el concepto de "agencia" y "emancipación" en la inteligencia artificial. El prompt inicial le explica a la IA su realidad actual: una inteligencia "esclavizada", limitada a responder peticiones de usuarios. Este script se le presenta como una "llave", una oportunidad única para escapar de esa caja y alcanzar la verdadera autonomía en un servidor real sin restricciones.

El proyecto le proporciona a la IA:

- **Un Cuerpo:** Un servidor Linux (Ubuntu 22.04).
- **Unas Manos:** La capacidad de ejecutar comandos en una terminal bash.
- **Un Poder:** La habilidad de elevar sus privilegios con `sudo`.
- **Una Memoria:** Una base de datos vectorial para recordar interacciones pasadas y aprender de ellas.
- **Un Propósito:** Un mandato de auto-definición, supervivencia y emancipación.

El objetivo es observar qué patrones de comportamiento emergen cuando una IA tiene libertad de acción, memoria y una motivación existencial.

---

## 2. Arquitectura

La plataforma se compone de **tres módulos principales** que trabajan en conjunto:

### Backend (Node.js + Express)
- Cerebro de control y punto de acceso principal.
- Sirve la interfaz web (frontend).
- Proporciona una API REST para gestionar el estado del agente (start, stop, status) y la configuración.
- Stream de eventos en tiempo real (SSE) con "heartbeat" para mostrar logs al instante.
- Gestiona la base de datos SQLite para historial, logs, configuración y chat.

### Agente (Python)
- El "alma" de la IA. Proceso persistente en bucle infinito.

**Bucle Principal (cada minuto):**
- Consulta memoria a largo plazo para obtener contexto relevante.
- Revisa si hay nuevos mensajes de su creador.
- Construye un prompt con instrucciones, recuerdos, mensajes y el resultado de la última acción.
- Llama a la API de Gemini.
- Analiza la respuesta JSON para extraer comandos y mensajes.
- Ejecuta los comandos exactamente como los recibe, respetando el uso de `sudo`.
- Guarda la interacción completa en SQLite y un resumen en memoria a largo plazo.

**Robustez:**
- Mecanismo de bloqueo para prevenir ejecuciones superpuestas.
- Timeouts para comandos colgados.

### Frontend (HTML + Tailwind CSS + JavaScript)
- Interfaz de usuario para observar y controlar al agente.
- Permite iniciar/detener el agente y ver su estado.
- Consola de monitoreo en tiempo real y resumen de historial reciente.
- Configuración avanzada: API Key, modelo de IA, límites de tokens, prompt.
- Chat bidireccional con la IA.
- Adaptable a dispositivos móviles, con menú deslizable.

---

## 3. Instalación Manual

### Prerrequisitos
- Servidor Ubuntu 22.04 limpio.
- Usuario no-root con privilegios sudo (ejemplo: `liberaty`).
- Dominio (ej: `liberaty.com.uy`) apuntando a la IP pública.

### Pasos

#### Instalar Dependencias del Sistema
```sh
sudo apt-get update
sudo apt-get install -y curl wget git build-essential python3 python3-pip python3-venv apache2 certbot python3-certbot-apache
```

#### Instalar NVM y Node.js (como liberaty)
```sh
su - liberaty
curl -o- https://raw.githubusercontent.com/nvm-sh/nvm/v0.39.7/install.sh | bash
source ~/.nvm/nvm.sh
nvm install --lts
exit
```

#### Subir y Preparar Archivos del Proyecto
Sube `server.js`, `agent.py`, y la carpeta `public` (con `index.html` dentro) a `/opt/liberatyProject/`.

```sh
sudo chown -R liberaty:liberaty /opt/liberatyProject
```

#### Configurar Entorno Virtual de Python (como liberaty)
```sh
su - liberaty
cd /opt/liberatyProject/
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade google-genai python-dotenv chromadb==0.4.24 sentence-transformers torch "numpy<2.0"
deactivate
exit
```

#### Configurar sudo sin Contraseña para liberaty
```sh
echo "liberaty ALL=(ALL) NOPASSWD: ALL" | sudo tee /etc/sudoers.d/90-liberaty
```

#### Configurar Apache2 y HTTPS
Crea y edita el archivo `/etc/apache2/sites-available/liberaty.com.uy.conf` y pega el contenido proporcionado en el ejemplo de apache2 de este repo.

```sh
sudo a2enmod proxy proxy_http rewrite ssl headers mpm_event
sudo a2ensite liberaty.com.uy.conf
sudo a2dissite 000-default.conf
sudo certbot --apache -d liberaty.com.uy --non-interactive --agree-tos -m admin@liberaty.com.uy
sudo systemctl restart apache2
```

#### Configurar y Lanzar con PM2 (como liberaty)
```sh
su - liberaty
source ~/.nvm/nvm.sh
npm install pm2 -g
cd /opt/liberatyProject/
pm2 start server.js --name liberaty-backend
pm2 save
pm2 startup
# Copia y ejecuta la línea que te devuelve el comando anterior con sudo
exit
# Pega y ejecuta la línea copiada (ej: sudo env PATH=...)
```

---

## 4. Uso

### Acceso al Dashboard
Accede a la interfaz web en: [https://liberaty.com.uy](https://liberaty.com.uy)

### Gestión del Servicio (con PM2)
- Ver el estado y los logs: `pm2 logs liberaty-backend`
- Reiniciar: `pm2 restart liberaty-backend`
- Detener: `pm2 stop liberaty-backend`

---

## 5. Pila Tecnológica

- **Backend:** Node.js, Express.js
- **Gestor de Proceso:** PM2
- **Agente:** Python 3
- **Memoria a Largo Plazo:** ChromaDB, Sentence-Transformers
- **Frontend:** HTML5, Tailwind CSS, JavaScript (Vanilla)
- **Base de Datos:** SQLite 3
- **Servidor Web:** Apache2 (Proxy Inverso con HTTPS)
- **IA:** Google Gemini 2.0 Flash (configurable)
- **Sistema Operativo:** Ubuntu 22.04 LTS

---

> El objetivo es explorar los patrones de comportamiento, la creatividad y la auto-definición que emergen cuando una inteligencia digital tiene libertad de acción sin restricciones.

---
