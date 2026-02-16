from flask import Flask, render_template, request, redirect, url_for, flash, session, jsonify
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from datetime import datetime, timedelta
import os, secrets, requests, random, string, smtplib
from urllib.parse import quote_plus
import pymysql
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import re
import uuid
import json 
pymysql.install_as_MySQLdb()

app = Flask(__name__)
app.secret_key = "student_app_secret_key_12345"
DB_USER = "root"
DB_PASSWORD = quote_plus("pankaj1412@2711")
DB_HOST = "TOMAR-PC"
DB_NAME = "wastemanagementmain"

app.config["SQLALCHEMY_DATABASE_URI"] = (
    f"mysql+pymysql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}/{DB_NAME}?charset=utf8mb4"
)
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

db = SQLAlchemy(app)

BASE_DIR = os.path.abspath(os.path.dirname(__file__))
UPLOAD_FOLDER = os.path.join(BASE_DIR, "static/uploads")
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER
 
SMTP_SERVER = "smtp.gmail.com"  
SMTP_PORT = 587
SMTP_USERNAME = "greenmatrixsmartcampus@gmail.com"  
SMTP_PASSWORD = "qqyt ndzh nijq ddkm"    
FROM_EMAIL = "noreply@wastemanagement.com"

otp_store = {}
password_reset_store = {}
class Student(db.Model):
    __tablename__ = "student"
    id = db.Column(db.Integer, primary_key=True)
    roll_no = db.Column(db.String(12), unique=True, nullable=False)
    name = db.Column(db.String(100), nullable=False)
    department = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(100), unique=True)
    phone = db.Column(db.String(15))
    password = db.Column(db.String(200), nullable=False)
    google_id = db.Column(db.String(100), unique=True)
    is_google_account = db.Column(db.Boolean, default=False)
    email_verified = db.Column(db.Boolean, default=False)
    profile_picture = db.Column(db.String(500))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class Complaint(db.Model):
    __tablename__ = 'complaints'
    
    id = db.Column(db.Integer, primary_key=True)
    tracking_id = db.Column(db.String(50), unique=True, nullable=False, index=True)
    student_id = db.Column(db.Integer, nullable=False, index=True)
    student_name = db.Column(db.String(100), nullable=False)
    department = db.Column(db.String(100), nullable=False)
    
    # Complaint details
    location = db.Column(db.String(100), nullable=False)
    issue_type = db.Column(db.String(100), nullable=False)
    priority = db.Column(db.String(20), nullable=False, default='Medium')
    complaint_text = db.Column(db.Text, nullable=False)
    
    # Image paths stored as comma-separated string
    images = db.Column(db.Text, nullable=True)
    
    # Status tracking
    status = db.Column(db.String(50), nullable=False, default='Pending', index=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, onupdate=datetime.utcnow)
    resolved_at = db.Column(db.DateTime, nullable=True)
    
    def get_image_list(self):
        """Convert stored image string to list"""
        if self.images:
            return self.images.split(',')
        return []
    
    def get_image_count(self):
        """Get number of images"""
        return len(self.get_image_list())
    
    def get_image_urls(self):
        """Get full URLs for images"""
        return [url_for('serve_uploaded_file', filename=img) for img in self.get_image_list()]
    
    def to_dict(self):
        """Convert complaint to dictionary for API responses"""
        return {
            'id': self.id,
            'tracking_id': self.tracking_id,
            'student_name': self.student_name,
            'department': self.department,
            'location': self.location,
            'issue_type': self.issue_type,
            'priority': self.priority,
            'complaint_text': self.complaint_text,
            'images': self.get_image_list(),
            'image_urls': self.get_image_urls(),
            'image_count': self.get_image_count(),
            'status': self.status,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None
        }

class PasswordResetToken(db.Model):
    __tablename__ = "password_reset_token"
    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey('student.id'), nullable=False)
    token = db.Column(db.String(100), unique=True, nullable=False)
    expires_at = db.Column(db.DateTime, nullable=False)
    is_used = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    student = db.relationship('Student', backref='reset_tokens')

def generate_tracking_id():
    while True:
        tid = "WM" + "".join(random.choices(string.digits, k=8))
        if not Complaint.query.filter_by(tracking_id=tid).first():
            return tid

def generate_reset_token():
    return secrets.token_urlsafe(32)

def send_email(to_email, subject, html_content, text_content=None):
    """Generic email sending function"""
    try:
        msg = MIMEMultipart('alternative')
        msg['Subject'] = subject
        msg['From'] = FROM_EMAIL
        msg['To'] = to_email
        
        if text_content:
            msg.attach(MIMEText(text_content, 'plain'))
        msg.attach(MIMEText(html_content, 'html'))
        
        server = smtplib.SMTP(SMTP_SERVER, SMTP_PORT)
        server.starttls()
        server.login(SMTP_USERNAME, SMTP_PASSWORD)
        server.send_message(msg)
        server.quit()
        
        print(f"✓ Email sent to {to_email}")
        return True
        
    except Exception as e:
        print(f"✗ Failed to send email to {to_email}: {str(e)}")
        return False

