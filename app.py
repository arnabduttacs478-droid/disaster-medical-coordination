from flask import Flask, render_template, request, redirect, url_for
import sqlite3

app = Flask(__name__)

DATABASE = "disaster.db"


# ---------------- DATABASE ----------------

def get_db():
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    return conn


# ---------------- HOME ----------------

@app.route("/")
def home():
    return render_template("index.html")


# ---------------- RESPONDER ----------------

@app.route("/responder")
def responder():
    return render_template("responder.html")


@app.route("/find-hospital", methods=["POST"])
def find_hospital():

    severity = request.form["severity"]
    resource = request.form["resource"]

    conn = get_db()

    # Create emergency
    cursor = conn.execute("""
        INSERT INTO emergencies
        (severity, required_resource, status)
        VALUES (?, ?, 'Active')
    """, (severity, resource))

    emergency_id = cursor.lastrowid

    # Get hospitals
    hospitals = conn.execute("""
        SELECT *
        FROM hospitals
    """).fetchall()

    suitable_hospitals = []

    for hospital in hospitals:

        # Effective available beds
        available = (
            hospital["total_beds"]
            + hospital["temporary_beds"]
            - hospital["occupied_beds"]
            - hospital["incoming_beds"]
        )

        # Hospital must have at least one available bed
        if available <= 0:
            continue

        # Check required resource
        if resource == "ICU Bed" and hospital["icu_beds"] <= 0:
            continue

        if resource == "Ventilator" and hospital["ventilators"] <= 0:
            continue

        if resource == "Emergency Care" and hospital["emergency_care"] <= 0:
            continue

        # Calculate matching score
        score = calculate_score(
            severity,
            available,
            hospital["distance"],
            hospital["incoming_beds"],
            resource,
            hospital
        )

        suitable_hospitals.append({
            "id": hospital["id"],
            "name": hospital["name"],
            "distance": hospital["distance"],
            "available": available,
            "incoming": hospital["incoming_beds"],
            "icu_beds": hospital["icu_beds"],
            "ventilators": hospital["ventilators"],
            "emergency_care": hospital["emergency_care"],
            "score": round(score, 2)
        })

    conn.commit()
    conn.close()

    # Highest score first
    suitable_hospitals.sort(
        key=lambda hospital: hospital["score"],
        reverse=True
    )

    return render_template(
        "results.html",
        hospitals=suitable_hospitals,
        severity=severity,
        resource=resource,
        emergency_id=emergency_id
    )


# ---------------- MATCHING SCORE ----------------

def calculate_score(
    severity,
    available,
    distance,
    incoming,
    resource,
    hospital
):

    # More available capacity = better
    capacity_score = min(available * 5, 30)

    # Closer hospital = better
    distance_score = max(30 - distance * 3, 0)

    # Incoming patients reduce preference
    incoming_penalty = incoming * 2

    # Resource-specific bonus
    resource_score = 0

    if resource == "ICU Bed":
        resource_score = min(hospital["icu_beds"] * 5, 20)

    elif resource == "Ventilator":
        resource_score = min(hospital["ventilators"] * 4, 20)

    elif resource == "Emergency Care":
        resource_score = min(hospital["emergency_care"] * 2, 20)

    elif resource == "General Bed":
        resource_score = 10

    # Critical emergencies get a stronger preference
    # toward capacity and resource availability.
    severity_multiplier = {
        "Critical": 1.25,
        "High": 1.15,
        "Medium": 1.05,
        "Low": 1.0
    }

    multiplier = severity_multiplier.get(severity, 1.0)

    score = (
        (capacity_score + resource_score) * multiplier
        + distance_score
        - incoming_penalty
    )

    return score


# ---------------- HOSPITAL DASHBOARD ----------------

@app.route("/hospital")
def hospital():

    conn = get_db()

    hospitals = conn.execute("""
        SELECT *
        FROM hospitals
        ORDER BY id
    """).fetchall()

    conn.close()

    return render_template(
        "hospital.html",
        hospitals=hospitals
    )


# ---------------- UPDATE HOSPITAL ----------------

@app.route("/hospital/update", methods=["POST"])
def update_hospital():

    hospital_id = request.form["hospital_id"]

    total_beds = int(request.form["total_beds"])
    occupied_beds = int(request.form["occupied_beds"])
    incoming_beds = int(request.form["incoming_beds"])
    temporary_beds = int(request.form["temporary_beds"])

    icu_beds = int(request.form["icu_beds"])
    ventilators = int(request.form["ventilators"])
    emergency_care = int(request.form["emergency_care"])

    conn = get_db()

    conn.execute("""
        UPDATE hospitals
        SET
            total_beds = ?,
            occupied_beds = ?,
            incoming_beds = ?,
            temporary_beds = ?,
            icu_beds = ?,
            ventilators = ?,
            emergency_care = ?
        WHERE id = ?
    """, (
        total_beds,
        occupied_beds,
        incoming_beds,
        temporary_beds,
        icu_beds,
        ventilators,
        emergency_care,
        hospital_id
    ))

    conn.commit()
    conn.close()

    return redirect(url_for("hospital"))


