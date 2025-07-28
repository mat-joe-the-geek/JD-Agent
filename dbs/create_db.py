import os
import sqlite3

DATABASE_PATH = os.path.join(os.path.dirname(__file__), "database.db")


def create_database():
    # Check if the database already exists
    db_exists = os.path.exists(DATABASE_PATH)

    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()

    if not db_exists:
        print(f"Creating new database at {DATABASE_PATH}...")
        # Create candidates table
        cursor.execute(
            """
            CREATE TABLE candidates (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                email TEXT UNIQUE NOT NULL,
                phone TEXT,
                current_role TEXT,
                experience_years INTEGER,
                skills TEXT,
                education TEXT,
                location TEXT,
                linkedin_profile TEXT,
                last_updated TEXT
            )
        """
        )
        print("Created 'candidates' table.")


        # Create Software Development candidates table
        cursor.execute(
            """
            CREATE TABLE software_development_candidates (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                email TEXT UNIQUE NOT NULL,
                phone TEXT,
                current_role TEXT,
                experience_years INTEGER,
                skills TEXT,
                education TEXT,
                location TEXT,
                linkedin_profile TEXT,
                last_updated TEXT
            )
        """
        )
        print("Created 'software_development_candidates' table.")

        # Create IT Services candidates table
        cursor.execute(
            """
            CREATE TABLE it_services_candidates (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                email TEXT UNIQUE NOT NULL,
                phone TEXT,
                current_role TEXT,
                experience_years INTEGER,
                skills TEXT,
                education TEXT,
                location TEXT,
                linkedin_profile TEXT,
                last_updated TEXT
            )
        """
        )
        print("Created 'it_services_candidates' table.")

        # Create Banking candidates table
        cursor.execute(
            """
            CREATE TABLE banking_candidates (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                email TEXT UNIQUE NOT NULL,
                phone TEXT,
                current_role TEXT,
                experience_years INTEGER,
                skills TEXT,
                education TEXT,
                location TEXT,
                linkedin_profile TEXT,
                last_updated TEXT
            )
        """
        )
        print("Created 'banking_candidates' table.")

        # Create Insurance candidates table
        cursor.execute(
            """
            CREATE TABLE insurance_candidates (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                email TEXT UNIQUE NOT NULL,
                phone TEXT,
                current_role TEXT,
                experience_years INTEGER,
                skills TEXT,
                education TEXT,
                location TEXT,
                linkedin_profile TEXT,
                last_updated TEXT
            )
        """
        )
        print("Created 'insurance_candidates' table.")

        # Create Healthcare candidates table
        cursor.execute(
            """
            CREATE TABLE healthcare_candidates (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                email TEXT UNIQUE NOT NULL,
                phone TEXT,
                current_role TEXT,
                experience_years INTEGER,
                skills TEXT,
                education TEXT,
                location TEXT,
                linkedin_profile TEXT,
                last_updated TEXT
            )
        """
        )
        print("Created 'healthcare_candidates' table.")

        # Create Travel candidates table
        cursor.execute(
            """
            CREATE TABLE travel_candidates (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                email TEXT UNIQUE NOT NULL,
                phone TEXT,
                current_role TEXT,
                experience_years INTEGER,
                skills TEXT,
                education TEXT,
                location TEXT,
                linkedin_profile TEXT,
                last_updated TEXT
            )
        """
        )
        print("Created 'travel_candidates' table.")

        # Create Real Estate candidates table
        cursor.execute(
            """
            CREATE TABLE real_estate_candidates (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                email TEXT UNIQUE NOT NULL,
                phone TEXT,
                current_role TEXT,
                experience_years INTEGER,
                skills TEXT,
                education TEXT,
                location TEXT,
                linkedin_profile TEXT,
                last_updated TEXT
            )
        """
        )
        print("Created 'real_estate_candidates' table.")

        # Create todos table
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS todos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                task TEXT NOT NULL,
                completed BOOLEAN NOT NULL DEFAULT 0,
                FOREIGN KEY (user_id) REFERENCES candidates (id)
            )
        """
        )
        print("Created 'todos' table.")


        # Insert dummy candidates
        dummy_candidates_data = [
            (
                "Zoe Smith",
                "zoe.s@example.com",
                "555-2001",
                "Junior Data Analyst",
                1,
                "Excel, SQL, Data Visualization",
                "B.Sc. Data Science",
                "San Diego",
                "linkedin.com/in/zoes",
                "2025-07-22"
            ),
            (
                "Max Johnson",
                "max.j@example.com",
                "555-2002",
                "Marketing Coordinator",
                2,
                "Content Creation, Social Media, SEO, CRM",
                "B.A. Marketing",
                "Portland",
                "linkedin.com/in/maxj",
                "2025-07-22"
            ),
        ]

        cursor.executemany(
            "INSERT INTO candidates (name, email, phone, current_role, experience_years, skills, education, location, linkedin_profile, last_updated) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            dummy_candidates_data
        )
        print(f"Inserted {len(dummy_candidates_data)} dummy candidates.")

        # Insert dummy todos
        dummy_todos = [
            (1, "Buy groceries", 0),
            (1, "Read a book", 1),
            (2, "Finish project report", 0),
            (2, "Go for a run", 0),
            (3, "Plan weekend trip", 1),
        ]
        cursor.executemany(
            "INSERT INTO todos (user_id, task, completed) VALUES (?, ?, ?)", dummy_todos
        )
        print(f"Inserted {len(dummy_todos)} dummy todos.")


        conn.commit()
        print("Database created and populated successfully.")
    else:
        print(f"Database already exists at {DATABASE_PATH}. No changes made.")

    conn.close()


if __name__ == "__main__":
    create_database()