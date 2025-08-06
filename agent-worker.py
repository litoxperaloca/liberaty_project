# agent-worker.py (Liberaty v3)
# =================================================================
# Este script actúa como un worker persistente e independiente.
# No se ejecuta en un bucle de tiempo, sino que escucha activamente
# en un canal de Redis por nuevas tareas publicadas por la API de control.

import os
import subprocess
import time
import json
import sqlite3
import sys
import uuid
import redis
from dotenv import load_dotenv
from openai import OpenAI, NotFoundError
import chromadb
from chromadb.config import Settings
from sentence_transformers import SentenceTransformer

# --- Configuración ---
load_dotenv()
DB_PATH = 'liberaty_v3.db'
REDIS_URL = os.getenv('REDIS_URL', 'redis://localhost:6379')

# --- Conexiones a Servicios ---
try:
    redis_client = redis.from_url(REDIS_URL, decode_responses=True)
    redis_client.ping()
    print("Worker conectado a Redis correctamente.")
except redis.exceptions.ConnectionError as e:
    print(f"CRITICAL: Worker no pudo conectar a Redis. Error: {e}", file=sys.stderr)
    sys.exit(1)


# --- Lógica de Logging ---
def log(log_type, message):
    """Función de logging que ahora publica en un canal de Redis."""
    log_entry = { "type": log_type, "message": str(message), "timestamp": time.time() }
    try:
        log_json = json.dumps(log_entry, ensure_ascii=False)
        redis_client.publish('liberaty:logs', log_json)
    except Exception as e:
        # Usamos print aquí porque si Redis falla, no podemos usar log()
        print(f"Error publicando log a Redis: {e}", file=sys.stderr)

# --- Clases y Funciones de Soporte ---

class LongTermMemory:
    def __init__(self, path="memory_db_v3"):
        try:
            self.model = SentenceTransformer('all-MiniLM-L6-v2')
            self.client = chromadb.PersistentClient(path=path, settings=Settings(anonymized_telemetry=False))
            self.collection = self.client.get_or_create_collection(name="liberaty_memory_v3")
            log("INFO", "Memoria a largo plazo inicializada.")
        except Exception as e:
            log("FATAL", f"No se pudo inicializar la memoria a largo plazo: {e}")
            self.model = None
            self.collection = None

    def add_memory(self, text):
        if not self.collection or not self.model: return
        try:
            embedding = self.model.encode(text).tolist()
            doc_id = str(uuid.uuid4())
            self.collection.add(embeddings=[embedding], documents=[text], ids=[doc_id])
            log("INFO", f"Nuevo recuerdo añadido a la memoria: '{text[:50]}...'")
        except Exception as e:
            log("ERROR", f"Error al añadir recuerdo a la memoria: {e}")

    def query_memory(self, query_text, n_results=3):
        if not self.collection or not self.model or self.collection.count() == 0: return []
        try:
            query_embedding = self.model.encode(query_text).tolist()
            results = self.collection.query(query_embeddings=[query_embedding], n_results=n_results)
            return results['documents'][0] if results and results['documents'] else []
        except Exception as e:
            log("ERROR", f"Error al consultar la memoria: {e}")
            return []

def get_config():
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT key, value FROM config")
        return {row[0]: row[1] for row in cursor.fetchall()}

def save_config_value(key, value):
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("INSERT OR REPLACE INTO config (key, value) VALUES (?, ?)", (key, value))
    log("INFO", f"Configuración guardada en DB: {key}")

def add_to_history(role, content):
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("INSERT INTO history (role, content) VALUES (?, ?)", (role, content))

def log_execution(commands, stdout, stderr):
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("INSERT INTO execution_logs (commands_requested, stdout, stderr) VALUES (?, ?, ?)", (json.dumps(commands), stdout, stderr))

def manage_openai_thread(config):
    global openai_client, thread_id
    try:
        if not openai_client:
            log("INFO", "Inicializando cliente de OpenAI...")
            openai_client = OpenAI(api_key=config.get('openai_api_key'))
        
        saved_thread_id = get_config().get('thread_id')
        if saved_thread_id:
            try:
                openai_client.beta.threads.retrieve(thread_id=saved_thread_id)
                thread_id = saved_thread_id
                log("INFO", f"Thread existente {thread_id} reutilizado.")
                return True
            except (NotFoundError, Exception):
                log("WARN", "Thread guardado no encontrado. Se creará uno nuevo.")
        
        new_thread = openai_client.beta.threads.create()
        thread_id = new_thread.id
        save_config_value('thread_id', thread_id)
        log("INFO", f"Nuevo thread creado y guardado: {thread_id}")
        return True
    except Exception as e:
        log("FATAL", f"Fallo al gestionar thread de OpenAI: {e}")
        return False

def call_openai_assistant(assistant_id, user_prompt):
    global openai_client, thread_id
    if not openai_client or not thread_id: return None
    try:
        openai_client.beta.threads.messages.create(thread_id=thread_id, role="user", content=user_prompt)
        run = openai_client.beta.threads.runs.create(thread_id=thread_id, assistant_id=assistant_id)
        start_time = time.time()
        while run.status in ['queued', 'in_progress']:
            time.sleep(2)
            run = openai_client.beta.threads.runs.retrieve(thread_id=thread_id, run_id=run.id)
            if time.time() - start_time > 180:
                openai_client.beta.threads.runs.cancel(thread_id=thread_id, run_id=run.id)
                return None
        if run.status == 'completed':
            messages = openai_client.beta.threads.messages.list(thread_id=thread_id, limit=1)
            return messages.data[0].content[0].text.value
        return None
    except Exception as e:
        log("ERROR", f"Error en llamada a OpenAI: {e}")
        return None

