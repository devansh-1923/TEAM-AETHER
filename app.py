from flask import Flask, jsonify, request, render_template
import json
import os
import uuid
from datetime import datetime

app = Flask(__name__)

REQUESTS_FILE = "requests.json"


def load_requests():
    if not os.path.exists(REQUESTS_FILE):
        return []

    try:
        with open(REQUESTS_FILE, "r") as file:
            return json.load(file)
    except:
        return []


def save_requests(data):
    with open(REQUESTS_FILE, "w") as file:
        json.dump(data, file, indent=4)


@app.route("/")
def home():
    return render_template("index.html")


@app.route("/api/health")
def health():
    return jsonify({
        "status": "online",
        "service": "QuickFixer Backend"
    })


@app.route("/api/request", methods=["POST"])
def create_request():

    data = request.get_json() or {}

    requests = load_requests()

    new_request = {
        "id": "QF-" + uuid.uuid4().hex[:6].upper(),
        "name": data.get("name"),
        "phone": data.get("phone"),
        "service": data.get("service"),
        "location": data.get("location"),
        "description": data.get("description"),
        "status": "Finding a Fixer",
        "created_at": datetime.now().strftime("%d-%m-%Y %H:%M")
    }

    requests.append(new_request)
    save_requests(requests)

    return jsonify({
        "success": True,
        "request": new_request
    })


@app.route("/api/requests")
def get_requests():
    return jsonify(load_requests())


@app.route("/api/request/<request_id>/status", methods=["PUT"])
def update_status(request_id):

    data = request.get_json() or {}
    new_status = data.get("status")

    requests = load_requests()

    for item in requests:
        if item["id"] == request_id:
            item["status"] = new_status
            save_requests(requests)

            return jsonify({
                "success": True,
                "request": item
            })

    return jsonify({
        "success": False,
        "message": "Request not found"
    }), 404


if __name__ == "__main__":
    app.run(debug=True)