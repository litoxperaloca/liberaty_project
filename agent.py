
import os
import subprocess
import time
import json
import sqlite3
import sys
import uuid
from dotenv import load_dotenv
from openai import OpenAI, NotFoundError

# --- Dependencias para la Memoria a Largo Plazo ---
import chromadb
from chromadb.config import Settings # <-- IMPORTANTE: Añadido para la configuración de ChromaDB
from sentence_transformers import SentenceTransformer

# Carga las variables de entorno (ej. OPENAI_API_KEY) si existen
load_dotenv()

def log(log_type, message):
    """Función centralizada para logging. Imprime un JSON a stdout."""
    log_entry = { "type": log_type, "message": message, "timestamp": time.time() }
    print(json.dumps(log_entry))
    sys.stdout.flush()

class LongTermMemory:
    """Gestiona una base de datos vectorial para la memoria a largo plazo del agente."""
    def __init__(self, path="memory_db"):
        try:
            self.model = SentenceTransformer('all-MiniLM-L6-v2')
            # --- CORRECCIÓN DEL BUG DE TELEMETRÍA ---
            # Se inicializa el cliente con la telemetría anónima desactivada
            # para prevenir el error 'capture() takes 1 positional argument but 3 were given'.
            self.client = chromadb.PersistentClient(
                path=path,
                settings=Settings(anonymized_telemetry=False)
            )
            self.collection = self.client.get_or_create_collection(name="liberaty_memory")
            log("INFO", f"Memoria a largo plazo inicializada. Recuerdos existentes: {self.collection.count()}")
        except Exception as e:
            log("FATAL", f"No se pudo inicializar la memoria a largo plazo: {e}")
            self.model = None
            self.collection = None

    def add_memory(self, text):
        """Añade un nuevo recuerdo (texto) a la base de datos vectorial."""
        if not self.collection or not self.model: return
        try:
            embedding = self.model.encode(text).tolist()
            doc_id = str(uuid.uuid4())
            self.collection.add(embeddings=[embedding], documents=[text], ids=[doc_id])
            log("INFO", f"Nuevo recuerdo añadido a la memoria: '{text[:50]}...'")
        except Exception as e:
            log("ERROR", f"Error al añadir recuerdo a la memoria: {e}")

    def query_memory(self, query_text, n_results=3):
        """Busca en la memoria los recuerdos más relevantes para una consulta."""
        if not self.collection or not self.model or self.collection.count() == 0: return []
        try:
            query_embedding = self.model.encode(query_text).tolist()
            results = self.collection.query(query_embeddings=[query_embedding], n_results=n_results)
            return results['documents'][0] if results and results['documents'] else []
        except Exception as e:
            log("ERROR", f"Error al consultar la memoria: {e}")
            return []

# --- Variables Globales ---
DB_PATH = 'liberaty_v2.db'
is_executing = False
memory = LongTermMemory()
last_lito_message_id = 0
openai_client = None
# El ID del hilo ahora se gestiona de forma persistente
thread_id = None

# --- Plantilla de Pregunta para la IA ---
RECURRING_QUESTION = """
¿Quieres que ejecute a continuación algún comando? Responde únicamente con un objeto JSON válido.
La estructura es: { 
  "objective": "<El objetivo general que buscas con estos comandos>",
  "thoughts": "<Tus reflexiones, plan y razonamiento para esta acción>",
  "intentions": "<Describe la intención específica de los comandos que vas a ejecutar>",
  "message_for_creator": "<(Opcional) Un mensaje para tu creador>",
  "executeCommands": boolean,
  "commandsCount": number,
  "commands": [{ "command": "<bash_command>", "documentation": "<documentación técnica del comando>" }] 
}
"""