# ---------------- COMMAND CENTER ----------------

@app.route("/command")
def command():

    conn = get_db()

    hospitals = conn.execute("""
        SELECT *
        FROM hospitals
        ORDER BY id
    """).fetchall()

    emergencies = conn.execute("""
        SELECT *
        FROM emergencies
        ORDER BY
            CASE status
                WHEN 'Incoming' THEN 1
                WHEN 'Active' THEN 2
                WHEN 'Admitted' THEN 3
                WHEN 'Cancelled' THEN 4
                ELSE 5
            END,
            CASE severity
                WHEN 'Critical' THEN 1
                WHEN 'High' THEN 2
                WHEN 'Medium' THEN 3
                WHEN 'Low' THEN 4
                ELSE 5
            END,
            id DESC
    """).fetchall()

    conn.close()

    return render_template(
        "command.html",
        hospitals=hospitals,
        emergencies=emergencies
    )


# ---------------- COMMIT PATIENT ----------------

@app.route("/commit/<int:emergency_id>/<int:hospital_id>")
def commit_patient(emergency_id, hospital_id):

    conn = get_db()

    emergency = conn.execute("""
        SELECT *
        FROM emergencies
        WHERE id = ?
    """, (emergency_id,)).fetchone()

    hospital = conn.execute("""
        SELECT *
        FROM hospitals
        WHERE id = ?
    """, (hospital_id,)).fetchone()

    if not emergency or not hospital:

        conn.close()

        return "Emergency or hospital not found.", 404

    # Emergency must still be active
    if emergency["status"] != "Active":

        conn.close()

        return redirect(url_for("command"))

    # Recalculate current availability
    available = (
        hospital["total_beds"]
        + hospital["temporary_beds"]
        - hospital["occupied_beds"]
        - hospital["incoming_beds"]
    )

    if available <= 0:

        conn.close()

        return "No beds currently available. Please search again.", 409

    # Reserve incoming capacity
    conn.execute("""
        UPDATE hospitals
        SET incoming_beds = incoming_beds + 1
        WHERE id = ?
    """, (hospital_id,))

    # Update emergency
    conn.execute("""
        UPDATE emergencies
        SET
            status = 'Incoming',
            matched_hospital_id = ?
        WHERE id = ?
    """, (
        hospital_id,
        emergency_id
    ))

    conn.commit()
    conn.close()

    return redirect(url_for("command"))


# ---------------- ADMIT PATIENT ----------------

@app.route("/admit/<int:emergency_id>/<int:hospital_id>")
def admit_patient(emergency_id, hospital_id):

    conn = get_db()

    hospital = conn.execute("""
        SELECT *
        FROM hospitals
        WHERE id = ?
    """, (hospital_id,)).fetchone()

    emergency = conn.execute("""
        SELECT *
        FROM emergencies
        WHERE id = ?
    """, (emergency_id,)).fetchone()

    if not hospital or not emergency:

        conn.close()

        return "Emergency or hospital not found.", 404

    # Only an incoming patient can be admitted
    if emergency["status"] != "Incoming":

        conn.close()

        return redirect(url_for("command"))

    # There must be an incoming patient to admit
    if hospital["incoming_beds"] <= 0:

        conn.close()

        return "No incoming patient is currently reserved for this hospital.", 409

    # Move patient from Incoming → Occupied
    conn.execute("""
        UPDATE hospitals
        SET
            incoming_beds = incoming_beds - 1,
            occupied_beds = occupied_beds + 1
        WHERE id = ?
    """, (hospital_id,))

    # Update emergency status
    conn.execute("""
        UPDATE emergencies
        SET status = 'Admitted'
        WHERE id = ?
    """, (emergency_id,))

    conn.commit()
    conn.close()

    return redirect(url_for("command"))


# ---------------- CANCEL / REDIRECT ----------------

@app.route("/cancel/<int:emergency_id>/<int:hospital_id>")
def cancel_patient(emergency_id, hospital_id):

    conn = get_db()

    hospital = conn.execute("""
        SELECT *
        FROM hospitals
        WHERE id = ?
    """, (hospital_id,)).fetchone()

    emergency = conn.execute("""
        SELECT *
        FROM emergencies
        WHERE id = ?
    """, (emergency_id,)).fetchone()

    if not hospital or not emergency:

        conn.close()

        return "Emergency or hospital not found.", 404

    # Only incoming patients can be cancelled
    if emergency["status"] != "Incoming":

        conn.close()

        return redirect(url_for("command"))

    # Release the committed incoming capacity
    if hospital["incoming_beds"] > 0:

        conn.execute("""
            UPDATE hospitals
            SET incoming_beds = incoming_beds - 1
            WHERE id = ?
        """, (hospital_id,))

        conn.execute("""
            UPDATE emergencies
            SET status = 'Cancelled'
            WHERE id = ?
        """, (emergency_id,))

        conn.commit()

    conn.close()

    return redirect(url_for("command"))


# ---------------- RUN APPLICATION ----------------

if __name__ == "__main__":
    app.run(debug=True)