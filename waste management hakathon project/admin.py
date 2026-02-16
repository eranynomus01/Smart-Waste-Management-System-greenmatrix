from flask import Flask, render_template, request, redirect, url_for, flash, session, jsonify, send_file
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime, timedelta
import os
import csv
import io
import pymysql
import uuid
from urllib.parse import quote_plus
from werkzeug.utils import secure_filename

app = Flask(__name__)
app.secret_key = "admin_app_secret_key_67890"

# ================= UPLOAD CONFIGURATION ================= #
UPLOAD_FOLDER = 'static/uploads'
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp'}
MAX_FILE_SIZE = 5 * 1024 * 1024  # 5MB per file
MAX_FILES = 5  # Maximum number of files per complaint

# Create upload directory if it doesn't exist
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = MAX_FILE_SIZE * MAX_FILES  # 25MB total

# ================= DATABASE CONFIG ================= #
pymysql.install_as_MySQLdb()

DB_USER = "root"
DB_PASSWORD = quote_plus("pankaj1412@2711")
DB_HOST = "TOMAR-PC"
DB_NAME = "wastemanagementmain"

app.config["SQLALCHEMY_DATABASE_URI"] = (
    f"mysql+pymysql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}/{DB_NAME}?charset=utf8mb4"
)
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

db = SQLAlchemy(app)

# ================= MODELS ================= #
class Admin(db.Model):
    __tablename__ = "admin"
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True, nullable=False)
    name = db.Column(db.String(100), nullable=False)
    password = db.Column(db.String(200), nullable=False)
    role = db.Column(db.String(50), default="admin")

class Student(db.Model):
    __tablename__ = "student"
    id = db.Column(db.Integer, primary_key=True)
    roll_no = db.Column(db.String(12), unique=True, nullable=False)
    name = db.Column(db.String(100), nullable=False)
    department = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(100))
    phone = db.Column(db.String(15))
    password = db.Column(db.String(200), nullable=False)

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
    
    # Assigned to
    assigned_to = db.Column(db.String(100), nullable=True)
    
    # Status tracking
    status = db.Column(db.String(50), nullable=False, default='Pending', index=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, onupdate=datetime.utcnow)
    resolved_at = db.Column(db.DateTime, nullable=True)
    
    def get_image_list(self):
        """Convert stored image string to list"""
        if self.images:
            # Handle both comma-separated string and JSON string
            if isinstance(self.images, str):
                if self.images.startswith('[') and self.images.endswith(']'):
                    # It's a JSON string
                    import json
                    try:
                        return json.loads(self.images)
                    except:
                        return self.images.strip('[]').replace('"', '').replace("'", '').split(',')
                else:
                    # It's a comma-separated string
                    return [img for img in self.images.split(',') if img]
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
            'assigned_to': self.assigned_to,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None
        }

class ActivityLog(db.Model):
    __tablename__ = "activity_log"
    id = db.Column(db.Integer, primary_key=True)
    user_type = db.Column(db.String(20))
    user_id = db.Column(db.Integer)
    action = db.Column(db.String(100))
    details = db.Column(db.Text)
    timestamp = db.Column(db.DateTime, server_default=db.func.now())

# ================= HELPER FUNCTIONS ================= #
def create_default_admin():
    """Create default admin if not exists"""
    if not Admin.query.filter_by(username="admin").first():
        admin = Admin(
            username="admin",
            name="Main Admin",
            password=generate_password_hash("admin123"),
            role="super_admin"
        )
        db.session.add(admin)
        db.session.commit()
        print("✅ Default Admin Created (admin / admin123)")

def log_activity(user_type, user_id, action, details=""):
    """Log user activity"""
    log = ActivityLog(
        user_type=user_type,
        user_id=user_id,
        action=action,
        details=details
    )
    db.session.add(log)
    db.session.commit()

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

# ================= STUDENT ROUTES ================= #
@app.route("/student/submit-complaint", methods=["POST"])
def student_submit_complaint():
    """Handle complaint submission from students with image uploads"""
    if "student_id" not in session:
        flash("Please login to submit a complaint", "warning")
        return redirect(url_for("student_login"))
    
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
                    relative_path = os.path.join('uploads', date_path, unique_filename).replace('\\', '/')
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
        
        # Convert image paths to comma-separated string
        images_string = ','.join(image_paths) if image_paths else None
        
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
            images=images_string,
            status="Pending",
            created_at=datetime.utcnow()
        )

        # Save to database
        db.session.add(complaint)
        db.session.commit()

        # Log activity
        log_activity("student", session["student_id"], "submit_complaint", 
                    f"Submitted complaint {tracking_id} with {len(image_paths)} images")

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

