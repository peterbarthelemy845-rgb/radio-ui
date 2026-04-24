from flask import Flask, render_template, jsonify, request, send_file
import json, os
from io import BytesIO
import qrcode

app = Flask(__name__)
CONFIG_FILE = "config.json"

STATE = {
    "playing": False,
    "station_name": "La Voix Divine",
    "station_subtitle": "Internet Stream",
    "stream_url": "http://162.244.81.219:8020/live"
}

def load_config():
    if not os.path.exists(CONFIG_FILE):
        return {"presets": []}
    with open(CONFIG_FILE) as f:
        return json.load(f)

def save_config(data):
    with open(CONFIG_FILE, "w") as f:
        json.dump(data, f, indent=2)

@app.route("/")
def home():
    return render_template("index.html")

@app.route("/api/state")
def state():
    config = load_config()

    presets = config.get("presets", [])

    if not presets:
        presets = [{
            "name": "La Voix Divine",
            "subtitle": "Internet Stream",
            "url": "http://162.244.81.219:8020/live"
        }]

    return jsonify({
        "playing": {
            "is_playing": STATE["playing"],
            "station_name": STATE["station_name"],
            "station_subtitle": STATE["station_subtitle"]
        },
        "station_name": STATE["station_name"],
        "station_subtitle": STATE["station_subtitle"],
        "stream_url": STATE["stream_url"],
        "preset_index": 0,
        "volume": 50,
        "presets": presets
    })

@app.route("/api/play-stream", methods=["POST"])
def play_stream():
    STATE["playing"] = True
    return jsonify({"status": "playing"})

@app.route("/api/stop-stream", methods=["POST"])
def stop_stream():
    STATE["playing"] = False
    return jsonify({"status": "stopped"})

@app.route("/api/skip-next", methods=["POST"])
def skip_next():
    return jsonify({"status": "ok"})

@app.route("/api/skip-prev", methods=["POST"])
def skip_prev():
    return jsonify({"status": "ok"})

@app.route("/api/volume", methods=["POST"])
def volume():
    return jsonify({"status": "ok"})

@app.route("/add_station")
def add_station_page():
    return render_template("add.html")

@app.route("/api/add-station", methods=["POST"])
def add_station():
    config = load_config()
    data = request.json or {}

    config.setdefault("presets", []).append({
        "name": data.get("name", "New Station"),
        "url": data.get("url", ""),
        "subtitle": "Custom"
    })

    save_config(config)
    return jsonify({"status": "ok"})

@app.route("/qr")
def qr():
    url = f"http://{request.host}/add_station"
    img = qrcode.make(url)
    buf = BytesIO()
    img.save(buf)
    buf.seek(0)
    return send_file(buf, mimetype="image/png")

@app.route("/api/network-status")
def network_status():
    return jsonify({"connected": True})

@app.route("/api/wifi-status")
def wifi_status():
    return jsonify({
        "connected": True,
        "ssid": "Public_Access",
        "saved_networks": []
    })

@app.route("/api/bluetooth-status")
def bluetooth_status():
    return jsonify({
        "powered": True,
        "connected_devices": []
    })

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