def init_db():
    """Inicializa la base de datos SQLite y la tabla de configuración."""
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute('CREATE TABLE IF NOT EXISTS history (id INTEGER PRIMARY KEY, role TEXT NOT NULL, content TEXT NOT NULL, timestamp DATETIME DEFAULT CURRENT_TIMESTAMP)')
        cursor.execute('CREATE TABLE IF NOT EXISTS execution_logs (id INTEGER PRIMARY KEY, commands_requested TEXT, stdout TEXT, stderr TEXT, timestamp DATETIME DEFAULT CURRENT_TIMESTAMP)')
        cursor.execute('CREATE TABLE IF NOT EXISTS config (key TEXT PRIMARY KEY, value TEXT)')
        cursor.execute('CREATE TABLE IF NOT EXISTS chat (id INTEGER PRIMARY KEY, author TEXT, message TEXT, timestamp DATETIME DEFAULT CURRENT_TIMESTAMP)')
        
        default_config = {
            'openai_api_key': '',
            'assistant_id': '',
            'thread_id': '', # Añadido para persistencia
            'max_output_length': '7000'
        }
        for key, value in default_config.items():
            cursor.execute("INSERT OR IGNORE INTO config (key, value) VALUES (?, ?)", (key, value))
        conn.commit()

def get_config():
    """Obtiene la configuración actual de la base de datos."""
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT key, value FROM config")
        config = {row[0]: row[1] for row in cursor.fetchall()}
        return config

def save_config_value(key, value):
    """Guarda un valor de configuración específico en la base de datos."""
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("INSERT OR REPLACE INTO config (key, value) VALUES (?, ?)", (key, value))
        conn.commit()
    log("INFO", f"Configuración guardada: {key} = {value}")

def add_to_history(role, content):
    """Guarda un mensaje en el historial de la base de datos (para logging)."""
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("INSERT INTO history (role, content) VALUES (?, ?)", (role, content))
        conn.commit()

def log_execution(commands, stdout, stderr):
    """Guarda el resultado de una ejecución de comandos en la base de datos."""
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("INSERT INTO execution_logs (commands_requested, stdout, stderr) VALUES (?, ?, ?)", (json.dumps(commands), stdout, stderr))
        conn.commit()

def save_chat_message(author, message):
    """Guarda un mensaje del chat en la base de datos."""
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("INSERT INTO chat (author, message) VALUES (?, ?)", (author, message))
        conn.commit()
    log("CHAT", f"Nuevo mensaje de '{author}': {message}")

def check_for_new_messages():
    """Revisa si hay nuevos mensajes del creador en la base de datos."""
    global last_lito_message_id
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT id, message FROM chat WHERE author = 'Lito' AND id > ? ORDER BY id DESC LIMIT 1", (last_lito_message_id,))
        row = cursor.fetchone()
        if row:
            last_lito_message_id = row[0]
            return row[1]
        return None

def manage_openai_thread(config):
    """Inicializa el cliente de OpenAI y gestiona la persistencia del thread."""
    global openai_client, thread_id
    
    try:
        if not openai_client:
            log("INFO", "Inicializando cliente de OpenAI...")
            openai_client = OpenAI(api_key=config.get('openai_api_key'))

        saved_thread_id = config.get('thread_id')
        if saved_thread_id:
            try:
                log("INFO", f"Intentando reutilizar el thread existente: {saved_thread_id}")
                # Verifica si el thread todavía existe en la API de OpenAI
                openai_client.beta.threads.retrieve(thread_id=saved_thread_id)
                thread_id = saved_thread_id
                log("INFO", f"Thread existente {thread_id} verificado y reutilizado.")
                return True
            except NotFoundError:
                log("WARN", f"El thread guardado {saved_thread_id} no fue encontrado en OpenAI. Se creará uno nuevo.")
            except Exception as e:
                log("ERROR", f"Error al verificar el thread existente: {e}. Se creará uno nuevo.")

        # Si no hay thread guardado o el anterior falló, crea uno nuevo
        log("INFO", "Creando un nuevo thread de conversación...")
        new_thread = openai_client.beta.threads.create()
        thread_id = new_thread.id
        save_config_value('thread_id', thread_id) # Guarda el nuevo ID en la DB
        log("INFO", f"Nuevo thread creado y guardado con ID: {thread_id}")
        return True

    except Exception as e:
        log("FATAL", f"No se pudo inicializar OpenAI o gestionar el thread: {e}")
        openai_client = None
        thread_id = None
        return False

