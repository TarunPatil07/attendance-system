import os
import datetime as dt
import time
from typing import Dict, List, Tuple, Optional

import numpy as np
from flask import Flask, jsonify, redirect, render_template, request, url_for, send_file
from werkzeug.utils import secure_filename

import pandas as pd
from email.mime.text import MIMEText
import smtplib

from config import Config
from face_recognition import (
    FaceRecognitionService,
    cosine_similarity,
    deserialize_embedding,
    serialize_embedding,
)
from models import AttendanceLog, FaceEmbedding, NotificationConfig, Student, db

face_service = FaceRecognitionService()


def create_app() -> Flask:
    app = Flask(__name__)
    app.config.from_object(Config)
    db.init_app(app)

    # Ensure upload directories exist
    upload_base = app.config.get(
        "UPLOAD_FOLDER", os.path.join(app.root_path, "static", "uploads")
    )
    student_dir = os.path.join(upload_base, "students")
    group_dir = os.path.join(upload_base, "groups")
    os.makedirs(student_dir, exist_ok=True)
    os.makedirs(group_dir, exist_ok=True)

    with app.app_context():
        db.create_all()
        # Ensure NotificationConfig exists
        if not NotificationConfig.query.first():
            cfg = NotificationConfig(
                smtp_server="smtp.gmail.com",
                smtp_port=587,
                smtp_username="tvpatil9100@gmail.com",
                smtp_password="qgcn otzj ovnr uzrw",
                use_tls=True,
                from_email="tvpatil9100@gmail.com",
                auto_email_enabled=True
            )
            db.session.add(cfg)
            db.session.commit()

    # ----------------- Helper Functions -----------------
    def _get_or_create_student(student_id: str, name: str, email: Optional[str]) -> Student:
        student = Student.query.filter_by(student_id=student_id).first()
        if not student:
            student = Student(student_id=student_id, name=name, email=email)
            db.session.add(student)
            db.session.commit()
        else:
            student.name = name
            student.email = email
            db.session.commit()
        return student

    def _save_image(bytes_data: bytes, subfolder: str, filename_hint: str) -> str:
        folder = os.path.join(upload_base, subfolder)
        os.makedirs(folder, exist_ok=True)
        safe_name = secure_filename(filename_hint) or f"image_{int(time.time())}.png"
        path = os.path.join(folder, safe_name)
        with open(path, "wb") as f:
            f.write(bytes_data)
        return os.path.relpath(path, app.root_path).replace("\\", "/")

    def _build_attendance_summary(present_students: Dict[int, Tuple[Student, str]], date_obj: dt.date):
        all_students = Student.query.all()
        present_list, absent_list = [], []
        now_str = dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        present_ids = set(present_students.keys())

        for sid, (student, image_path) in present_students.items():
            present_list.append({
                "name": student.name,
                "student_id": student.student_id,
                "timestamp": now_str,
                "image_path": image_path,
            })

        for student in all_students:
            if student.id not in present_ids:
                absent_list.append({
                    "name": student.name,
                    "student_id": student.student_id,
                    "timestamp": now_str
                })

        return {"present": present_list, "absent": absent_list}

    def _match_group_embeddings(group_embeddings: List[np.ndarray], image_rel_path: str, date_obj: dt.date):
        if not group_embeddings:
            return {"present": [], "absent": []}

        all_embeddings = FaceEmbedding.query.join(Student).all()
        known: List[Tuple[Student, np.ndarray]] = [
            (fe.student, deserialize_embedding(fe.embedding))
            for fe in all_embeddings if deserialize_embedding(fe.embedding).size > 0
        ]

        present_students: Dict[int, Tuple[Student, str]] = {}
        similarity_threshold = 0.35
        today = dt.date.today()

        for g_emb in group_embeddings:
            best_student = None
            best_score = -1.0
            for student, known_vec in known:
                score = cosine_similarity(g_emb, known_vec)
                if score > best_score:
                    best_score = score
                    best_student = student
            if best_student and best_score >= similarity_threshold:
                present_students[best_student.id] = (best_student, image_rel_path)

        for student in Student.query.all():
            status = "present" if student.id in present_students else "absent"
            log = AttendanceLog(
                student_id=student.id,
                date=today,
                status=status,
                image_path=image_rel_path if status == "present" else None,
            )
            db.session.add(log)
        db.session.commit()
        return _build_attendance_summary(present_students, date_obj)

    # ----------------- Routes -----------------
    @app.route("/")
    def home():
        return render_template("home.html")

    @app.route("/login", methods=["GET", "POST"])
    def login():
        if request.method == "POST":
            username = request.form.get("username")
            password = request.form.get("password")
            if username == "sit" and password == "ise":
                return redirect(url_for("dashboard"))
            else:
                return render_template("login.html", error="Invalid username or password")
        return render_template("login.html")

    @app.route("/dashboard")
    def dashboard():
        return render_template("dashboard.html")

    # --------------- STUDENT REGISTRATION ---------------
    @app.route("/api/students/register/upload", methods=["POST"])
    def register_student_upload():
        try:
            student_id = request.form.get("student_id")
            name = request.form.get("name")
            email = request.form.get("email")
            files = request.files.getlist("images")

            if not student_id or not name or not files:
                return jsonify({"success": False, "message": "Missing required fields."}), 400

            student = _get_or_create_student(student_id, name, email)
            saved_count = 0

            for file in files:
                if not file or not file.filename:
                    continue
                filename = f"{student_id}_{int(time.time())}_{file.filename}"
                image_bytes = file.read()
                try:
                    embeddings = face_service.embeddings_from_bytes(image_bytes)
                except Exception as exc:
                    return jsonify({"success": False, "message": f"Face detection failed: {exc}"}), 500

                if not embeddings:
                    continue

                rel_path = _save_image(image_bytes, "students", filename)
                for emb in embeddings:
                    fe = FaceEmbedding(student=student, embedding=serialize_embedding(emb), image_path=rel_path)
                    db.session.add(fe)
                    saved_count += 1

            db.session.commit()
            if saved_count == 0:
                return jsonify({"success": False, "message": "No faces detected."}), 400
            return jsonify({"success": True, "message": "Student registered.", "embeddings_saved": saved_count})
        except Exception as exc:
            return jsonify({"success": False, "message": str(exc)}), 500

    # --------------- STUDENT REGISTRATION VIA WEBCAM ---------------
    @app.route("/api/students/register/webcam", methods=["POST"])
    def register_student_webcam():
        try:
            data = request.get_json(silent=True) or {}
            student_id = data.get("student_id")
            name = data.get("name")
            email = data.get("email")
            image_data = data.get("imageData")  # base64 image from webcam

            if not student_id or not name or not image_data:
                return jsonify({"success": False, "message": "Missing required fields."}), 400

            student = _get_or_create_student(student_id, name, email)
            image_bytes, embeddings = face_service.embeddings_from_base64(image_data)

            if not embeddings:
                return jsonify({"success": False, "message": "No faces detected."}), 400

            filename = f"{student_id}_{int(time.time())}_webcam.png"
            rel_path = _save_image(image_bytes, "students", filename)

            saved_count = 0
            for emb in embeddings:
                fe = FaceEmbedding(student=student, embedding=serialize_embedding(emb), image_path=rel_path)
                db.session.add(fe)
                saved_count += 1

            db.session.commit()
            return jsonify({"success": True, "message": "Student registered via webcam.", "embeddings_saved": saved_count})
        except Exception as exc:
            return jsonify({"success": False, "message": str(exc)}), 500

    # --------------- GROUP ATTENDANCE ---------------
    @app.route("/api/attendance/upload", methods=["POST"])
    def attendance_upload():
        try:
            file = request.files.get("group_image")
            if not file:
                return jsonify({"success": False, "message": "No image uploaded."}), 400

            filename = f"group_{int(time.time())}_{file.filename}"
            image_bytes = file.read()
            embeddings = face_service.embeddings_from_bytes(image_bytes)

            rel_path = _save_image(image_bytes, "groups", filename)
            today = dt.date.today()
            summary = _match_group_embeddings(embeddings, rel_path, today)
            return jsonify({"success": True, "summary": summary})
        except Exception as exc:
            return jsonify({"success": False, "message": str(exc)}), 500

    # --------------- WEBCAM ATTENDANCE ---------------
    @app.route("/api/attendance/webcam", methods=["POST"])
    def attendance_webcam():
        try:
            data = request.get_json(silent=True) or {}
            image_data = data.get("imageData")
            if not image_data:
                return jsonify({"success": False, "message": "No image data."}), 400

            image_bytes, embeddings = face_service.embeddings_from_base64(image_data)
            filename = f"group_{int(time.time())}_webcam.png"
            rel_path = _save_image(image_bytes, "groups", filename)
            today = dt.date.today()
            summary = _match_group_embeddings(embeddings, rel_path, today)
            return jsonify({"success": True, "summary": summary})
        except Exception as exc:
            return jsonify({"success": False, "message": str(exc)}), 500

    # ----------------- EXCEL ATTENDANCE EXPORT -----------------
    @app.route("/api/attendance/export/<date_str>", methods=["GET"])
    def export_attendance(date_str):
        try:
            target_date = dt.date.fromisoformat(date_str)
            logs = AttendanceLog.query.join(Student).filter(
                AttendanceLog.date == target_date
            ).all()

            if not logs:
                return jsonify({"success": False, "message": "No attendance records found."}), 404

            present_data = []
            absent_data = []

            for log in logs:
                student = log.student
                row = {
                    "Student ID": student.student_id,
                    "Name": student.name,
                    "Timestamp": log.date.strftime("%Y-%m-%d")
                }
                if log.status == "present":
                    present_data.append(row)
                else:
                    absent_data.append(row)

            file_path = f"attendance_{date_str}.xlsx"
            with pd.ExcelWriter(file_path, engine="openpyxl") as writer:
                pd.DataFrame(present_data).to_excel(writer, index=False, sheet_name="Present")
                pd.DataFrame(absent_data).to_excel(writer, index=False, sheet_name="Absent")

            return send_file(file_path, as_attachment=True, mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
        except Exception as exc:
            return jsonify({"success": False, "message": str(exc)}), 500

    # ----------------- SMTP NOTIFICATIONS -----------------
    @app.route("/api/notifications/send_absent", methods=["POST"])
    def send_absent_notifications():
        try:
            data = request.get_json(silent=True) or {}
            date_str = data.get("date")
            target_date = dt.date.today()
            if date_str:
                target_date = dt.date.fromisoformat(date_str)

            cfg = NotificationConfig.query.first()
            if not cfg or not cfg.smtp_server:
                return jsonify({"success": False, "message": "SMTP is not configured."}), 400

            absences = AttendanceLog.query.join(Student).filter(
                AttendanceLog.date == target_date,
                AttendanceLog.status == "absent"
            ).all()

            if not absences:
                return jsonify({"success": True, "message": "No absentees today."})

            sent_count = 0
            errors = []

            with smtplib.SMTP(cfg.smtp_server, cfg.smtp_port, timeout=10) as server:
                if cfg.use_tls:
                    server.starttls()
                if cfg.smtp_username and cfg.smtp_password:
                    server.login(cfg.smtp_username, cfg.smtp_password)

                for log in absences:
                    student = log.student
                    if not student.email:
                        continue

                    body = (
                        f"Dear {student.name},\n\n"
                        f"You were marked ABSENT on {log.date.strftime('%Y-%m-%d')}.\n"
                        f"If this is incorrect, please contact your instructor.\n\n"
                        f"Regards,\nSmart Attendance System"
                    )
                    msg = MIMEText(body)
                    msg["Subject"] = "Absence Alert - Smart Attendance System"
                    msg["From"] = cfg.from_email or cfg.smtp_username
                    msg["To"] = student.email

                    try:
                        server.send_message(msg)
                        sent_count += 1
                    except Exception as exc:
                        errors.append(f"Failed for {student.email}: {exc}")

            return jsonify({"success": True, "message": f"Sent {sent_count} absentee emails.", "errors": errors})
        except Exception as exc:
            return jsonify({"success": False, "message": str(exc)}), 500

    # ----------------- NOTIFICATION CONFIG -----------------
    @app.route("/api/notifications/config", methods=["GET"])
    def get_notify_config():
        try:
            cfg = NotificationConfig.query.first()
            if not cfg:
                return jsonify({})
            return jsonify({
                "smtp_server": cfg.smtp_server,
                "smtp_port": cfg.smtp_port,
                "smtp_username": cfg.smtp_username,
                "smtp_password": cfg.smtp_password,
                "from_email": cfg.from_email,
                "use_tls": cfg.use_tls,
                "auto_email_enabled": cfg.auto_email_enabled
            })
        except Exception as exc:
            return jsonify({"success": False, "message": str(exc)}), 500

    @app.route("/api/notifications/save", methods=["POST"])
    def save_notify_config():
        try:
            data = request.form or {}
            cfg = NotificationConfig.query.first()
            if not cfg:
                cfg = NotificationConfig()
                db.session.add(cfg)

            cfg.smtp_server = data.get("smtp_server")
            cfg.smtp_port = int(data.get("smtp_port") or 0)
            cfg.smtp_username = data.get("smtp_username")
            cfg.smtp_password = data.get("smtp_password")
            cfg.from_email = data.get("from_email")
            cfg.use_tls = data.get("use_tls") == "true"
            cfg.auto_email_enabled = data.get("auto_email_enabled") == "true"

            db.session.commit()
            return jsonify({"success": True, "message": "Notification settings saved."})
        except Exception as exc:
            return jsonify({"success": False, "message": str(exc)}), 500

    return app


if __name__ == "__main__":
    application = create_app()
    application.run(debug=True)



#-----    (facerec) C:\Users\sudee\Downloads\FACE-REC>python app.py -----------#