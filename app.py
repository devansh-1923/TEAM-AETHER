from flask import Flask, jsonify, request, render_template, session
import sqlite3
import os
import uuid
import math
from datetime import datetime
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)

# =========================================================
# CONFIGURATION
# =========================================================

app.secret_key = os.environ.get(
    "FLASK_SECRET_KEY",
    "team-aether-development-key"
)

DATABASE = "aether.db"


# =========================================================
# DATABASE
# =========================================================

def get_db():
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():

    conn = get_db()

    # USERS
    conn.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            email TEXT UNIQUE NOT NULL,
            phone TEXT,
            password TEXT NOT NULL,
            role TEXT NOT NULL
                CHECK(role IN ('customer', 'provider')),
            created_at TEXT NOT NULL
        )
    """)

    # PROVIDERS
    conn.execute("""
        CREATE TABLE IF NOT EXISTS providers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER UNIQUE NOT NULL,
            service_type TEXT NOT NULL,
            latitude REAL,
            longitude REAL,
            available INTEGER DEFAULT 0,
            FOREIGN KEY(user_id)
                REFERENCES users(id)
        )
    """)

    # SERVICE REQUESTS
    conn.execute("""
        CREATE TABLE IF NOT EXISTS service_requests (
            id TEXT PRIMARY KEY,
            customer_id INTEGER NOT NULL,
            provider_id INTEGER,
            service TEXT NOT NULL,
            latitude REAL NOT NULL,
            longitude REAL NOT NULL,
            description TEXT,
            status TEXT NOT NULL,
            created_at TEXT NOT NULL,

            FOREIGN KEY(customer_id)
                REFERENCES users(id),

            FOREIGN KEY(provider_id)
                REFERENCES users(id)
        )
    """)

    conn.commit()
    conn.close()


# =========================================================
# DISTANCE CALCULATION
# =========================================================

def calculate_distance(lat1, lon1, lat2, lon2):

    """
    Calculate distance between two GPS coordinates
    using the Haversine formula.

    Returns distance in kilometers.
    """

    earth_radius = 6371

    lat1 = math.radians(lat1)
    lat2 = math.radians(lat2)

    dlat = lat2 - lat1
    dlon = math.radians(lon2 - lon1)

    a = (
        math.sin(dlat / 2) ** 2
        +
        math.cos(lat1)
        * math.cos(lat2)
        * math.sin(dlon / 2) ** 2
    )

    c = 2 * math.atan2(
        math.sqrt(a),
        math.sqrt(1 - a)
    )

    return earth_radius * c


# =========================================================
# HOME / FRONTEND
# =========================================================

@app.route("/")
def home():

    return render_template("index.html")


# =========================================================
# HEALTH CHECK
# =========================================================

@app.route("/api/health")
def health():

    return jsonify({
        "success": True,
        "status": "online",
        "service": "TEAM AETHER Backend"
    })


# =========================================================
# REGISTER
# =========================================================

@app.route("/api/register", methods=["POST"])
def register():

    data = request.get_json() or {}

    name = data.get("name")
    email = data.get("email")
    phone = data.get("phone")
    password = data.get("password")
    role = data.get("role")

    # Validate basic fields

    if not name or not email or not password:

        return jsonify({
            "success": False,
            "message": "Name, email and password are required"
        }), 400

    # Validate role

    if role not in ["customer", "provider"]:

        return jsonify({
            "success": False,
            "message": "Role must be customer or provider"
        }), 400

    # Provider must provide service

    service_type = data.get("service_type")

    if role == "provider" and not service_type:

        return jsonify({
            "success": False,
            "message": "Provider service_type is required"
        }), 400

    conn = get_db()

    try:

        cursor = conn.execute("""
            INSERT INTO users
            (
                name,
                email,
                phone,
                password,
                role,
                created_at
            )
            VALUES (?, ?, ?, ?, ?, ?)
        """, (
            name,
            email,
            phone,
            generate_password_hash(password),
            role,
            datetime.now().isoformat()
        ))

        user_id = cursor.lastrowid

        # Create provider profile

        if role == "provider":

            conn.execute("""
                INSERT INTO providers
                (
                    user_id,
                    service_type,
                    available
                )
                VALUES (?, ?, ?)
            """, (
                user_id,
                service_type,
                0
            ))

        conn.commit()
        conn.close()

        return jsonify({
            "success": True,
            "message": "Registration successful",
            "user_id": user_id
        })

    except sqlite3.IntegrityError:

        conn.close()

        return jsonify({
            "success": False,
            "message": "Email already registered"
        }), 409


# =========================================================
# LOGIN
# =========================================================

@app.route("/api/login", methods=["POST"])
def login():

    data = request.get_json() or {}

    email = data.get("email")
    password = data.get("password")

    if not email or not password:

        return jsonify({
            "success": False,
            "message": "Email and password are required"
        }), 400

    conn = get_db()

    user = conn.execute("""
        SELECT *
        FROM users
        WHERE email = ?
    """, (email,)).fetchone()

    conn.close()

    if not user:

        return jsonify({
            "success": False,
            "message": "Invalid email or password"
        }), 401

    if not check_password_hash(
        user["password"],
        password
    ):

        return jsonify({
            "success": False,
            "message": "Invalid email or password"
        }), 401

    # Create session

    session["user_id"] = user["id"]
    session["role"] = user["role"]

    return jsonify({
        "success": True,
        "message": "Login successful",

        "user": {
            "id": user["id"],
            "name": user["name"],
            "email": user["email"],
            "phone": user["phone"],
            "role": user["role"]
        }
    })


# =========================================================
# LOGOUT
# =========================================================

@app.route("/api/logout", methods=["POST"])
def logout():

    session.clear()

    return jsonify({
        "success": True,
        "message": "Logged out"
    })


# =========================================================
# CURRENT USER
# =========================================================

@app.route("/api/me")
def current_user():

    if "user_id" not in session:

        return jsonify({
            "logged_in": False
        })

    conn = get_db()

    user = conn.execute("""
        SELECT
            id,
            name,
            email,
            phone,
            role
        FROM users
        WHERE id = ?
    """, (
        session["user_id"],
    )).fetchone()

    conn.close()

    if not user:

        session.clear()

        return jsonify({
            "logged_in": False
        })

    return jsonify({
        "logged_in": True,
        "user": dict(user)
    })


# =========================================================
# PROVIDER AVAILABILITY
# =========================================================

@app.route(
    "/api/provider/availability",
    methods=["PUT"]
)
def update_availability():

    # Only providers

    if (
        "user_id" not in session
        or session.get("role") != "provider"
    ):

        return jsonify({
            "success": False,
            "message": "Provider authentication required"
        }), 403

    data = request.get_json() or {}

    available = data.get("available")

    if available not in [True, False]:

        return jsonify({
            "success": False,
            "message": "available must be true or false"
        }), 400

    conn = get_db()

    conn.execute("""
        UPDATE providers
        SET available = ?
        WHERE user_id = ?
    """, (
        int(available),
        session["user_id"]
    ))

    conn.commit()
    conn.close()

    return jsonify({
        "success": True,
        "available": available
    })


# =========================================================
# PROVIDER LOCATION
# =========================================================

@app.route(
    "/api/provider/location",
    methods=["PUT"]
)
def update_provider_location():

    # Only providers

    if (
        "user_id" not in session
        or session.get("role") != "provider"
    ):

        return jsonify({
            "success": False,
            "message": "Provider authentication required"
        }), 403

    data = request.get_json() or {}

    latitude = data.get("latitude")
    longitude = data.get("longitude")

    if latitude is None or longitude is None:

        return jsonify({
            "success": False,
            "message": "Latitude and longitude are required"
        }), 400

    try:

        latitude = float(latitude)
        longitude = float(longitude)

    except ValueError:

        return jsonify({
            "success": False,
            "message": "Invalid coordinates"
        }), 400

    # Validate GPS range

    if not (-90 <= latitude <= 90):

        return jsonify({
            "success": False,
            "message": "Invalid latitude"
        }), 400

    if not (-180 <= longitude <= 180):

        return jsonify({
            "success": False,
            "message": "Invalid longitude"
        }), 400

    conn = get_db()

    conn.execute("""
        UPDATE providers
        SET
            latitude = ?,
            longitude = ?
        WHERE user_id = ?
    """, (
        latitude,
        longitude,
        session["user_id"]
    ))

    conn.commit()
    conn.close()

    return jsonify({
        "success": True,
        "message": "Location updated",
        "latitude": latitude,
        "longitude": longitude
    })


# =========================================================
# NEARBY PROVIDERS
# =========================================================

@app.route(
    "/api/providers/nearby",
    methods=["GET"]
)
def nearby_providers():

    # Customer only

    if (
        "user_id" not in session
        or session.get("role") != "customer"
    ):

        return jsonify({
            "success": False,
            "message": "Customer authentication required"
        }), 403

    try:

        latitude = float(
            request.args.get("latitude")
        )

        longitude = float(
            request.args.get("longitude")
        )

    except (TypeError, ValueError):

        return jsonify({
            "success": False,
            "message": "Valid latitude and longitude are required"
        }), 400

    service = request.args.get("service")

    if not service:

        return jsonify({
            "success": False,
            "message": "Service is required"
        }), 400

    conn = get_db()

    providers = conn.execute("""
        SELECT
            users.id,
            users.name,
            users.phone,
            providers.service_type,
            providers.latitude,
            providers.longitude,
            providers.available

        FROM users

        JOIN providers
        ON users.id = providers.user_id

        WHERE users.role = 'provider'

        AND providers.available = 1

        AND LOWER(providers.service_type)
            = LOWER(?)

        AND providers.latitude IS NOT NULL

        AND providers.longitude IS NOT NULL
    """, (
        service,
    )).fetchall()

    conn.close()

    results = []

    for provider in providers:

        distance = calculate_distance(
            latitude,
            longitude,
            provider["latitude"],
            provider["longitude"]
        )

        results.append({

            "id": provider["id"],

            "name": provider["name"],

            "phone": provider["phone"],

            "service_type":
                provider["service_type"],

            "latitude":
                provider["latitude"],

            "longitude":
                provider["longitude"],

            "available": True,

            "distance_km":
                round(distance, 2)
        })

    # Closest first

    results.sort(
        key=lambda x: x["distance_km"]
    )

    return jsonify({

        "success": True,

        "count": len(results),

        "providers": results
    })


# =========================================================
# CREATE SERVICE REQUEST
# =========================================================

@app.route(
    "/api/request",
    methods=["POST"]
)
def create_request():

    # Customer only

    if (
        "user_id" not in session
        or session.get("role") != "customer"
    ):

        return jsonify({
            "success": False,
            "message": "Customer authentication required"
        }), 403

    data = request.get_json() or {}

    service = data.get("service")
    latitude = data.get("latitude")
    longitude = data.get("longitude")
    description = data.get("description")

    if (
        not service
        or latitude is None
        or longitude is None
    ):

        return jsonify({
            "success": False,
            "message": "Service and location are required"
        }), 400

    try:

        latitude = float(latitude)
        longitude = float(longitude)

    except ValueError:

        return jsonify({
            "success": False,
            "message": "Invalid coordinates"
        }), 400

    # -----------------------------------------------------
    # FIND CLOSEST AVAILABLE PROVIDER
    # -----------------------------------------------------

    conn = get_db()

    providers = conn.execute("""
        SELECT
            users.id,
            users.name,
            providers.service_type,
            providers.latitude,
            providers.longitude

        FROM users

        JOIN providers
        ON users.id = providers.user_id

        WHERE users.role = 'provider'

        AND providers.available = 1

        AND LOWER(providers.service_type)
            = LOWER(?)

        AND providers.latitude IS NOT NULL

        AND providers.longitude IS NOT NULL
    """, (
        service,
    )).fetchall()

    closest_provider = None
    closest_distance = None

    for provider in providers:

        distance = calculate_distance(
            latitude,
            longitude,
            provider["latitude"],
            provider["longitude"]
        )

        if (
            closest_distance is None
            or distance < closest_distance
        ):

            closest_distance = distance
            closest_provider = provider

    # -----------------------------------------------------
    # CREATE REQUEST
    # -----------------------------------------------------

    request_id = (
        "QF-"
        + uuid.uuid4().hex[:6].upper()
    )

    if closest_provider:

        provider_id = closest_provider["id"]

        status = "Provider Found"

    else:

        provider_id = None

        status = "Finding a Provider"

    conn.execute("""
        INSERT INTO service_requests
        (
            id,
            customer_id,
            provider_id,
            service,
            latitude,
            longitude,
            description,
            status,
            created_at
        )

        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (

        request_id,

        session["user_id"],

        provider_id,

        service,

        latitude,

        longitude,

        description,

        status,

        datetime.now().isoformat()
    ))

    conn.commit()
    conn.close()

    response = {

        "success": True,

        "request_id": request_id,

        "status": status
    }

    if closest_provider:

        response["provider"] = {

            "id":
                closest_provider["id"],

            "name":
                closest_provider["name"],

            "distance_km":
                round(closest_distance, 2)
        }

    return jsonify(response)


