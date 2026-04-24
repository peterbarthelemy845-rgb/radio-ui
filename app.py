from flask import Flask, render_template, jsonify, request, send_file
import json, os, subprocess, signal
from io import BytesIO
import qrcode

app = Flask(__name__)

CONFIG_FILE = "config.json"

DEFAULT_PRESET = {
    "name": "La Voix Divine",
    "subtitle": "Internet Stream",
    "url": "http://162.244.81.219:8020/live"
}

STATE = {
    "is_playing": False,
    "station_name": DEFAULT_PRESET["name"],
    "station_subtitle": DEFAULT_PRESET["subtitle"],
    "stream_url": DEFAULT_PRESET["url"],
    "preset_index": 0,
    "volume": 50
}

PLAYER_PROCESS = None


def load_config():
    if not os.path.exists(CONFIG_FILE):
        return {"presets": [DEFAULT_PRESET]}
    try:
        with open(CONFIG_FILE) as f:
            data = json.load(f)
        if not data.get("presets"):
            data["presets"] = [DEFAULT_PRESET]
        return data
    except Exception:
        return {"presets": [DEFAULT_PRESET]}


def save_config(data):
    with open(CONFIG_FILE, "w") as f:
        json.dump(data, f, indent=2)


def stop_player():
    global PLAYER_PROCESS
    if PLAYER_PROCESS and PLAYER_PROCESS.poll() is None:
        try:
            PLAYER_PROCESS.terminate()
            PLAYER_PROCESS.wait(timeout=3)
        except Exception:
            try:
                PLAYER_PROCESS.kill()
            except Exception:
                pass
    PLAYER_PROCESS = None


def start_player(url):
    global PLAYER_PROCESS
    stop_player()

    # Try mpv first, then ffplay as fallback
    commands = [
        ["mpv", "--no-video", "--really-quiet", url],
        ["ffplay", "-nodisp", "-autoexit", "-loglevel", "quiet", url],
    ]

    for cmd in commands:
        try:
            PLAYER_PROCESS = subprocess.Popen(
                cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )
            return True
        except FileNotFoundError:
            continue

    return False


@app.route("/")
def home():
    return render_template("index.html")


@app.route("/api/state")
def state():
    config = load_config()
    return jsonify({
        "playing": {
            "is_playing": STATE["is_playing"],
            "station_name": STATE["station_name"],
            "station_subtitle": STATE["station_subtitle"]
        },
        "station_name": STATE["station_name"],
        "station_subtitle": STATE["station_subtitle"],
        "stream_url": STATE["stream_url"],
        "preset_index": STATE["preset_index"],
        "volume": STATE["volume"],
        "presets": config.get("presets", [DEFAULT_PRESET])
    })


@app.route("/api/play-stream", methods=["POST"])
def play_stream():
    config = load_config()
    data = request.get_json(silent=True) or {}

    presets = config.get("presets", [DEFAULT_PRESET])

    url = data.get("url") or STATE["stream_url"] or presets[0]["url"]
    name = data.get("name") or STATE["station_name"] or presets[0]["name"]
    subtitle = data.get("subtitle") or STATE["station_subtitle"] or presets[0].get("subtitle", "Internet Stream")

    ok = start_player(url)

    if ok:
        STATE["is_playing"] = True
        STATE["station_name"] = name
        STATE["station_subtitle"] = subtitle
        STATE["stream_url"] = url
        return jsonify({"status": "playing"})

    return jsonify({"status": "error", "message": "No audio player found. Install mpv."}), 500


@app.route("/api/stop-stream", methods=["POST"])
def stop_stream():
    stop_player()
    STATE["is_playing"] = False
    return jsonify({"status": "stopped"})


@app.route("/api/volume", methods=["POST"])
def volume():
    data = request.get_json(silent=True) or {}
    vol = int(data.get("volume", 50))
    STATE["volume"] = vol

    try:
        subprocess.run(["amixer", "set", "Master", f"{vol}%"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception:
        pass

    return jsonify({"status": "ok", "volume": vol})


@app.route("/api/network-status")
def network_status():
    return jsonify({
        "connected": True,
        "playing": STATE["is_playing"]
    })


@app.route("/api/wifi-status")
def wifi_status():
    try:
        ssid = subprocess.check_output(["iwgetid", "-r"], text=True).strip()
    except Exception:
        ssid = ""

    return jsonify({
        "connected": bool(ssid),
        "ssid": ssid if ssid else "Not connected",
        "saved_networks": []
    })


@app.route("/api/bluetooth-status")
def bluetooth_status():
    return jsonify({
        "powered": True,
        "connected_devices": []
    })


@app.route("/add_station")
def add_station_page():
    return render_template("add.html")


@app.route("/api/add-station", methods=["POST"])
def add_station():
    config = load_config()

    if request.content_type and "multipart/form-data" in request.content_type:
        name = request.form.get("name", "New Station")
        url = request.form.get("url", "")
        subtitle = request.form.get("subtitle", "Custom Station")
    else:
        data = request.get_json(silent=True) or {}
        name = data.get("name", "New Station")
        url = data.get("url", "")
        subtitle = data.get("subtitle", "Custom Station")

    if not url:
        return jsonify({"status": "error", "message": "Stream URL required"}), 400

    config.setdefault("presets", []).append({
        "name": name,
        "subtitle": subtitle,
        "url": url
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


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
