// api-server.js (Liberaty v3 - con Autenticación de Admin)
// =================================================================

// --- Dependencias ---
const express = require('express');
const http = require('http');
const { Server } = require("socket.io");
const { createClient } = require('redis');
const sqlite3 = require('sqlite3').verbose();
const path = require('path');
const pm2 = require('pm2');
const crypto = require('crypto'); // Para generar tokens seguros

// --- Constantes y Configuración ---
const PORT = process.env.PORT || 3000;
const DB_PATH = path.join(__dirname, 'liberaty_v3.db');
const REDIS_URL = process.env.REDIS_URL || 'redis://localhost:6379';
// ¡IMPORTANTE! Cambia esta contraseña por una contraseña segura
const ADMIN_PASSWORD = process.env.ADMIN_PASSWORD || 'admin123';

const app = express();
const server = http.createServer(app);
const io = new Server(server, { cors: { origin: "*" } });

// --- Conexiones y Estado Global ---
const db = new sqlite3.Database(DB_PATH);
const redisClient = createClient({ url: REDIS_URL });
const redisSubscriber = redisClient.duplicate();
let agentActive = false;
let agentInterval = null;
let adminToken = null; // Almacenará el token de sesión del admin

// --- Middleware ---
app.use(express.json());
app.use(express.static(path.join(__dirname, 'public')));

// Middleware de autenticación para rutas protegidas
const protectApi = (req, res, next) => {
    const providedToken = req.headers['authorization']?.split(' ')[1]; // Espera "Bearer <token>"
    if (adminToken && providedToken === adminToken) {
        next(); // El token es válido, continuar.
    } else {
        res.status(403).json({ error: 'Acceso denegado. Se requiere autenticación de administrador.' });
    }
};

// --- Lógica de Comunicación (Redis y WebSockets) ---

async function connectServices() {
    try {
        await redisClient.connect();
        await redisSubscriber.connect();
        console.log('Conectado a Redis correctamente.');
        await redisSubscriber.subscribe('liberaty:logs', (message) => {
            io.emit('agent-log', JSON.parse(message));
        });
    } catch (err) {
        console.error('CRITICAL: No se pudo conectar a Redis.', err);
        process.exit(1);
    }
}

// --- Rutas de la API ---

// --- Rutas Públicas (no requieren autenticación) ---
app.get('/api/status/processes', (req, res) => { /* ... (sin cambios) ... */ });
app.get('/api/stats/interactions', (req, res) => { /* ... (sin cambios) ... */ });
app.get('/api/recent-activity', (req, res) => { /* ... (sin cambios) ... */ });
app.get('/api/history', (req, res) => { /* ... (sin cambios) ... */ });
app.get('/api/logs', (req, res) => { /* ... (sin cambios) ... */ });
app.get('/api/chat', (req, res) => { /* ... (sin cambios) ... */ });

// --- Ruta de Autenticación ---
app.post('/api/auth/login', (req, res) => {
    const { password } = req.body;
    if (password === ADMIN_PASSWORD) {
        // Genera un token de sesión seguro y aleatorio
        adminToken = crypto.randomBytes(32).toString('hex');
        console.log('Administrador ha iniciado sesión.');
        res.json({ message: 'Inicio de sesión exitoso.', token: adminToken });
    } else {
        res.status(401).json({ error: 'Contraseña incorrecta.' });
    }
});

// --- Rutas Protegidas (requieren autenticación) ---
app.post('/api/agent/start', protectApi, (req, res) => {
    if (agentActive) return res.status(400).json({ message: 'El agente ya está activo.' });
    agentActive = true;
    console.log('Agente activado por administrador.');
    redisClient.publish('liberaty:tasks', JSON.stringify({ task: 'execute_cycle' }));
    agentInterval = setInterval(() => {
        if (agentActive) redisClient.publish('liberaty:tasks', JSON.stringify({ task: 'execute_cycle' }));
    }, 90000);
    io.emit('status-change', { agent_active: true });
    res.json({ message: 'Ciclo del agente iniciado.' });
});

app.post('/api/agent/stop', protectApi, (req, res) => {
    if (!agentActive) return res.status(400).json({ message: 'El agente no está activo.' });
    agentActive = false;
    clearInterval(agentInterval);
    agentInterval = null;
    console.log('Agente desactivado por administrador.');
    io.emit('status-change', { agent_active: false });
    res.json({ message: 'Ciclo del agente detenido.' });
});

app.get('/api/config', protectApi, (req, res) => {
    db.all("SELECT key, value FROM config", [], (err, rows) => {
        if (err) return res.status(500).json({ error: err.message });
        const config = rows.reduce((acc, row) => { acc[row.key] = row.value; return acc; }, {});
        res.json(config);
    });
});

app.post('/api/config', protectApi, (req, res) => {
    const config = req.body;
    const stmt = db.prepare("INSERT OR REPLACE INTO config (key, value) VALUES (?, ?)");
    Object.entries(config).forEach(([key, value]) => stmt.run(key, String(value)));
    stmt.finalize((err) => {
        if (err) return res.status(500).json({ error: `Error al guardar: ${err.message}` });
        res.json({ message: 'Configuración guardada.' });
    });
});