# ================= ADMIN ROUTES ================= #
@app.route("/", methods=["GET", "POST"])
def admin_login():
    """Admin login page"""
    if "admin_id" in session:
        return redirect(url_for("admin_dashboard"))
    
    if request.method == "POST":
        username = request.form.get("username")
        password = request.form.get("password")

        admin = Admin.query.filter_by(username=username).first()
        if admin and check_password_hash(admin.password, password):
            session["admin_id"] = admin.id
            session["admin_name"] = admin.name
            session["admin_role"] = admin.role
            
            log_activity("admin", admin.id, "login", f"Admin {admin.name} logged in")
            flash("Welcome Admin!", "success")
            return redirect(url_for("admin_dashboard"))

        flash("Invalid admin credentials", "danger")
    
    return render_template("admin_login.html")

@app.route("/admin/dashboard")
def admin_dashboard():
    """Admin dashboard with all complaints and analytics"""
    if "admin_id" not in session:
        return redirect(url_for("admin_login"))

    complaints = Complaint.query.order_by(Complaint.created_at.desc()).all()
    
    # Calculate statistics
    total_complaints = len(complaints)
    pending_count = Complaint.query.filter_by(status="Pending").count()
    in_progress_count = Complaint.query.filter_by(status="In Progress").count()
    resolved_count = Complaint.query.filter_by(status="Resolved").count()
    high_priority_count = Complaint.query.filter_by(priority="High").count()
    
    # Issue types data for charts
    issue_types_data = {}
    complaints_by_type = db.session.query(
        Complaint.issue_type, 
        db.func.count(Complaint.id)
    ).group_by(Complaint.issue_type).all()
    
    for issue_type, count in complaints_by_type:
        issue_types_data[issue_type] = count
    
    # Location data for charts
    location_data = {}
    complaints_by_location = db.session.query(
        Complaint.location, 
        db.func.count(Complaint.id)
    ).group_by(Complaint.location).all()
    
    for location, count in complaints_by_location:
        location_data[location] = count
    
    # Timeline data (last 7 days)
    dates_data = {}
    date_labels = []
    date_counts = []
    
    for i in range(6, -1, -1):
        date = (datetime.now() - timedelta(days=i)).strftime('%Y-%m-%d')
        start_of_day = datetime.now() - timedelta(days=i)
        start_of_day = start_of_day.replace(hour=0, minute=0, second=0, microsecond=0)
        end_of_day = start_of_day + timedelta(days=1)
        
        count = Complaint.query.filter(
            Complaint.created_at >= start_of_day,
            Complaint.created_at < end_of_day
        ).count()
        
        dates_data[date] = count
        date_labels.append(date)
        date_counts.append(count)
    
    # Resolution rate for current month
    start_of_month = datetime.now().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    
    if datetime.now().month == 12:
        end_of_month = datetime.now().replace(year=datetime.now().year+1, month=1, day=1)
    else:
        end_of_month = datetime.now().replace(month=datetime.now().month+1, day=1)
    
    resolved_this_month = Complaint.query.filter(
        Complaint.status == 'Resolved',
        Complaint.created_at >= start_of_month,
        Complaint.created_at < end_of_month
    ).count()
    
    total_this_month = Complaint.query.filter(
        Complaint.created_at >= start_of_month,
        Complaint.created_at < end_of_month
    ).count()
    
    resolution_rate = round((resolved_this_month / total_this_month * 100) if total_this_month > 0 else 0, 1)
    
    # Recent activities
    recent_activities = ActivityLog.query.order_by(ActivityLog.timestamp.desc()).limit(10).all()
    
    # Average resolution time
    resolved_complaints = Complaint.query.filter_by(status="Resolved").all()
    avg_resolution_time = 0
    if resolved_complaints:
        total_hours = sum([
            ((c.updated_at or c.resolved_at or datetime.utcnow()) - c.created_at).total_seconds() / 3600 
            for c in resolved_complaints if c.created_at
        ])
        avg_resolution_time = round(total_hours / len(resolved_complaints), 1)
    
    current_date = datetime.now().strftime('%B %d, %Y')
    
    return render_template(
        "admin_dashboard.html",
        complaints=complaints,
        admin_name=session["admin_name"],
        admin_role=session.get("admin_role", "admin"),
        total_complaints=total_complaints,
        pending_count=pending_count,
        in_progress_count=in_progress_count,
        resolved_count=resolved_count,
        high_priority_count=high_priority_count,
        resolution_rate=resolution_rate,
        avg_resolution_time=avg_resolution_time,
        recent_activities=recent_activities,
        issue_types_labels=list(issue_types_data.keys()),
        issue_types_counts=list(issue_types_data.values()),
        location_labels=list(location_data.keys()),
        location_counts=list(location_data.values()),
        date_labels=date_labels,
        date_counts=date_counts,
        current_date=current_date
    )