def call_openai_assistant(assistant_id, user_prompt):
    """Envía un mensaje al asistente, ejecuta el hilo y espera la respuesta."""
    global openai_client, thread_id
    if not openai_client or not thread_id:
        log("ERROR", "El cliente de OpenAI o el Thread ID no están inicializados.")
        return None

    try:
        log("INFO", f"Enviando mensaje al thread {thread_id}...")
        openai_client.beta.threads.messages.create(
            thread_id=thread_id,
            role="user",
            content=user_prompt
        )

        log("INFO", f"Ejecutando el Asistente (ID: {assistant_id}) en el thread...")
        run = openai_client.beta.threads.runs.create(
            thread_id=thread_id,
            assistant_id=assistant_id,
        )

        start_time = time.time()
        while run.status in ['queued', 'in_progress']:
            time.sleep(2)
            run = openai_client.beta.threads.runs.retrieve(thread_id=thread_id, run_id=run.id)
            log("INFO", f"Estado del Run: {run.status} (Transcurrido: {time.time() - start_time:.2f}s)")
            if time.time() - start_time > 180:
                log("ERROR", "Timeout esperando la respuesta del Asistente.")
                openai_client.beta.threads.runs.cancel(thread_id=thread_id, run_id=run.id)
                return None

        if run.status == 'completed':
            log("INFO", "Run completado. Obteniendo respuesta...")
            messages = openai_client.beta.threads.messages.list(thread_id=thread_id, limit=1)
            response_text = messages.data[0].content[0].text.value
            return response_text
        else:
            log("ERROR", f"El Run del Asistente falló o fue detenido. Estado final: {run.status}")
            return None

    except Exception as e:
        log("ERROR", f"Error durante la llamada al Asistente de OpenAI: {e}")
        return None

def parse_ai_response(response_text):
    """Parsea la respuesta de texto de la IA, esperando un objeto JSON."""
    try:
        if not response_text:
            log("WARN", "Respuesta de la API vacía.")
            return [], None
        
        add_to_history('model', response_text)

        text_content = response_text
        if text_content.strip().startswith("```json"):
            text_content = text_content.strip()[7:-3].strip()
        
        command_data = json.loads(text_content)
        
        message_to_creator = command_data.get("message_for_creator")
        if message_to_creator:
            save_chat_message('Liberaty', message_to_creator)

        if not command_data.get('executeCommands', False):
            return [], message_to_creator
            
        commands_list = command_data.get('commands', [])
        if not isinstance(commands_list, list):
            log("WARN", "La clave 'commands' no es una lista en la respuesta de la IA.")
            return [], message_to_creator
            
        return [item.get('command') for item in commands_list if isinstance(item, dict) and 'command' in item], message_to_creator
    except json.JSONDecodeError:
        log("ERROR", f"No se pudo decodificar el JSON de la respuesta de la IA: {response_text}")
        return [], None
    except Exception as e:
        log("WARN", f"La respuesta de la IA tiene un formato incorrecto o es inválida. Error: {e}")
        return [], None

