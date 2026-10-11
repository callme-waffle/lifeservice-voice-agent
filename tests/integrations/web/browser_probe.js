/* VOIC-FEAT-001 M6-S2, PRD-01/06 and SRS-W01/W02/W03 browser boundary. */
"use strict";

const fs = require("fs");
const http = require("http");
const WebSocket = require("ws");

function getJson(url) {
  return new Promise((resolve, reject) => {
    http.get(url, response => {
      let body = "";
      response.on("data", chunk => { body += chunk; });
      response.on("end", () => {
        try { resolve(JSON.parse(body)); } catch (error) { reject(error); }
      });
    }).on("error", reject);
  });
}

async function main() {
  const pages = await getJson("http://127.0.0.1:19222/json/list");
  const page = pages.find(item => item.type === "page");
  if (!page) throw new Error("Chrome page unavailable");
  const cdp = new WebSocket(page.webSocketDebuggerUrl);
  const pending = new Map();
  let nextId = 1;
  cdp.on("message", data => {
    const message = JSON.parse(data.toString());
    if (!message.id) return;
    const waiter = pending.get(message.id);
    if (!waiter) return;
    pending.delete(message.id);
    if (message.error) waiter.reject(new Error(message.error.message));
    else if (message.result?.exceptionDetails) waiter.reject(new Error("browser evaluation failed"));
    else waiter.resolve(message.result?.result?.value);
  });
  await new Promise((resolve, reject) => {
    cdp.once("open", resolve);
    cdp.once("error", reject);
  });
  function evaluate(expression) {
    return new Promise((resolve, reject) => {
      const id = nextId++;
      pending.set(id, { resolve, reject });
      cdp.send(JSON.stringify({ id, method: "Runtime.evaluate", params: {
        expression, awaitPromise: true, returnByValue: true,
      } }));
    });
  }

  const token = process.env.VOICE_AGENT_WEB_ACCESS_TOKEN;
  if (!token) throw new Error("missing runtime token");
  const url = "ws://127.0.0.1:18000/voice";
  const rejected = await evaluate(`new Promise(resolve => {
    const ws = new WebSocket(${JSON.stringify(url)}, ["voice-agent", "token.invalid"]);
    let opened = false;
    ws.onopen = () => { opened = true; ws.close(); };
    ws.onerror = () => {};
    ws.onclose = () => resolve(!opened);
    setTimeout(() => { ws.close(); resolve(false); }, 5000);
  })`);

  const pcm = fs.readFileSync(process.argv[2]);
  const frames = [];
  for (let offset = 0, sequence = 0; offset < pcm.length; offset += 32000, sequence++) {
    const part = pcm.subarray(offset, offset + 32000);
    const frame = Buffer.alloc(4 + part.length);
    frame.writeUInt32BE(sequence, 0);
    part.copy(frame, 4);
    frames.push(frame.toString("base64"));
  }
  const result = await evaluate(`new Promise(resolve => {
    const startedAt = performance.now();
    const ws = new WebSocket(${JSON.stringify(url)}, ["voice-agent", ${JSON.stringify(`token.${token}`)}]);
    ws.binaryType = "arraybuffer";
    const frames = ${JSON.stringify(frames)};
    const report = { opened: false, sessionMatch: true, statuses: [], transcripts: 0,
      taskResults: 0, audioChunks: 0, audioBytes: 0, audioContiguous: true,
      inputChunks: frames.length, timesMs: {}, closeCode: null };
    let sessionId = null;
    let audioSequence = 0;
    ws.onopen = () => { report.opened = true; ws.send(JSON.stringify({type:"start"})); };
    ws.onerror = () => {};
    ws.onmessage = event => {
      if (typeof event.data !== "string") {
        const view = new DataView(event.data);
        if (view.getUint32(0) !== audioSequence++) report.audioContiguous = false;
        report.audioChunks++;
        report.audioBytes += event.data.byteLength - 4;
        report.timesMs.firstAudio ??= Math.round(performance.now() - startedAt);
        return;
      }
      const data = JSON.parse(event.data);
      if (data.type === "started") {
        sessionId = data.session_id;
        for (const encoded of frames) {
          const binary = atob(encoded);
          const bytes = new Uint8Array(binary.length);
          for (let index = 0; index < binary.length; index++) bytes[index] = binary.charCodeAt(index);
          ws.send(bytes);
        }
        ws.send(JSON.stringify({type:"end"}));
        report.timesMs.inputEnd = Math.round(performance.now() - startedAt);
      } else if (data.type === "event") {
        const item = data.event;
        if (item.session_id !== sessionId) report.sessionMatch = false;
        const payload = item.payload;
        if (payload.status) report.statuses.push(payload.status);
        if (payload.is_final === true) {
          report.transcripts++;
          report.timesMs.finalTranscript = Math.round(performance.now() - startedAt);
        } else if (typeof payload.text === "string") {
          report.taskResults++;
          report.timesMs.taskResult = Math.round(performance.now() - startedAt);
        }
      }
    };
    ws.onclose = event => {
      report.closeCode = event.code;
      report.timesMs.total = Math.round(performance.now() - startedAt);
      resolve(report);
    };
    setTimeout(() => { ws.close(); resolve(report); }, 180000);
  })`);

  async function cancelledSession() {
    return evaluate(`new Promise(resolve => {
      const ws = new WebSocket(${JSON.stringify(url)}, ["voice-agent", ${JSON.stringify(`token.${token}`)}]);
      const statuses = [];
      let started = false;
      ws.onopen = () => ws.send(JSON.stringify({type:"start"}));
      ws.onerror = () => {};
      ws.onmessage = event => {
        const data = JSON.parse(event.data);
        if (data.type === "started") { started = true; ws.send(JSON.stringify({type:"cancel"})); }
        if (data.type === "event" && data.event.payload.status) statuses.push(data.event.payload.status);
      };
      ws.onclose = () => resolve({started, statuses});
      setTimeout(() => { ws.close(); resolve({started:false, statuses}); }, 5000);
    })`);
  }
  const afterCancel = await cancelledSession();
  const nextSession = await cancelledSession();
  cdp.close();
  process.stdout.write(JSON.stringify({ rejected, result, afterCancel, nextSession }) + "\n");
}

main().catch(error => {
  process.stderr.write(`browser probe failed: ${error.message}\n`);
  process.exitCode = 1;
});
