from datetime import datetime, date

from flask_sqlalchemy import SQLAlchemy


db = SQLAlchemy()


class Student(db.Model):
    __tablename__ = "students"

    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.String(64), unique=True, nullable=False)
    name = db.Column(db.String(128), nullable=False)
    email = db.Column(db.String(128), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    embeddings = db.relationship("FaceEmbedding", back_populates="student", cascade="all, delete-orphan")
    attendance_logs = db.relationship("AttendanceLog", back_populates="student", cascade="all, delete-orphan")


class FaceEmbedding(db.Model):
    __tablename__ = "face_embeddings"

    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey("students.id"), nullable=False)
    embedding = db.Column(db.Text, nullable=False)
    image_path = db.Column(db.String(256), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    student = db.relationship("Student", back_populates="embeddings")


class AttendanceLog(db.Model):
    __tablename__ = "attendance_logs"

    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey("students.id"), nullable=False)
    date = db.Column(db.Date, nullable=False, default=date.today)
    time = db.Column(db.Time, nullable=False, default=lambda: datetime.utcnow().time())
    status = db.Column(db.String(16), nullable=False)
    image_path = db.Column(db.String(256), nullable=True)

    student = db.relationship("Student", back_populates="attendance_logs")


class NotificationConfig(db.Model):
    __tablename__ = "notification_config"

    id = db.Column(db.Integer, primary_key=True)
    smtp_server = db.Column(db.String(128), nullable=True)
    smtp_port = db.Column(db.Integer, nullable=True)
    smtp_username = db.Column(db.String(128), nullable=True)
    smtp_password = db.Column(db.String(256), nullable=True)
    use_tls = db.Column(db.Boolean, default=True)
    from_email = db.Column(db.String(128), nullable=True)
    auto_email_enabled = db.Column(db.Boolean, default=False)