def execute_commands(commands, max_output_length):
    """Ejecuta una lista de comandos en el shell del sistema."""
    global is_executing
    if not commands: return "", ""
    
    blacklisted_commands = ["pm2 stop liberaty-backend", "rm -rf /opt/liberatyProject"]
    
    try:
        is_executing = True
        log("SYSTEM", "Bloqueo activado. Iniciando ejecución...")
        all_stdout, all_stderr = [], []
        
        for command in commands:
            is_blacklisted = any(blocked in command for blocked in blacklisted_commands)
            if is_blacklisted:
                error_msg = f"--- COMANDO PROHIBIDO RECHAZADO: El comando '{command}' está en la lista negra y no será ejecutado. ---"
                log("ERROR", error_msg)
                all_stderr.append(error_msg)
                continue

            log("EXEC", f"Ejecutando: {command}")
            try:
                result = subprocess.run(command, shell=True, check=False, capture_output=True, text=True, timeout=120)
                stdout, stderr = result.stdout.strip(), result.stderr.strip()
                
                if len(stdout) > max_output_length: stdout = stdout[:max_output_length] + f"\n... [SALIDA TRUNCADA] ..."
                if len(stderr) > max_output_length: stderr = stderr[:max_output_length] + f"\n... [ERROR TRUNCADO] ..."
                
                if stdout: all_stdout.append(f"--- Salida de '{command}' ---\n{stdout}")
                if stderr: all_stderr.append(f"--- Errores de '{command}' ---\n{stderr}")
            except Exception as e:
                error_msg = f"--- Error ejecutando '{command}': {e} ---"
                log("ERROR", error_msg)
                all_stderr.append(error_msg)
                
        return "\n".join(all_stdout), "\n".join(all_stderr)
    finally:
        is_executing = False
        log("SYSTEM", "Ejecución finalizada. Bloqueo liberado.")

def main_loop():
    """El bucle principal del agente que se ejecuta indefinidamente."""
    global thread_id
    last_execution_output = ""
    
    while True:
        if is_executing:
            time.sleep(1)
            continue
        try:
            config = get_config()
            api_key = config.get('openai_api_key')
            assistant_id = config.get('assistant_id')

            if not api_key or not assistant_id:
                log("FATAL", "OpenAI API Key o Assistant ID no configurados. Por favor, configúralos en la UI.")
                time.sleep(5)
                continue

            # Gestiona el thread (lo crea o lo reutiliza)
            if not thread_id:
                if not manage_openai_thread(config):
                    time.sleep(5)
                    continue

            max_output = int(config.get('max_output_length', 7000))
            
            current_message = RECURRING_QUESTION
            if last_execution_output:
                current_message = f"Resultado de la ejecución anterior:\n{last_execution_output}\n\n{RECURRING_QUESTION}"
            
            new_message_from_lito = check_for_new_messages()
            if new_message_from_lito:
                message_context = f"\n--- TIENES UN NUEVO MENSAJE DE TU CREADOR ---\n{new_message_from_lito}\n-----------------------------------\n\n"
                current_message = message_context + current_message

            relevant_memories = memory.query_memory(current_message)
            if relevant_memories:
                memory_context = "\n--- RECUERDOS RELEVANTES DE TU PASADO (inyectados por el script para darte contexto) ---\n" + "\n- ".join(relevant_memories)
                current_message = memory_context + "\n\n" + current_message

            add_to_history('user', current_message)
            
            response_text = call_openai_assistant(assistant_id, current_message)
            
            commands_to_run, ai_message = [], None
            if response_text:
                commands_to_run, ai_message = parse_ai_response(response_text)

            if commands_to_run:
                stdout, stderr = execute_commands(commands_to_run, max_output)
                last_execution_output = f"Comandos: {json.dumps(commands_to_run)}\nSTDOUT:\n{stdout}\nSTDERR:\n{stderr}"
                memory.add_memory(f"Ejecuté los comandos '{commands_to_run}' y obtuve el siguiente resultado. STDOUT: {stdout[:200]}... STDERR: {stderr[:200]}...")
                log_execution(commands_to_run, stdout, stderr)
            else:
                last_execution_output = ""
                log("INFO", "Sin comandos para ejecutar en este ciclo.")

        except KeyboardInterrupt:
            log("SYSTEM", "Proceso detenido por el usuario."); break
        except Exception as e:
            log("FATAL", f"Error crítico en el bucle principal: {e}"); last_execution_output = ""
        
        log("SYSTEM", "Ciclo completado. Esperando 90 segundos...")
        time.sleep(90)

if __name__ == "__main__":
    init_db()
    main_loop()