app.post('/api/chat', protectApi, (req, res) => {
    const { message } = req.body;
    if (!message || typeof message !== 'string' || message.trim() === '') {
        return res.status(400).json({ error: 'El mensaje no puede estar vacío.' });
    }
    const newMessage = {
        author: 'Lito',
        message: message.trim(),
        timestamp: new Date().toISOString()
    };
    db.run("INSERT INTO chat (author, message, timestamp) VALUES (?, ?, ?)", [newMessage.author, newMessage.message, newMessage.timestamp], function(err) {
        if (err) return res.status(500).json({ error: `Error al guardar: ${err.message}` });
        io.emit('new-chat-message', newMessage);
        res.status(201).json({ id: this.lastID });
    });
});


// --- Código de los endpoints públicos (sin cambios) ---
app.get('/api/status/processes', (req, res) => {
    pm2.list((err, list) => {
        if (err) return res.status(500).json({ error: 'No se pudo obtener el estado.' });
        const apiProcess = list.find(p => p.name === 'liberaty-api');
        const workerProcess = list.find(p => p.name === 'liberaty-worker');
        res.json({
            agent_active: agentActive,
            api_process: apiProcess?.pm2_env?.status === 'online',
            worker_process: workerProcess?.pm2_env?.status === 'online',
        });
    });
});

app.get('/api/stats/interactions', (req, res) => {
    const query = `
        SELECT 
            SUM(CASE WHEN json_valid(content) AND json_extract(content, '$.executeCommands') = 1 THEN 1 ELSE 0 END) as with_commands,
            SUM(CASE WHEN json_valid(content) AND json_extract(content, '$.executeCommands') = 0 AND json_extract(content, '$.message_for_creator') IS NOT NULL THEN 1 ELSE 0 END) as message_only,
            SUM(CASE WHEN json_valid(content) = 0 OR content = '{}' OR (json_extract(content, '$.executeCommands') = 0 AND json_extract(content, '$.message_for_creator') IS NULL) THEN 1 ELSE 0 END) as empty_or_error
        FROM history WHERE role = 'model'`;
    db.get(query, (err, row) => {
        if (err) return res.status(500).json({ error: err.message });
        res.json({
            with_commands: row.with_commands || 0,
            message_only: row.message_only || 0,
            empty_or_error: row.empty_or_error || 0,
        });
    });
});

app.get('/api/recent-activity', async (req, res) => {
    try {
        const lastObjectiveQuery = `SELECT json_extract(content, '$.objective') as objective FROM history WHERE role = 'model' AND json_extract(content, '$.objective') IS NOT NULL AND json_extract(content, '$.objective') != '' ORDER BY timestamp DESC LIMIT 1`;
        const lastCommandQuery = `SELECT commands_requested, stdout, stderr FROM execution_logs ORDER BY timestamp DESC LIMIT 1`;
        const lastChatMessageQuery = `SELECT message FROM chat WHERE author = 'Liberaty' ORDER BY timestamp DESC LIMIT 1`;

        const last_objective = await new Promise((resolve, reject) => db.get(lastObjectiveQuery, (err, row) => err ? reject(err) : resolve(row?.objective)));
        const last_command_log = await new Promise((resolve, reject) => db.get(lastCommandQuery, (err, row) => err ? reject(err) : resolve(row)));
        const last_chat_message = await new Promise((resolve, reject) => db.get(lastChatMessageQuery, (err, row) => err ? reject(err) : resolve(row?.message)));

        let last_command = { command: null, stdout: null, stderr: null };
        if (last_command_log) {
            try {
                const commands = JSON.parse(last_command_log.commands_requested);
                last_command.command = commands[0] || 'N/A';
                last_command.stdout = last_command_log.stdout;
                last_command.stderr = last_command_log.stderr;
            } catch { last_command.command = 'Error al parsear comando'; }
        }
        res.json({ last_objective, last_command, last_chat_message });
    } catch (err) {
        res.status(500).json({ error: err.message });
    }
});

app.get('/api/history', (req, res) => { db.all("SELECT role, content, timestamp FROM history ORDER BY timestamp DESC LIMIT 100", [], (err, rows) => res.status(err ? 500 : 200).json(err ? {error: err.message} : rows))});
app.get('/api/logs', (req, res) => { db.all("SELECT commands_requested, stdout, stderr, timestamp FROM execution_logs ORDER BY timestamp DESC LIMIT 100", [], (err, rows) => res.status(err ? 500 : 200).json(err ? {error: err.message} : rows))});
app.get('/api/chat', (req, res) => { db.all("SELECT author, message, timestamp FROM chat ORDER BY timestamp ASC", [], (err, rows) => res.status(err ? 500 : 200).json(err ? {error: err.message} : rows))});


// --- Inicio del Servidor ---
server.listen(PORT, '0.0.0.0', async () => {
    console.log(`Servidor API de Liberaty v3 escuchando en http://0.0.0.0:${PORT}`);
    await connectServices();
});