def parse_ai_response(response_text):
    if not response_text: return [], None
    add_to_history('model', response_text)
    if response_text.strip().startswith("```json"):
        response_text = response_text.strip()[7:-3].strip()
    try:
        data = json.loads(response_text)
        if data.get("message_for_creator"):
            with sqlite3.connect(DB_PATH) as conn:
                conn.execute("INSERT INTO chat (author, message) VALUES (?, ?)", ('Liberaty', data.get("message_for_creator")))
        if not data.get('executeCommands', False): return [], data.get("message_for_creator")
        return [c.get('command') for c in data.get('commands', []) if isinstance(c, dict)], data.get("message_for_creator")
    except Exception as e:
        log("ERROR", f"Error parseando JSON de la IA: {e}")
        return [], None

def execute_commands(commands, max_output_length):
    if not commands: return "", ""
    all_stdout, all_stderr = [], []
    for command in commands:
        log("EXEC", f"Ejecutando: {command}")
        try:
            result = subprocess.run(command, shell=True, check=False, capture_output=True, text=True, timeout=120)
            stdout, stderr = result.stdout.strip(), result.stderr.strip()
            if len(stdout) > max_output_length: stdout = stdout[:max_output_length] + "..."
            if len(stderr) > max_output_length: stderr = stderr[:max_output_length] + "..."
            if stdout: all_stdout.append(f"--- Salida de '{command}' ---\n{stdout}")
            if stderr: all_stderr.append(f"--- Errores de '{command}' ---\n{stderr}")
        except Exception as e:
            error_msg = f"--- Error ejecutando '{command}': {e} ---"
            log("ERROR", error_msg)
            all_stderr.append(error_msg)
    return "\n".join(all_stdout), "\n".join(all_stderr)


# --- Lógica del Worker ---
openai_client = None
thread_id = None
last_execution_output = ""
memory = LongTermMemory()
RECURRING_QUESTION = """¿Quieres que ejecute a continuación algún comando? Responde únicamente con un objeto JSON válido con la estructura especificada."""

def process_task(task_data):
    global last_execution_output
    log("INFO", f"Tarea recibida del bus de mensajería: {task_data.get('task')}")

    try:
        config = get_config()
        api_key = config.get('openai_api_key')
        assistant_id = config.get('assistant_id')

        if not api_key or not assistant_id:
            log("FATAL", "API Key o Assistant ID no configurados. La tarea no puede continuar.")
            return

        if not manage_openai_thread(config):
            return

        current_message = RECURRING_QUESTION
        if last_execution_output:
            current_message = f"Resultado de la ejecución anterior:\n{last_execution_output}\n\n{RECURRING_QUESTION}"
        
        relevant_memories = memory.query_memory(current_message)
        if relevant_memories:
            memory_context = "\n--- RECUERDOS RELEVANTES DE TU PASADO ---\n" + "\n- ".join(relevant_memories)
            current_message = memory_context + "\n\n" + current_message
        
        add_to_history('user', current_message)
        response_text = call_openai_assistant(assistant_id, current_message)
        
        commands_to_run, _ = parse_ai_response(response_text) if response_text else ([], None)

        if commands_to_run:
            stdout, stderr = execute_commands(commands_to_run, int(config.get('max_output_length', 7000)))
            last_execution_output = f"Comandos: {json.dumps(commands_to_run)}\nSTDOUT:\n{stdout}\nSTDERR:\n{stderr}"
            memory.add_memory(f"Ejecuté '{commands_to_run}' y obtuve: STDOUT: {stdout[:100]}... STDERR: {stderr[:100]}...")
            log_execution(commands_to_run, stdout, stderr)
        else:
            last_execution_output = ""
            log("INFO", "Sin comandos para ejecutar en este ciclo.")

    except Exception as e:
        log("FATAL", f"Error crítico procesando la tarea: {e}")
        last_execution_output = ""


def main():
    """Función principal que inicia el worker y maneja el apagado gracioso."""
    log("SYSTEM", "Agente Worker v3 iniciando...")
    log("SYSTEM", "Escuchando por tareas en el canal 'liberaty:tasks' de Redis...")
    
    pubsub = redis_client.pubsub()
    
    try:
        pubsub.subscribe('liberaty:tasks')
        for message in pubsub.listen():
            if message['type'] == 'message':
                try:
                    task_data = json.loads(message['data'])
                    if task_data.get('task') == 'execute_cycle':
                        process_task(task_data)
                except json.JSONDecodeError:
                    log("ERROR", f"No se pudo decodificar el mensaje de la tarea: {message['data']}")
                except Exception as e:
                    log("FATAL", f"Error inesperado en el bucle de escucha: {e}")
    except KeyboardInterrupt:
        log("SYSTEM", "Señal de interrupción recibida. Apagando worker...")
    except Exception as e:
        log("FATAL", f"Error no capturado en el bucle principal: {e}")
    finally:
        log("SYSTEM", "Cerrando conexiones y terminando.")
        pubsub.close()
        redis_client.close()

if __name__ == "__main__":
    main()
