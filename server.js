const express = require('express');
const cors = require('cors');
const bodyParser = require('body-parser');
const { spawn } = require('child_process');
const sqlite3 = require('sqlite3').verbose();
const app = express();
const PORT = 3000;
const DB_PATH = 'liberaty_v2.db';
let clients = [];
const db = new sqlite3.Database(DB_PATH, (err) => {
    if (err) { console.error('Error al abrir la base de datos', err.message); } 
    else {
        console.log('Conectado a la base de datos SQLite.');
        db.run(`CREATE TABLE IF NOT EXISTS config (key TEXT PRIMARY KEY, value TEXT)`);
        db.run(`CREATE TABLE IF NOT EXISTS history (id INTEGER PRIMARY KEY, role TEXT, content TEXT, timestamp DATETIME DEFAULT CURRENT_TIMESTAMP)`);
        db.run(`CREATE TABLE IF NOT EXISTS execution_logs (id INTEGER PRIMARY KEY, commands_requested TEXT, stdout TEXT, stderr TEXT, timestamp DATETIME DEFAULT CURRENT_TIMESTAMP)`);
        db.run(`CREATE TABLE IF NOT EXISTS chat (id INTEGER PRIMARY KEY, author TEXT, message TEXT, timestamp DATETIME DEFAULT CURRENT_TIMESTAMP)`);
    }
});
app.use(cors());
app.use(bodyParser.json());
app.use(express.static('public')); 
let agentProcess = null;
function sendEventToClients(data) {
    const eventString = `data: ${JSON.stringify(data)}\n\n`;
    clients.forEach(client => client.res.write(eventString));
}
app.get('/api/agent/stream', (req, res) => {
    res.setHeader('Content-Type', 'text/event-stream');
    res.setHeader('Cache-Control', 'no-cache');
    res.setHeader('Connection', 'keep-alive');
    res.flushHeaders();
    const clientId = Date.now();
    const newClient = { id: clientId, res };
    clients.push(newClient);
    console.log(`[SSE] Cliente conectado: ${clientId}`);
    res.write(`data: ${JSON.stringify({ type: 'SYSTEM', message: 'Conectado al stream del agente.' })}\n\n`);
    req.on('close', () => {
        console.log(`[SSE] Cliente desconectado: ${clientId}`);
        clients = clients.filter(client => client.id !== clientId);
    });
});
app.get('/api/agent/status', (req, res) => { res.json({ running: agentProcess !== null }); });
app.post('/api/agent/start', (req, res) => {
    if (agentProcess) { return res.status(400).json({ message: 'El agente ya está en ejecución.' }); }
    const pythonExecutable = '/opt/liberatyProject/.venv/bin/python3';
    agentProcess = spawn(pythonExecutable, ['-u', 'agent.py']);
    agentProcess.stdout.on('data', (data) => {
        const message = data.toString().trim();
        console.log(`[Agent STDOUT]: ${message}`);
        try { sendEventToClients(JSON.parse(message)); } 
        catch (e) { sendEventToClients({ type: 'RAW', message }); }
    });
    agentProcess.stderr.on('data', (data) => {
        const message = data.toString().trim();
        console.error(`[Agent STDERR]: ${message}`);
        sendEventToClients({ type: 'ERROR', message: `Agent STDERR: ${message}` });
    });
    agentProcess.on('close', (code) => {
        console.log(`El proceso del agente terminó con el código ${code}`);
        sendEventToClients({ type: 'SYSTEM', message: `Agente detenido. Código de salida: ${code}` });
        agentProcess = null;
    });
    res.json({ message: 'Agente iniciado correctamente.' });
});
app.post('/api/agent/stop', (req, res) => {
    if (!agentProcess) { return res.status(400).json({ message: 'El agente no está en ejecución.' }); }
    agentProcess.kill('SIGINT'); 
    agentProcess = null;
    res.json({ message: 'Agente detenido.' });
});
app.get('/api/config', (req, res) => {
    db.all("SELECT key, value FROM config", [], (err, rows) => {
        if (err) return res.status(500).json({ error: err.message });
        const config = rows.reduce((acc, row) => { acc[row.key] = row.value; return acc; }, {});
        res.json(config);
    });
});
app.post('/api/config', (req, res) => {
    const config = req.body;
    const stmt = db.prepare("INSERT OR REPLACE INTO config (key, value) VALUES (?, ?)");
    Object.entries(config).forEach(([key, value]) => {
        stmt.run(key, value);
    });
    stmt.finalize((err) => {
        if (err) return res.status(500).json({ error: err.message });
        res.json({ message: 'Configuración guardada.' });
    });
});
app.get('/api/history', (req, res) => {
    db.all("SELECT role, content, timestamp FROM history ORDER BY timestamp DESC LIMIT 100", [], (err, rows) => {
        if (err) return res.status(500).json({ error: err.message });
        res.json(rows);
    });
});
app.get('/api/logs', (req, res) => {
    db.all("SELECT commands_requested, stdout, stderr, timestamp FROM execution_logs ORDER BY timestamp DESC LIMIT 100", [], (err, rows) => {
        if (err) return res.status(500).json({ error: err.message });
        res.json(rows);
    });
});
app.get('/api/chat', (req, res) => {
    db.all("SELECT author, message, timestamp FROM chat ORDER BY timestamp ASC", [], (err, rows) => {
        if (err) return res.status(500).json({ error: err.message });
        res.json(rows);
    });
});
app.post('/api/chat', (req, res) => {
    const { message } = req.body;
    if (!message) {
        return res.status(400).json({ error: 'El mensaje no puede estar vacío.' });
    }
    db.run("INSERT INTO chat (author, message) VALUES (?, ?)", ['Lito', message], function(err) {
        if (err) return res.status(500).json({ error: err.message });
        res.json({ id: this.lastID });
    });
});
app.listen(PORT, '0.0.0.0', () => { 
    console.log(`Servidor de Liberaty v2 escuchando en el puerto ${PORT}`);
    setInterval(() => {
        clients.forEach(client => client.res.write(':heartbeat\n\n'));
    }, 25000);
});

