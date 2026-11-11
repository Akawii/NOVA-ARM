const WebSocket = require("ws");
const osc = require("osc");

// ---------------- WebSocket Server ----------------
const wss = new WebSocket.Server({ port: 9000 });

console.log("WebSocket server running on ws://localhost:9000");

// ---------------- OSC UDP ----------------
const udpPort = new osc.UDPPort({
    localAddress: "0.0.0.0",
    localPort: 57121,

    remoteAddress: "127.0.0.1",
    remotePort: 7000
});

udpPort.open();

console.log("OSC sending to TouchDesigner on port 7000");

// ---------------- Helpers ----------------
function buildOSCArg(value) {

    // integers
    if (Number.isInteger(value)) {
        return {
            type: "i",
            value: value
        };
    }

    // floats
    if (typeof value === "number") {
        return {
            type: "f",
            value: value
        };
    }

    // booleans
    if (typeof value === "boolean") {
        return {
            type: "i",
            value: value ? 1 : 0
        };
    }

    // strings
    return {
        type: "s",
        value: String(value)
    };
}

// ---------------- Bridge ----------------
wss.on("connection", (ws) => {

    console.log("Browser connected");

    ws.on("message", (msg) => {

        try {

            const data = JSON.parse(msg);

            console.log("RAW MESSAGE:", data);

            // Safety
            if (!data.address) {
                console.error("Missing OSC address");
                return;
            }

            let oscArgs = [];

            // ---------------- Modern format ----------------
            // {
            //   address: "/test",
            //   args: ["hello"]
            // }

            if (Array.isArray(data.args)) {

                oscArgs = data.args.map(arg => buildOSCArg(arg));

            }

            // ---------------- Legacy format ----------------
            // {
            //   address: "/test",
            //   value: 1
            // }

            else if (data.value !== undefined) {

                oscArgs = [buildOSCArg(data.value)];

            }

            // ---------------- Fallback ----------------
            else {

                console.error("No OSC args found");
                return;

            }

            const packet = {
                address: data.address,
                args: oscArgs
            };

            console.log("SENDING OSC:", packet);

            udpPort.send(packet);

        } catch (e) {

            console.error("Bad message:", e);

        }
    });

    ws.on("close", () => {

        console.log("Browser disconnected");

    });
});