from flask import Flask, render_template, jsonify, request, send_file
import json, os, subprocess
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
        subprocess.run(
            ["amixer", "set", "Master", f"{vol}%"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )
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


@app.route("/api/wifi-scan")
def wifi_scan():
    try:
        output = subprocess.check_output(
            ["nmcli", "-t", "-f", "SSID,SIGNAL,SECURITY", "dev", "wifi"],
            text=True
        )

        networks = []
        seen = set()

        for line in output.splitlines():
            parts = line.split(":")
            ssid = parts[0].strip() if len(parts) > 0 else ""
            signal = parts[1].strip() if len(parts) > 1 else ""
            security = parts[2].strip() if len(parts) > 2 else ""

            if ssid and ssid not in seen:
                seen.add(ssid)
                networks.append({
                    "ssid": ssid,
                    "signal": signal,
                    "security": security
                })

        return jsonify({"status": "ok", "networks": networks})

    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route("/api/wifi-connect", methods=["POST"])
def wifi_connect():
    data = request.get_json(silent=True) or {}

    ssid = data.get("ssid", "")
    password = data.get("password", "")

    if not ssid:
        return jsonify({"status": "error", "message": "SSID required"}), 400

    try:
        cmd = ["nmcli", "device", "wifi", "connect", ssid]

        if password:
            cmd += ["password", password]

        output = subprocess.check_output(
            cmd,
            stderr=subprocess.STDOUT,
            text=True
        )

        return jsonify({
            "status": "ok",
            "message": output
        })

    except subprocess.CalledProcessError as e:
        return jsonify({
            "status": "error",
            "message": e.output
        }), 500

    except Exception as e:
        return jsonify({
            "status": "error",
            "message": str(e)
        }), 500


@app.route("/api/bluetooth-status")
def bluetooth_status():
    try:
        output = subprocess.check_output(["bluetoothctl", "show"], text=True)
        powered = "Powered: yes" in output
    except Exception:
        powered = False

    return jsonify({
        "powered": powered,
        "connected_devices": []
    })


@app.route("/api/bluetooth-scan")
def bluetooth_scan():
    try:
        subprocess.run(
            ["bluetoothctl", "power", "on"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )

        subprocess.run(
            ["bluetoothctl", "scan", "on"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=5
        )

        output = subprocess.check_output(["bluetoothctl", "devices"], text=True)

        devices = []

        for line in output.splitlines():
            if line.startswith("Device"):
                parts = line.split(" ", 2)
                if len(parts) >= 3:
                    devices.append({
                        "mac": parts[1],
                        "name": parts[2]
                    })

        return jsonify({"status": "ok", "devices": devices})

    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route("/api/bluetooth-connect", methods=["POST"])
def bluetooth_connect():
    data = request.get_json(silent=True) or {}
    mac = data.get("mac", "")

    if not mac:
        return jsonify({"status": "error", "message": "MAC required"}), 400

    try:
        subprocess.run(["bluetoothctl", "power", "on"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        subprocess.run(["bluetoothctl", "trust", mac], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        subprocess.run(["bluetoothctl", "pair", mac], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=15)
        subprocess.run(["bluetoothctl", "connect", mac], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=15)

        return jsonify({
            "status": "ok",
            "message": "Bluetooth connected"
        })

    except Exception as e:
        return jsonify({
            "status": "error",
            "message": str(e)
        }), 500


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