@app.route("/admin/update-status", methods=["POST"])
def update_status():
    """Update complaint status"""
    if "admin_id" not in session:
        return redirect(url_for("admin_login"))

    complaint_id = request.form.get("complaint_id")
    status = request.form.get("status")
    assigned_to = request.form.get("assigned_to", "")

    complaint = Complaint.query.get_or_404(complaint_id)
    old_status = complaint.status
    complaint.status = status
    if assigned_to:
        complaint.assigned_to = assigned_to
    if status == "Resolved" and not complaint.resolved_at:
        complaint.resolved_at = datetime.utcnow()
    
    db.session.commit()
    
    log_activity("admin", session["admin_id"], "update_status",
                f"Updated complaint #{complaint.id} from {old_status} to {status}")

    flash("Status updated successfully", "success")
    return redirect(url_for("admin_dashboard"))

@app.route("/admin/complaint/<int:complaint_id>/details")
def complaint_details(complaint_id):
    """Get complaint details as JSON"""
    if "admin_id" not in session:
        return jsonify({"error": "Unauthorized"}), 401
    
    complaint = Complaint.query.get_or_404(complaint_id)
    return jsonify(complaint.to_dict())

@app.route("/admin/export/complaints")
def export_complaints():
    """Export complaints to CSV"""
    if "admin_id" not in session:
        return redirect(url_for("admin_login"))
    
    output = io.StringIO()
    writer = csv.writer(output)
    
    writer.writerow(['ID', 'Tracking ID', 'Student', 'Department', 'Location', 
                    'Issue Type', 'Priority', 'Status', 'Assigned To', 'Image Count', 'Created At', 'Updated At'])
    
    complaints = Complaint.query.all()
    for complaint in complaints:
        writer.writerow([
            complaint.id,
            complaint.tracking_id,
            complaint.student_name,
            complaint.department,
            complaint.location,
            complaint.issue_type,
            complaint.priority,
            complaint.status,
            complaint.assigned_to or '',
            complaint.get_image_count(),
            complaint.created_at.strftime('%Y-%m-%d %H:%M'),
            complaint.updated_at.strftime('%Y-%m-%d %H:%M') if complaint.updated_at else ''
        ])
    
    output.seek(0)
    
    log_activity("admin", session["admin_id"], "export_complaints", "Exported complaints to CSV")
    
    return send_file(
        io.BytesIO(output.getvalue().encode()),
        mimetype='text/csv',
        as_attachment=True,
        download_name=f'complaints_export_{datetime.now().strftime("%Y%m%d_%H%M%S")}.csv'
    )

@app.route("/admin/complaint/<int:complaint_id>/reminder", methods=["POST"])
def send_reminder(complaint_id):
    """Send reminder for a complaint"""
    if "admin_id" not in session:
        return jsonify({"error": "Unauthorized"}), 401
    
    complaint = Complaint.query.get_or_404(complaint_id)
    
    log_activity("admin", session["admin_id"], "send_reminder",
                f"Sent reminder for complaint #{complaint.id}")
    
    return jsonify({
        "success": True, 
        "message": f"Reminder sent for complaint #{complaint.tracking_id}"
    })

@app.route("/admin/bulk-update", methods=["POST"])
def bulk_update():
    """Bulk update complaints"""
    if "admin_id" not in session:
        return jsonify({"error": "Unauthorized"}), 401
    
    data = request.get_json()
    complaint_ids = data.get("complaint_ids", [])
    status = data.get("status")
    assigned_to = data.get("assigned_to", "")
    
    if not complaint_ids or not status:
        return jsonify({"error": "Missing required fields"}), 400
    
    updated_count = 0
    for complaint_id in complaint_ids:
        complaint = Complaint.query.get(complaint_id)
        if complaint:
            old_status = complaint.status
            complaint.status = status
            if assigned_to:
                complaint.assigned_to = assigned_to
            if status == "Resolved" and not complaint.resolved_at:
                complaint.resolved_at = datetime.utcnow()
            db.session.commit()
            updated_count += 1
    
    log_activity("admin", session["admin_id"], "bulk_update",
                f"Bulk updated {updated_count} complaints to {status}")
    
    return jsonify({
        "success": True,
        "message": f"Updated {updated_count} complaints to {status}"
    })

