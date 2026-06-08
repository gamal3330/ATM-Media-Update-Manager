const express = require("express");
const QRCode = require("qrcode");
const { Client, LocalAuth } = require("whatsapp-web.js");

const PORT = Number(process.env.WHATSAPP_GATEWAY_PORT || 3020);
const HOST = process.env.WHATSAPP_GATEWAY_HOST || "127.0.0.1";
const TOKEN = process.env.WHATSAPP_GATEWAY_TOKEN || "";
const AUTH_PATH = process.env.WHATSAPP_AUTH_PATH || ".wwebjs_auth";
const CLIENT_ID = process.env.WHATSAPP_CLIENT_ID || "qib-atm-manager";
const HEADLESS = String(process.env.WHATSAPP_HEADLESS || "true").toLowerCase() !== "false";
const LOOPBACK_HOSTS = new Set(["127.0.0.1", "localhost", "::1"]);

let status = "starting";
let ready = false;
let latestQr = null;
let latestQrImage = null;
let lastError = null;
let lastReadyAt = null;
let lastDisconnectedAt = null;
let reconnectAttempts = 0;
let nextReconnectAt = null;
let reconnectTimer = null;
let initializing = false;
let client = null;

function statusPayload() {
  return {
    ok: ready,
    ready,
    status,
    qr_available: Boolean(latestQr),
    last_error: lastError,
    last_ready_at: lastReadyAt,
    last_disconnected_at: lastDisconnectedAt,
    reconnect_attempts: reconnectAttempts,
    next_reconnect_at: nextReconnectAt,
  };
}

function requireToken(req, res, next) {
  if (req.path === "/health") {
    next();
    return;
  }
  if (!TOKEN && !LOOPBACK_HOSTS.has(HOST)) {
    res.status(503).json({
      ok: false,
      error: "WHATSAPP_GATEWAY_TOKEN is required when the gateway listens outside localhost",
    });
    return;
  }
  if (!TOKEN) {
    next();
    return;
  }
  const expected = `Bearer ${TOKEN}`;
  if (req.headers.authorization !== expected) {
    res.status(401).json({ ok: false, error: "Invalid WhatsApp gateway token" });
    return;
  }
  next();
}

function normalizeChatId(value) {
  const raw = String(value || "").trim();
  if (!raw) return "";
  if (raw.endsWith("@c.us") || raw.endsWith("@g.us")) return raw;
  const digits = raw.replace(/[+\s()-]/g, "");
  if (!/^\d{8,15}$/.test(digits)) return "";
  return `${digits}@c.us`;
}

function createClient() {
  const nextClient = new Client({
    authStrategy: new LocalAuth({
      clientId: CLIENT_ID,
      dataPath: AUTH_PATH,
    }),
    puppeteer: {
      headless: HEADLESS,
      executablePath: process.env.WHATSAPP_CHROME_PATH || undefined,
      args: ["--no-sandbox", "--disable-setuid-sandbox", "--disable-dev-shm-usage"],
    },
  });

  nextClient.on("qr", async (qr) => {
    status = "qr";
    ready = false;
    latestQr = qr;
    lastError = null;
    try {
      latestQrImage = await QRCode.toDataURL(qr, { width: 320, margin: 2 });
    } catch (error) {
      latestQrImage = null;
      lastError = error.message;
    }
    console.log("WhatsApp QR is ready. Open QIB ATM Manager Notification Center to scan it.");
  });

  nextClient.on("authenticated", () => {
    status = "authenticated";
    lastError = null;
    console.log("WhatsApp session authenticated.");
  });

  nextClient.on("ready", () => {
    status = "ready";
    ready = true;
    latestQr = null;
    latestQrImage = null;
    lastError = null;
    lastReadyAt = new Date().toISOString();
    reconnectAttempts = 0;
    nextReconnectAt = null;
    console.log("WhatsApp gateway is ready.");
  });

  nextClient.on("auth_failure", (message) => {
    status = "auth_failure";
    ready = false;
    lastError = message || "WhatsApp authentication failed";
    console.error(lastError);
    scheduleReconnect("auth_failure");
  });

  nextClient.on("disconnected", (reason) => {
    status = "disconnected";
    ready = false;
    lastDisconnectedAt = new Date().toISOString();
    lastError = reason || "WhatsApp disconnected";
    console.error(`WhatsApp disconnected: ${lastError}`);
    scheduleReconnect("disconnected");
  });

  return nextClient;
}

function scheduleReconnect(reason) {
  if (reconnectTimer) return;
  reconnectAttempts += 1;
  const delayMs = Math.min(60000, 5000 * reconnectAttempts);
  nextReconnectAt = new Date(Date.now() + delayMs).toISOString();
  console.log(`Scheduling WhatsApp reconnect after ${delayMs} ms (${reason}).`);
  reconnectTimer = setTimeout(async () => {
    reconnectTimer = null;
    await initializeClient();
  }, delayMs);
}

async function initializeClient() {
  if (initializing) return;
  initializing = true;
  status = ready ? status : "starting";
  try {
    if (client) {
      try {
        await client.destroy();
      } catch (_error) {
        // The browser may already be closed; recreating the client is enough.
      }
    }
    client = createClient();
    await client.initialize();
  } catch (error) {
    status = "error";
    ready = false;
    lastError = error.message;
    console.error("Failed to initialize WhatsApp gateway:", error);
    scheduleReconnect("initialize_failed");
  } finally {
    initializing = false;
  }
}

initializeClient();

const app = express();
app.use(express.json({ limit: "256kb" }));
app.use(requireToken);

app.get("/health", (_req, res) => {
  res.json({ ok: true, service: "qib-whatsapp-gateway" });
});

app.get("/status", (_req, res) => {
  res.json(statusPayload());
});

app.get("/qr", (_req, res) => {
  res.json({
    ...statusPayload(),
    qr: latestQr,
    qr_image: latestQrImage,
  });
});

app.post("/send", async (req, res) => {
  if (!ready) {
    res.status(409).json({ ok: false, error: "WhatsApp gateway is not ready", ...statusPayload() });
    return;
  }

  const chatId = normalizeChatId(req.body?.to);
  const message = String(req.body?.message || "").trim();
  if (!chatId || !message) {
    res.status(400).json({ ok: false, error: "Recipient and message are required" });
    return;
  }

  try {
    const sent = await client.sendMessage(chatId, message);
    res.json({ ok: true, id: sent.id?._serialized || null, to: chatId });
  } catch (error) {
    lastError = error.message;
    res.status(500).json({ ok: false, error: error.message });
  }
});

app.listen(PORT, HOST, () => {
  console.log(`QIB WhatsApp gateway listening on http://${HOST}:${PORT}`);
  if (!TOKEN && LOOPBACK_HOSTS.has(HOST)) {
    console.warn("WHATSAPP_GATEWAY_TOKEN is not set. Only use this on localhost.");
  }
});

async function shutdown() {
  try {
    if (reconnectTimer) clearTimeout(reconnectTimer);
    if (client) await client.destroy();
  } finally {
    process.exit(0);
  }
}

process.on("SIGINT", shutdown);
process.on("SIGTERM", shutdown);