# =========================================================
# GET CUSTOMER / PROVIDER REQUESTS
# =========================================================

@app.route("/api/requests")
def get_requests():

    if "user_id" not in session:

        return jsonify({
            "success": False,
            "message": "Login required"
        }), 401

    conn = get_db()

    if session["role"] == "customer":

        rows = conn.execute("""
            SELECT *
            FROM service_requests
            WHERE customer_id = ?
            ORDER BY created_at DESC
        """, (
            session["user_id"],
        )).fetchall()

    else:

        rows = conn.execute("""
            SELECT *
            FROM service_requests
            WHERE provider_id = ?
            ORDER BY created_at DESC
        """, (
            session["user_id"],
        )).fetchall()

    conn.close()

    return jsonify([
        dict(row)
        for row in rows
    ])


# =========================================================
# UPDATE REQUEST STATUS
# =========================================================

@app.route(
    "/api/request/<request_id>/status",
    methods=["PUT"]
)
def update_request_status(request_id):

    if "user_id" not in session:

        return jsonify({
            "success": False,
            "message": "Login required"
        }), 401

    data = request.get_json() or {}

    new_status = data.get("status")

    allowed_statuses = [
        "Accepted",
        "Rejected",
        "On the way",
        "Arrived",
        "Completed",
        "Cancelled"
    ]

    if new_status not in allowed_statuses:

        return jsonify({
            "success": False,
            "message": "Invalid status"
        }), 400

    conn = get_db()

    service_request = conn.execute("""
        SELECT *
        FROM service_requests
        WHERE id = ?
    """, (
        request_id,
    )).fetchone()

    if not service_request:

        conn.close()

        return jsonify({
            "success": False,
            "message": "Request not found"
        }), 404

    # -----------------------------------------------------
    # PROVIDER CAN UPDATE REQUEST
    # -----------------------------------------------------

    if session["role"] == "provider":

        if service_request["provider_id"] != session["user_id"]:

            conn.close()

            return jsonify({
                "success": False,
                "message": "You are not assigned to this request"
            }), 403

    # -----------------------------------------------------
    # CUSTOMER CAN CANCEL
    # -----------------------------------------------------

    elif session["role"] == "customer":

        if service_request["customer_id"] != session["user_id"]:

            conn.close()

            return jsonify({
                "success": False,
                "message": "You do not own this request"
            }), 403

        if new_status != "Cancelled":

            conn.close()

            return jsonify({
                "success": False,
                "message": "Customer can only cancel a request"
            }), 403

    conn.execute("""
        UPDATE service_requests
        SET status = ?
        WHERE id = ?
    """, (
        new_status,
        request_id
    ))

    conn.commit()

    updated_request = conn.execute("""
        SELECT *
        FROM service_requests
        WHERE id = ?
    """, (
        request_id,
    )).fetchone()

    conn.close()

    return jsonify({
        "success": True,
        "request": dict(updated_request)
    })


# =========================================================
# START APPLICATION
# =========================================================

init_db()

if __name__ == "__main__":

    app.run(
        host="0.0.0.0",
        port=5000,
        debug=True
    )