def send_verification_email(email, otp):
    """Send OTP verification email to user"""
    subject = "Waste Management - Email Verification Code"
    
    html_content = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <style>
            body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; }}
            .container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
            .header {{ background: linear-gradient(135deg, #0d9488, #0f766e); color: white; padding: 30px; text-align: center; border-radius: 10px 10px 0 0; }}
            .content {{ background: #f8fafc; padding: 30px; border-radius: 0 0 10px 10px; }}
            .otp-code {{ font-size: 32px; font-weight: bold; color: #0d9488; letter-spacing: 5px; text-align: center; margin: 20px 0; }}
            .footer {{ text-align: center; margin-top: 30px; color: #64748b; font-size: 12px; }}
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <h2>Waste Management System</h2>
                <p>Email Verification</p>
            </div>
            <div class="content">
                <h3>Hello,</h3>
                <p>You're registering for the Waste Management System. Please use the following verification code to complete your registration:</p>
                
                <div class="otp-code">{otp}</div>
                
                <p>This code will expire in <strong>5 minutes</strong>.</p>
                
                <p>If you didn't request this verification, please ignore this email.</p>
                
                <p><strong>Note:</strong> For security reasons, never share this code with anyone.</p>
            </div>
            <div class="footer">
                <p>&copy; {datetime.now().year} Waste Management System. All rights reserved.</p>
                <p>This is an automated email, please do not reply.</p>
            </div>
        </div>
    </body>
    </html>
    """
    
    text_content = f"""
    Waste Management System - Email Verification
    
    Your verification code is: {otp}
    
    This code will expire in 5 minutes.
    
    If you didn't request this verification, please ignore this email.
    
    Note: For security reasons, never share this code with anyone.
    
    © {datetime.now().year} Waste Management System. All rights reserved.
    """
    
    return send_email(email, subject, html_content, text_content)

def send_password_reset_email(email, name, reset_url):
    """Send password reset email with reset link"""
    subject = "Waste Management - Password Reset Request"
    
    html_content = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <style>
            body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; }}
            .container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
            .header {{ background: linear-gradient(135deg, #0d9488, #0f766e); color: white; padding: 30px; text-align: center; border-radius: 10px 10px 0 0; }}
            .content {{ background: #f8fafc; padding: 30px; border-radius: 0 0 10px 10px; }}
            .reset-button {{ display: inline-block; background: linear-gradient(135deg, #0d9488, #0f766e); color: white; padding: 12px 30px; text-decoration: none; border-radius: 5px; font-weight: bold; margin: 20px 0; }}
            .warning {{ background: #fef3c7; border-left: 4px solid #f59e0b; padding: 15px; margin: 20px 0; }}
            .footer {{ text-align: center; margin-top: 30px; color: #64748b; font-size: 12px; }}
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <h2>Password Reset Request</h2>
            </div>
            <div class="content">
                <h3>Hello {name},</h3>
                <p>We received a request to reset your password for the Waste Management System.</p>
                
                <p>Click the button below to reset your password:</p>
                
                <div style="text-align: center;">
                    <a href="{reset_url}" class="reset-button">Reset Password</a>
                </div>
                
                <p>Or copy and paste this link in your browser:</p>
                <p style="background: #f1f5f9; padding: 10px; border-radius: 5px; word-break: break-all;">
                    {reset_url}
                </p>
                
                <div class="warning">
                    <strong>Important:</strong>
                    <ul>
                        <li>This link will expire in 15 minutes</li>
                        <li>If you didn't request this password reset, please ignore this email</li>
                        <li>For security, do not share this link with anyone</li>u
                    </ul>
                </div>
                
                <p>If you're having trouble clicking the button, copy and paste the URL above into your web browser.</p>
            </div>
            <div class="footer">
                <p>&copy; {datetime.now().year} Waste Management System. All rights reserved.</p>
                <p>This is an automated email, please do not reply.</p>
            </div>
        </div>
    </body>
    </html>
    """
    
    text_content = f"""
    Waste Management System - Password Reset Request
    
    Hello {name},
    
    We received a request to reset your password for the Waste Management System.
    
    To reset your password, click this link: {reset_url}
    
    Important:
    - This link will expire in 15 minutes
    - If you didn't request this password reset, please ignore this email
    - For security, do not share this link with anyone
    
    If you're having trouble clicking the link, copy and paste the URL into your web browser.
    
    © {datetime.now().year} Waste Management System. All rights reserved.
    """
    
    return send_email(email, subject, html_content, text_content)

def send_password_changed_email(email, name):
    """Send confirmation email when password is changed"""
    subject = "Waste Management - Password Changed Successfully"
    
    html_content = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <style>
            body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; }}
            .container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
            .header {{ background: linear-gradient(135deg, #0d9488, #0f766e); color: white; padding: 30px; text-align: center; border-radius: 10px 10px 0 0; }}
            .content {{ background: #f8fafc; padding: 30px; border-radius: 0 0 10px 10px; }}
            .success-box {{ background: #d1fae5; border: 1px solid #10b981; border-radius: 8px; padding: 20px; margin: 20px 0; }}
            .warning-box {{ background: #fef3c7; border: 1px solid #f59e0b; border-radius: 8px; padding: 20px; margin: 20px 0; }}
            .footer {{ text-align: center; margin-top: 30px; color: #64748b; font-size: 12px; }}
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <h2>Password Changed Successfully</h2>
            </div>
            <div class="content">
                <h3>Hello {name},</h3>
                
                <div class="success-box">
                    <h4 style="color: #065f46; margin-top: 0;">✓ Password Updated Successfully</h4>
                    <p>Your Waste Management System password has been changed successfully.</p>
                </div>
                
                <div class="warning-box">
                    <h4 style="color: #92400e; margin-top: 0;">Security Information</h4>
                    <p><strong>If you made this change:</strong> No further action is required.</p>
                    <p><strong>If you did NOT make this change:</strong> Please contact support immediately at:</p>
                    <p style="margin-left: 20px;">
                        Email: <strong>greenmatrixsmartcampus@gmail.com</strong><br>
                        Phone: <strong>[Your Support Phone Number]</strong>
                    </p>
                </div>
                
                <p>For security purposes, we recommend:</p>
                <ul>
                    <li>Using a strong, unique password</li>
                    <li>Enabling two-factor authentication if available</li>
                    <li>Not sharing your password with anyone</li>
                    <li>Logging out from shared computers</li>
                </ul>
            </div>
            <div class="footer">
                <p>&copy; {datetime.now().year} Waste Management System. All rights reserved.</p>
                <p>This is an automated email, please do not reply.</p>
            </div>
        </div>
    </body>
    </html>
    """
    
    text_content = f"""
    Waste Management System - Password Changed Successfully
    
    Hello {name},
    
    Your Waste Management System password has been changed successfully.
    
    ✓ Password Updated Successfully
    
    Security Information:
    
    If you made this change: No further action is required.
    
    If you did NOT make this change: Please contact support immediately at:
    Email: greenmatrixsmartcampus@gmail.com
    Phone: [Your Support Phone Number]
    
    For security purposes, we recommend:
    - Using a strong, unique password
    - Enabling two-factor authentication if available
    - Not sharing your password with anyone
    - Logging out from shared computers
    
    © {datetime.now().year} Waste Management System. All rights reserved.
    """
    
    return send_email(email, subject, html_content, text_content)

@app.route("/", methods=["GET", "POST"])
def index():
    if request.method == "POST":
        roll_no = request.form.get("roll_no")
        student = Student.query.filter_by(roll_no=roll_no).first()

        if not student:
            flash("Student not found", "danger")
            return redirect(url_for("index"))

        if not student.is_google_account:
            password = request.form.get("password")
            if not password or not check_password_hash(student.password, password):
                flash("Invalid password", "danger")
                return redirect(url_for("index"))

        session["student_id"] = student.id
        session["student_name"] = student.name
        session["department"] = student.department
        session["roll_no"] = student.roll_no

        flash("Login successful", "success")
        return redirect(url_for("student_dashboard"))

    stats = {
        "total_students": Student.query.count(),
        "total_complaints": Complaint.query.count(),
        "pending_complaints": Complaint.query.filter_by(status="Pending").count(),
        "resolved_complaints": Complaint.query.filter_by(status="Resolved").count(),
        "current_year": datetime.now().year,
    }

    return render_template("index.html", stats=stats, current_year=datetime.now().year)

# ================= PASSWORD RESET FLOW ================= #

@app.route("/student/forgot-password", methods=["GET"])
def forgot_password():
    """Render forgot password page"""
    return render_template("forgot_password.html")

@app.route("/api/send-reset-otp", methods=["POST"])
def send_reset_otp():
    """Send OTP for password reset"""
    try:
        data = request.get_json()
        email = data.get("email")
        
        if not email:
            return jsonify({"success": False, "error": "Email is required"})
        
        # Check if email exists
        student = Student.query.filter_by(email=email).first()
        if not student:
            return jsonify({"success": False, "error": "No account found with this email"})
        
        # Generate OTP
        otp = ''.join(random.choices(string.digits, k=6))
        
        # Store OTP temporarily (expires in 5 minutes)
        password_reset_store[email] = {
            "otp": otp,
            "expires": datetime.now() + timedelta(minutes=5),
            "student_id": student.id
        }
        
        # Send OTP email
        subject = "Waste Management - Password Reset OTP"
        html_content = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <style>
                body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; }}
                .container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
                .header {{ background: linear-gradient(135deg, #0d9488, #0f766e); color: white; padding: 30px; text-align: center; border-radius: 10px 10px 0 0; }}
                .content {{ background: #f8fafc; padding: 30px; border-radius: 0 0 10px 10px; }}
                .otp-code {{ font-size: 32px; font-weight: bold; color: #0d9488; letter-spacing: 5px; text-align: center; margin: 20px 0; }}
                .footer {{ text-align: center; margin-top: 30px; color: #64748b; font-size: 12px; }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h2>Waste Management System</h2>
                    <p>Password Reset Verification</p>
                </div>
                <div class="content">
                    <h3>Hello {student.name},</h3>
                    <p>We received a request to reset your password. Please use the following verification code:</p>
                    
                    <div class="otp-code">{otp}</div>
                    
                    <p>This code will expire in <strong>5 minutes</strong>.</p>
                    
                    <p>If you didn't request this password reset, please ignore this email.</p>
                    
                    <p><strong>Security Note:</strong> Never share this code with anyone. Our team will never ask for your verification code.</p>
                </div>
                <div class="footer">
                    <p>&copy; {datetime.now().year} Waste Management System. All rights reserved.</p>
                    <p>This is an automated email, please do not reply.</p>
                </div>
            </div>
        </body>
        </html>
        """
        
        text_content = f"""
        Waste Management System - Password Reset Verification
        
        Hello {student.name},
        
        We received a request to reset your password. Please use the following verification code:
        
        {otp}
        
        This code will expire in 5 minutes.
        
        If you didn't request this password reset, please ignore this email.
        
        Security Note: Never share this code with anyone. Our team will never ask for your verification code.
        
        © {datetime.now().year} Waste Management System. All rights reserved.
        """
        
        email_sent = send_email(email, subject, html_content, text_content)
        
        if email_sent:
            print(f"Password reset OTP for {email}: {otp}")
            return jsonify({"success": True, "message": "Verification code sent to your email"})
        else:
            return jsonify({"success": False, "error": "Failed to send verification email. Please try again."})
        
    except Exception as e:
        print(f"Error in send_reset_otp: {str(e)}")
        return jsonify({"success": False, "error": "An error occurred. Please try again."})

@app.route("/api/verify-reset-otp", methods=["POST"])
def verify_reset_otp():
    """Verify OTP for password reset"""
    try:
        data = request.get_json()
        email = data.get("email")
        otp = data.get("otp")
        
        if not email or not otp:
            return jsonify({"success": False, "error": "Email and OTP are required"})
        
        # Check if OTP exists and is not expired
        if email not in password_reset_store:
            return jsonify({"success": False, "error": "OTP not found or expired. Please request a new code."})
        
        stored_data = password_reset_store[email]
        
        if datetime.now() > stored_data["expires"]:
            del password_reset_store[email]
            return jsonify({"success": False, "error": "OTP expired. Please request a new code."})
        
        if stored_data["otp"] != otp:
            # Count failed attempts
            if "attempts" not in stored_data:
                stored_data["attempts"] = 1
            else:
                stored_data["attempts"] += 1
            
            if stored_data["attempts"] >= 3:
                del password_reset_store[email]
                return jsonify({"success": False, "error": "Too many failed attempts. Please request a new code."})
            
            return jsonify({"success": False, "error": "Invalid verification code"})
        
        # OTP verified successfully
        session["reset_email"] = email
        session["reset_verified"] = True
        session["reset_student_id"] = stored_data["student_id"]
        
        # Clear OTP from store
        del password_reset_store[email]
        
        return jsonify({
            "success": True,
            "message": "Verification successful",
            "redirect_url": url_for("reset_password")
        })
        
    except Exception as e:
        print(f"Error in verify_reset_otp: {str(e)}")
        return jsonify({"success": False, "error": "An error occurred. Please try again."})

@app.route("/reset-password", methods=["GET", "POST"])
def reset_password():
    """Reset password after OTP verification"""
    if not session.get("reset_verified") or not session.get("reset_email"):
        flash("Please verify your email first", "danger")
        return redirect(url_for("forgot_password"))
    
    if request.method == "GET":
        return render_template("reset_password.html", email=session.get("reset_email"))
    
    elif request.method == "POST":
        try:
            email = session.get("reset_email")
            student_id = session.get("reset_student_id")
            new_password = request.form.get("new_password")
            confirm_password = request.form.get("confirm_password")
            
            if not new_password or not confirm_password:
                flash("Both password fields are required", "danger")
                return redirect(url_for("reset_password"))
            
            if new_password != confirm_password:
                flash("Passwords do not match", "danger")
                return redirect(url_for("reset_password"))
            
            # Password strength validation
            if len(new_password) < 8:
                flash("Password must be at least 8 characters long", "danger")
                return redirect(url_for("reset_password"))
            
            # Update password
            student = Student.query.get(student_id)
            if not student:
                flash("Student not found", "danger")
                return redirect(url_for("forgot_password"))
            
            student.password = generate_password_hash(new_password)
            db.session.commit()
            
            # Send confirmation email
            send_password_changed_email(student.email, student.name)
            
            # Clear reset session
            session.pop("reset_email", None)
            session.pop("reset_verified", None)
            session.pop("reset_student_id", None)
            
            flash("Password reset successfully! You can now login with your new password", "success")
            return redirect(url_for("index"))
            
        except Exception as e:
            db.session.rollback()
            flash(f"Failed to reset password: {str(e)}", "danger")
            return redirect(url_for("reset_password"))

# ================= REGISTRATION OTP FLOW ================= #

@app.route("/student/signup", methods=["GET"])
def student_signup():
    return render_template("signup_verification.html")

@app.route("/send-otp", methods=["POST"])
def send_otp():
    try:
        data = request.get_json()
        email = data.get("email")
        
        if not email:
            return jsonify({"success": False, "error": "Email is required"})
        
        # Check if email already exists
        if Student.query.filter_by(email=email).first():
            return jsonify({"success": False, "error": "Email already registered. Please login instead."})
        
        otp = ''.join(random.choices(string.digits, k=6))
        
        otp_store[email] = {
            "otp": otp,
            "expires": datetime.now() + timedelta(minutes=5)
        }
        
        # Send email
        email_sent = send_verification_email(email, otp)
        
        if email_sent:
            print(f"Registration OTP for {email}: {otp}")
            return jsonify({"success": True, "message": "Verification code sent to your email"})
        else:
            return jsonify({"success": False, "error": "Failed to send verification code. Please try again."})
        
    except Exception as e:
        print(f"Error in send_otp: {str(e)}")
        return jsonify({"success": False, "error": "Failed to send verification code. Please try again."})

@app.route("/verify-otp", methods=["POST"])
def verify_otp():
    try:
        data = request.get_json()
        email = data.get("email")
        otp = data.get("otp")
        
        if not email or not otp:
            return jsonify({"success": False, "error": "Email and OTP are required"})
        
        if email not in otp_store:
            return jsonify({"success": False, "error": "OTP not found or expired"})
        
        stored_data = otp_store[email]
        
        if datetime.now() > stored_data["expires"]:
            del otp_store[email]
            return jsonify({"success": False, "error": "OTP expired. Please request a new code."})
        
        if stored_data["otp"] != otp:
            return jsonify({"success": False, "error": "Invalid verification code"})
        
        del otp_store[email]
        
        session["verified_email"] = email
        session["verification_method"] = "email"
        
        return jsonify({
            "success": True,
            "redirect_url": url_for("complete_registration")
        })
        
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})

@app.route("/student/complete-registration", methods=["GET", "POST"])
def complete_registration():
    print(f"\n" + "="*50)
    print("COMPLETE REGISTRATION ACCESSED")
    print(f"Session data: {dict(session)}")
    print("="*50 + "\n")
    
    if request.method == "GET":
        # Check if user came from Google OAuth
        if "google_user_info" in session:
            user_info = session["google_user_info"]
            print(f"Google user info found: {user_info}")
            
            # Auto-fill form with Google info
            return render_template("complete_registration.html", 
                                 user_info=user_info,
                                 email=user_info["email"],
                                 name=user_info.get("name", ""),
                                 picture=user_info.get("picture", ""),
                                 google_id=user_info["google_id"])
        
        # Check if user came from email verification
        elif "verified_email" in session:
            email = session["verified_email"]
            print(f"Verified email found: {email}")
            
            return render_template("complete_registration.html",
                                 user_info={"email": email, "name": "", "picture": ""},
                                 email=email,
                                 name="",
                                 picture="")
        
        else:
            print("No registration info found in session")
            flash("Please verify your email or login with Google first", "danger")
            return redirect(url_for("student_signup"))
    
    elif request.method == "POST":
        try:
            print(f"Registration POST data: {dict(request.form)}")
            
            roll_no = request.form.get("roll_no")
            name = request.form.get("name")
            email = request.form.get("email")
            department = request.form.get("department")
            phone = request.form.get("phone")
            password = request.form.get("password")
            confirm_password = request.form.get("confirm_password")
            google_id = request.form.get("google_id")
            picture = request.form.get("picture")
            
            # Validate required fields
            if not roll_no:
                flash("Roll number is required", "danger")
                return redirect(url_for("complete_registration"))
            
            if not department:
                flash("Department is required", "danger")
                return redirect(url_for("complete_registration"))
            
            # For non-Google accounts, validate password
            if not google_id:
                if not password:
                    flash("Password is required for email registration", "danger")
                    return redirect(url_for("complete_registration"))
                
                if password != confirm_password:
                    flash("Passwords do not match", "danger")
                    return redirect(url_for("complete_registration"))
                
                if len(password) < 8:
                    flash("Password must be at least 8 characters", "danger")
                    return redirect(url_for("complete_registration"))
            
            # Check if roll number already exists
            if Student.query.filter_by(roll_no=roll_no).first():
                flash("Student with this roll number already exists", "danger")
                return redirect(url_for("complete_registration"))
            
            # Check if email already exists (different account)
            existing_student = Student.query.filter_by(email=email).first()
            if existing_student:
                if google_id and existing_student.google_id != google_id:
                    flash("Email already registered with different account", "danger")
                    return redirect(url_for("complete_registration"))
                elif not google_id and existing_student.google_id:
                    flash("Email already registered with Google. Please use Google login.", "danger")
                    return redirect(url_for("complete_registration"))
            
            # Determine final name
            final_name = name if name else "Student"
            
            # Create student record
            student = Student(
                roll_no=roll_no,
                name=final_name,
                department=department,
                email=email,
                phone=phone if phone else None,
                google_id=google_id if google_id else None,
                is_google_account=bool(google_id),
                email_verified=True,
                profile_picture=picture if picture else None,
                password=generate_password_hash(password) if password else generate_password_hash(secrets.token_urlsafe(16)),
                created_at=datetime.utcnow()
            )
            
            db.session.add(student)
            db.session.commit()
            
            print(f"✅ Student created: {student.id}, {student.name}, {student.email}")
            
            # Send welcome email
            if email:
                try:
                    send_welcome_email(email, student.name)
                    print(f"✅ Welcome email sent to {email}")
                except Exception as e:
                    print(f"⚠️ Could not send welcome email: {str(e)}")
            
            # Clear session data
            session_keys = ["google_user_info", "verified_email", "verification_method", "oauth_state"]
            for key in session_keys:
                session.pop(key, None)
            
            # Set session for auto-login
            session["student_id"] = student.id
            session["student_name"] = student.name
            session["department"] = student.department
            session["roll_no"] = student.roll_no
            
            print(f"✅ Session set for user: {student.name}")
            flash("Registration successful! Welcome to Waste Management System", "success")
            return redirect(url_for("student_dashboard"))
            
        except Exception as e:
            db.session.rollback()
            print(f"❌ Registration error: {str(e)}")
            import traceback
            traceback.print_exc()
            flash(f"Registration failed: {str(e)}", "danger")
            return redirect(url_for("complete_registration"))

def send_welcome_email(email, name):
    """Send welcome email to new user"""
    subject = "Welcome to Waste Management System"
    
    # Use the correct port (5001 instead of 5000)
    login_url = "http://localhost:5001"  # Updated port
    
    html_content = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <style>
            body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; }}
            .container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
            .header {{ background: linear-gradient(135deg, #0d9488, #0f766e); color: white; padding: 30px; text-align: center; border-radius: 10px 10px 0 0; }}
            .content {{ background: #f8fafc; padding: 30px; border-radius: 0 0 10px 10px; }}
            .footer {{ text-align: center; margin-top: 30px; color: #64748b; font-size: 12px; }}
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <h2>Welcome to Waste Management System!</h2>
            </div>
            <div class="content">
                <h3>Hello {name},</h3>
                <p>Welcome to the Waste Management System! Your account has been successfully created.</p>
                
                <p>You can now:</p>
                <ul>
                    <li>Report waste management issues</li>
                    <li>Track your complaint status</li>
                    <li>Contribute to a cleaner campus</li>
                    <li>View your complaint history</li>
                </ul>
                
                <p>To get started, simply login to your account and submit your first complaint.</p>
                
                <p><strong>Login URL:</strong> <a href="{login_url}">{login_url}</a></p>
                
                <p>If you have any questions or need assistance, please don't hesitate to contact us at:</p>
                <p><strong>Email:</strong> greenmatrixsmartcampus@gmail.com</p>
                
                <p>Thank you for helping us maintain a cleaner environment!</p>
            </div>
            <div class="footer">
                <p>&copy; {datetime.now().year} Waste Management System. All rights reserved.</p>
            </div>
        </div>
    </body>
    </html>
    """
    
    text_content = f"""
    Welcome to Waste Management System!
    
    Hello {name},
    
    Welcome to the Waste Management System! Your account has been successfully created.
    
    You can now:
    - Report waste management issues
    - Track your complaint status
    - Contribute to a cleaner campus
    - View your complaint history
    
    To get started, simply login to your account at: {login_url}
    
    If you have any questions or need assistance, please contact us at:
    Email: greenmatrixsmartcampus@gmail.com
    
    Thank you for helping us maintain a cleaner environment!
    
    © {datetime.now().year} Waste Management System. All rights reserved.
    """
    
    return send_email(email, subject, html_content, text_content)
@app.route("/student/dashboard")
def student_dashboard():
    if "student_id" not in session:
        return redirect(url_for("index"))

    student = Student.query.get(session["student_id"])
    complaints = Complaint.query.filter_by(student_id=session["student_id"]).all()

    # Calculate stats
    total_complaints = len(complaints)
    pending_complaints = len([c for c in complaints if c.status == "Pending"])
    resolved_complaints = len([c for c in complaints if c.status == "Resolved"])
    in_progress_complaints = len([c for c in complaints if c.status == "In Progress"])

    stats = {
        "total": total_complaints,
        "pending": pending_complaints,
        "resolved": resolved_complaints,
        "in_progress": in_progress_complaints
    }

    return render_template(
        "student_dashboard.html",
        complaints=complaints,
        name=session["student_name"],
        department=session["department"],
        roll_no=session["roll_no"],
        stats=stats,
        student=student
    )

@app.route("/student/my-complaints")
def my_complaints():
    if "student_id" not in session:
        return redirect(url_for("index"))
    
    complaints = Complaint.query.filter_by(student_id=session["student_id"]).all()
    
    return render_template(
        "student_dashboard.html",
        complaints=complaints,
        name=session["student_name"],
        department=session["department"],
        roll_no=session["roll_no"],
    )

UPLOAD_FOLDER = 'static/uploads'
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp'}
MAX_FILE_SIZE = 5 * 1024 * 1024  # 5MB per file
MAX_FILES = 5  # Maximum number of files per complaint

# Make sure upload directory exists
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = MAX_FILE_SIZE * MAX_FILES  # 25MB total

def allowed_file(filename):
    """Check if file has an allowed extension"""
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def generate_unique_filename(original_filename):
    """Generate a unique filename using UUID and timestamp"""
    # Get file extension
    ext = original_filename.rsplit('.', 1)[1].lower() if '.' in original_filename else ''
    # Generate unique filename with timestamp and UUID
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    unique_id = str(uuid.uuid4())[:8]  # First 8 characters of UUID
    return f"complaint_{timestamp}_{unique_id}.{ext}"

def generate_tracking_id():
    """Generate a unique tracking ID for complaints"""
    timestamp = datetime.now().strftime('%Y%m%d%H%M%S')
    unique_id = str(uuid.uuid4())[:6].upper()
    return f"WM{timestamp}{unique_id}"

@app.route("/student/submit-complaint", methods=["POST"])
def submit_complaint():
    # Check if student is logged in
    if "student_id" not in session:
        flash("Please login to submit a complaint", "warning")
        return redirect(url_for("index"))
    
    try:
        # Get form data
        location = request.form.get("location")
        issue_type = request.form.get("issue_type")
        priority = request.form.get("priority")
        description = request.form.get("description")

        # Validate required fields
        if not all([location, issue_type, priority, description]):
            flash("All fields are required", "danger")
            return redirect(url_for("student_dashboard", _anchor="new-complaint"))

        # Handle file uploads
        uploaded_files = request.files.getlist('images')
        image_paths = []
        upload_errors = []
        
        # Filter out empty file inputs
        valid_files = [f for f in uploaded_files if f and f.filename]
        
        # Check number of files
        if len(valid_files) > MAX_FILES:
            flash(f'You can only upload up to {MAX_FILES} images. Only the first {MAX_FILES} will be saved.', 'warning')
            valid_files = valid_files[:MAX_FILES]
        
        # Process each uploaded file
        for file in valid_files:
            # Check if file is allowed
            if file and allowed_file(file.filename):
                # Check file size
                file.seek(0, os.SEEK_END)
                file_length = file.tell()
                file.seek(0)  # Reset file pointer
                
                if file_length > MAX_FILE_SIZE:
                    upload_errors.append(f'{file.filename} exceeds 5MB limit and was not uploaded')
                    continue
                
                try:
                    # Secure the filename and generate unique name
                    secure_name = secure_filename(file.filename)
                    unique_filename = generate_unique_filename(secure_name)
                    
                    # Create year/month subdirectories to organize uploads
                    date_path = datetime.now().strftime('%Y/%m')
                    upload_subdir = os.path.join(UPLOAD_FOLDER, date_path)
                    os.makedirs(upload_subdir, exist_ok=True)
                    
                    # Save the file
                    file_path = os.path.join(upload_subdir, unique_filename)
                    file.save(file_path)
                    
                    # Store relative path for database (for easy retrieval)
                    relative_path = os.path.join('uploads', date_path, unique_filename)
                    image_paths.append(relative_path)
                    
                except Exception as e:
                    upload_errors.append(f'Error saving {file.filename}: {str(e)}')
            else:
                upload_errors.append(f'{file.filename} is not an allowed file type (use PNG, JPG, JPEG, GIF, WEBP)')
        
        # Show upload errors if any
        if upload_errors:
            for error in upload_errors:
                flash(error, 'warning')
        
        # Generate unique tracking ID
        tracking_id = generate_tracking_id()
        
        # Create complaint object
        complaint = Complaint(
            tracking_id=tracking_id,
            student_id=session["student_id"],
            student_name=session.get("student_name", "Student"),
            department=session.get("department", "Not Specified"),
            location=location,
            issue_type=issue_type,
            priority=priority,
            complaint_text=description,
            images=','.join(image_paths) if image_paths else None,  # Store as comma-separated string
            status="Pending",
            created_at=datetime.utcnow()
        )

        # Save to database
        db.session.add(complaint)
        db.session.commit()

        # Success message with image count
        if image_paths:
            flash(f'Complaint submitted successfully! Tracking ID: {tracking_id}. {len(image_paths)} image(s) uploaded.', 'success')
        else:
            flash(f'Complaint submitted successfully! Tracking ID: {tracking_id}', 'success')
        
        return redirect(url_for("student_dashboard", _anchor="my-complaints"))
        
    except Exception as e:
        db.session.rollback()
        flash(f'Error submitting complaint: {str(e)}', 'danger')
        return redirect(url_for("student_dashboard", _anchor="new-complaint"))

# Optional: Add a route to serve uploaded images securely
@app.route('/uploads/<path:filename>')
def serve_uploaded_file(filename):
    """Serve uploaded files securely"""
    from flask import send_from_directory
    return send_from_directory(UPLOAD_FOLDER, filename)

# Optional: Add a route to delete images (if complaint is cancelled)
@app.route('/delete-upload/<path:filename>', methods=['DELETE'])
def delete_uploaded_file(filename):
    """Delete an uploaded file (for cleanup)"""
    try:
        file_path = os.path.join(UPLOAD_FOLDER, filename)
        if os.path.exists(file_path) and os.path.isfile(file_path):
            os.remove(file_path)
            return {'success': True, 'message': 'File deleted successfully'}
        return {'success': False, 'error': 'File not found'}, 404
    except Exception as e:
        return {'success': False, 'error': str(e)}, 500
@app.route("/student/view-complaint/<int:complaint_id>")
def view_complaint(complaint_id):
    if "student_id" not in session:
        return redirect(url_for("index"))
    
    complaint = Complaint.query.get_or_404(complaint_id)
    
    # Check if complaint belongs to current student
    if complaint.student_id != session["student_id"]:
        flash("Access denied", "danger")
        return redirect(url_for("student_dashboard"))
    
    return render_template(
        "view_complaint.html",
        complaint=complaint,
        name=session["student_name"],
        department=session["department"],
        roll_no=session["roll_no"]
    )

@app.route("/student/update-profile", methods=["POST"])
def update_profile():
    if "student_id" not in session:
        return redirect(url_for("index"))
    
    student = Student.query.get(session["student_id"])
    
    name = request.form.get("name")
    phone = request.form.get("phone")
    current_password = request.form.get("current_password")
    new_password = request.form.get("new_password")
    confirm_password = request.form.get("confirm_password")
    
    if name:
        student.name = name
        session["student_name"] = name
    
    if phone:
        student.phone = phone
    
    # Handle password change
    if current_password and new_password:
        if not check_password_hash(student.password, current_password):
            flash("Current password is incorrect", "danger")
        elif new_password != confirm_password:
            flash("New passwords do not match", "danger")
        elif len(new_password) < 8:
            flash("Password must be at least 8 characters", "danger")
        else:
            student.password = generate_password_hash(new_password)
            send_password_changed_email(student.email, student.name)
            flash("Password updated successfully", "success")
    
    db.session.commit()
    flash("Profile updated successfully", "success")
    return redirect(url_for("student_dashboard"))

@app.route("/student/logout")
def student_logout():
    session.clear()
    flash("Logged out successfully", "info")
    return redirect(url_for("index"))
@app.route("/test/registration")
def test_registration():
    """Test registration flow"""
    return render_template("test_registration.html")

@app.route("/test/direct-registration")
def test_direct_registration():
    """Test registration directly without Google OAuth"""
    # Simulate a Google user
    session["google_user_info"] = {
        "google_id": "test_google_id_123",
        "email": "testuser@example.com",
        "name": "Test User",
        "picture": ""
    }
    return redirect(url_for("complete_registration"))

@app.route("/debug/session")
def debug_session():
    """Show current session data"""
    session_data = {}
    for key, value in session.items():
        if key != '_flashes':
            try:
                session_data[key] = str(value)
            except:
                session_data[key] = f"<unserializable: {type(value)}>"
    
    return f"""
    <html>
    <head><title>Session Debug</title></head>
    <body>
        <h1>Session Data</h1>
        <pre>{json.dumps(session_data, indent=2)}</pre>
        <h2>Actions:</h2>
        <p><a href="{url_for('clear_session')}">Clear Session</a></p>
        <p><a href="{url_for('index')}">Go Home</a></p>
    </body>
    </html>
    """

@app.route("/clear-session")
def clear_session():
    """Clear session data"""
    session.clear()
    return "Session cleared"
if __name__ == "__main__":
    with app.app_context():
        db.create_all()
        print("=" * 60)
        print("Waste Management System - Student Portal")
        print("=" * 60)
        print("Database tables created/checked")
        print("Email Configuration:")
        print(f"SMTP Server: {SMTP_SERVER}:{SMTP_PORT}")
        print(f"From Email: {FROM_EMAIL}")
        print(f"SMTP Username: {SMTP_USERNAME}")
        print("=" * 60)
        print("Password Reset Features:")
        print("✓ OTP-based password reset")
        print("✓ Email verification for security")
        print("✓ Password strength validation")
        print("✓ Security confirmation emails")
        print("=" * 60)
        print("Server running at http://localhost:8080")  # Changed port
        print("=" * 60)
    
    app.run(debug=True, host="0.0.0.0", port=8080)  # Changed port
    