@app.route("/admin/analytics")
def admin_analytics():
    """Advanced analytics page"""
    if "admin_id" not in session:
        return redirect(url_for("admin_login"))
    
    monthly_stats = []
    for i in range(5, -1, -1):
        month_start = datetime.now().replace(day=1)
        month_start = month_start - timedelta(days=30*i)
        month_end = month_start.replace(day=28) + timedelta(days=4)
        month_end = month_end.replace(day=1) - timedelta(days=1)
        
        total = Complaint.query.filter(
            Complaint.created_at >= month_start,
            Complaint.created_at <= month_end
        ).count()
        
        resolved = Complaint.query.filter(
            Complaint.status == 'Resolved',
            Complaint.created_at >= month_start,
            Complaint.created_at <= month_end
        ).count()
        
        monthly_stats.append({
            'month': month_start.strftime('%b %Y'),
            'total': total,
            'resolved': resolved,
            'rate': round((resolved / total * 100) if total > 0 else 0, 1)
        })
    
    dept_stats = db.session.query(
        Complaint.department,
        db.func.count(Complaint.id).label('total'),
        db.func.sum(db.case((Complaint.status == 'Resolved', 1), else_=0)).label('resolved')
    ).group_by(Complaint.department).all()
    
    top_issues = db.session.query(
        Complaint.issue_type,
        db.func.count(Complaint.id).label('count')
    ).group_by(Complaint.issue_type)\
     .order_by(db.desc('count'))\
     .limit(10).all()
    
    return render_template(
        "admin_analytics.html",
        admin_name=session["admin_name"],
        monthly_stats=monthly_stats,
        dept_stats=dept_stats,
        top_issues=top_issues
    )

@app.route("/admin/activity-logs")
def activity_logs():
    """View activity logs"""
    if "admin_id" not in session:
        return redirect(url_for("admin_login"))
    
    logs = ActivityLog.query.order_by(ActivityLog.timestamp.desc()).all()
    
    return render_template(
        "admin_activity_logs.html",
        admin_name=session["admin_name"],
        logs=logs
    )

@app.route("/admin/logout")
def admin_logout():
    """Admin logout"""
    if "admin_id" in session:
        log_activity("admin", session.get("admin_id"), "logout", 
                    f"Admin {session.get('admin_name')} logged out")
    session.clear()
    flash("Admin logged out", "info")
    return redirect(url_for("admin_login"))

# ================= IMAGE SERVING ROUTE ================= #
@app.route('/uploads/<path:filename>')
def serve_uploaded_file(filename):
    """Serve uploaded files securely"""
    from flask import send_from_directory
    return send_from_directory(UPLOAD_FOLDER, filename)

# ================= API ROUTES ================= #
@app.route("/api/dashboard-data")
def dashboard_data():
    """API endpoint for auto-refresh data"""
    if "admin_id" not in session:
        return jsonify({"error": "Unauthorized"}), 401
    
    pending_count = Complaint.query.filter_by(status="Pending").count()
    in_progress_count = Complaint.query.filter_by(status="In Progress").count()
    resolved_count = Complaint.query.filter_by(status="Resolved").count()
    total_complaints = Complaint.query.count()
    
    recent_activities = []
    logs = ActivityLog.query.order_by(ActivityLog.timestamp.desc()).limit(5).all()
    for log in logs:
        recent_activities.append({
            'user_type': log.user_type,
            'action': log.action,
            'details': log.details,
            'timestamp': log.timestamp.isoformat() if log.timestamp else None
        })
    
    return jsonify({
        'pending_count': pending_count,
        'in_progress_count': in_progress_count,
        'resolved_count': resolved_count,
        'total_complaints': total_complaints,
        'recent_activities': recent_activities
    })

# ================= MAIN ================= #
if __name__ == "__main__":
    with app.app_context():
        db.create_all()
        create_default_admin()
    app.run(debug=True, port=5002, host='0.0.0.0')