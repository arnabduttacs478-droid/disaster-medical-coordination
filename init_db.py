import sqlite3

DATABASE = "disaster.db"

conn = sqlite3.connect(DATABASE)

cursor = conn.cursor()


# ---------------- RESET DATABASE ----------------

cursor.execute("DROP TABLE IF EXISTS emergencies")
cursor.execute("DROP TABLE IF EXISTS hospitals")


# ---------------- HOSPITALS TABLE ----------------

cursor.execute("""
CREATE TABLE hospitals (

    id INTEGER PRIMARY KEY AUTOINCREMENT,

    name TEXT NOT NULL,

    distance REAL NOT NULL,

    total_beds INTEGER NOT NULL,

    occupied_beds INTEGER NOT NULL,

    incoming_beds INTEGER NOT NULL,

    temporary_beds INTEGER NOT NULL,

    icu_beds INTEGER NOT NULL,

    ventilators INTEGER NOT NULL,

    emergency_care INTEGER NOT NULL

)
""")


# ---------------- EMERGENCIES TABLE ----------------

cursor.execute("""
CREATE TABLE emergencies (

    id INTEGER PRIMARY KEY AUTOINCREMENT,

    severity TEXT NOT NULL,

    required_resource TEXT NOT NULL,

    status TEXT NOT NULL,

    matched_hospital_id INTEGER

)
""")


# ---------------- INITIAL HOSPITAL DATA ----------------

cursor.execute("""
INSERT INTO hospitals
(
    name,
    distance,
    total_beds,
    occupied_beds,
    incoming_beds,
    temporary_beds,
    icu_beds,
    ventilators,
    emergency_care
)
VALUES
(
    'City General Hospital',
    3.2,
    30,
    18,
    2,
    5,
    4,
    3,
    10
),
(
    'Metro Care Hospital',
    5.1,
    40,
    20,
    1,
    10,
    2,
    5,
    15
),
(
    'LifeLine Medical Center',
    2.4,
    20,
    15,
    0,
    4,
    0,
    1,
    8
)
""")


conn.commit()
conn.close()

print("Database initialized successfully.")