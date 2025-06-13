import json
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
import pytz
from dateutil import parser
import stripe
from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail
from twilio.rest import Client as TwilioClient

import firebase_admin
from firebase_admin import credentials, firestore, auth, storage
from firebase_functions import https_fn, scheduler_fn
from flask import Flask, request, jsonify
from flask_cors import CORS

# Initialize Firebase Admin SDK
if not firebase_admin._apps:
    firebase_admin.initialize_app()

db = firestore.client()
bucket = storage.bucket()

# Initialize Flask app for routing
app = Flask(__name__)
CORS(app)

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Utility functions
def get_current_timestamp():
    return datetime.utcnow()

def validate_auth_token(token: str) -> Dict[str, Any]:
    """Validate Firebase Auth token and return user info"""
    try:
        decoded_token = auth.verify_id_token(token)
        return {"success": True, "user": decoded_token}
    except Exception as e:
        return {"success": False, "error": str(e)}

def require_auth(required_roles: List[str] = None):
    """Decorator to require authentication and optionally specific roles"""
    def decorator(func):
        def wrapper(*args, **kwargs):
            auth_header = request.headers.get('Authorization')
            if not auth_header or not auth_header.startswith('Bearer '):
                return jsonify({"error": "Missing or invalid authorization header"}), 401
            
            token = auth_header.split(' ')[1]
            auth_result = validate_auth_token(token)
            
            if not auth_result["success"]:
                return jsonify({"error": "Invalid token"}), 401
            
            # Get user role from Firestore
            user_doc = db.collection('users').document(auth_result["user"]["uid"]).get()
            if not user_doc.exists:
                return jsonify({"error": "User not found"}), 404
            
            user_data = user_doc.to_dict()
            user_role = user_data.get('role', 'client')
            
            if required_roles and user_role not in required_roles:
                return jsonify({"error": "Insufficient permissions"}), 403
            
            # Add user info to request context
            request.user_id = auth_result["user"]["uid"]
            request.user_role = user_role
            request.user_data = user_data
            
            return func(*args, **kwargs)
        wrapper.__name__ = func.__name__
        return wrapper
    return decorator

# =============================================================================
# USER MANAGEMENT ENDPOINTS
# =============================================================================

@app.route('/api/users', methods=['POST'])
@require_auth(['admin'])
def create_user():
    """Create a new user account"""
    try:
        data = request.get_json()
        
        # Create Firebase Auth user
        user_record = auth.create_user(
            email=data['email'],
            password=data['password'],
            display_name=f"{data['profile']['firstName']} {data['profile']['lastName']}"
        )
        
        # Create user document in Firestore
        user_data = {
            'email': data['email'],
            'role': data.get('role', 'client'),
            'profile': data.get('profile', {}),
            'preferences': data.get('preferences', {
                'notificationMethod': 'email',
                'marketingConsent': False,
                'reminderSettings': {
                    'email': True,
                    'sms': False,
                    'hoursBefore': [24, 2]
                }
            }),
            'medicalInfo': data.get('medicalInfo', {}),
            'isActive': True,
            'createdAt': get_current_timestamp(),
            'updatedAt': get_current_timestamp()
        }
        
        db.collection('users').document(user_record.uid).set(user_data)
        
        return jsonify({
            "success": True,
            "userId": user_record.uid,
            "message": "User created successfully"
        }), 201
        
    except Exception as e:
        logger.error(f"Error creating user: {str(e)}")
        return jsonify({"error": str(e)}), 400

@app.route('/api/users/<user_id>', methods=['GET'])
@require_auth()
def get_user(user_id):
    """Get user details"""
    try:
        # Users can only access their own data unless they're admin
        if request.user_role != 'admin' and request.user_id != user_id:
            return jsonify({"error": "Access denied"}), 403
        
        user_doc = db.collection('users').document(user_id).get()
        if not user_doc.exists:
            return jsonify({"error": "User not found"}), 404
        
        user_data = user_doc.to_dict()
        # Remove sensitive data
        user_data.pop('passwordHash', None)
        
        return jsonify({"success": True, "user": user_data}), 200
        
    except Exception as e:
        logger.error(f"Error getting user: {str(e)}")
        return jsonify({"error": str(e)}), 400

@app.route('/api/users/<user_id>', methods=['PUT'])
@require_auth()
def update_user(user_id):
    """Update user details"""
    try:
        # Users can only update their own data unless they're admin
        if request.user_role != 'admin' and request.user_id != user_id:
            return jsonify({"error": "Access denied"}), 403
        
        data = request.get_json()
        update_data = {
            'updatedAt': get_current_timestamp()
        }
        
        # Only allow certain fields to be updated
        allowed_fields = ['profile', 'preferences', 'medicalInfo']
        if request.user_role == 'admin':
            allowed_fields.extend(['role', 'isActive'])
        
        for field in allowed_fields:
            if field in data:
                update_data[field] = data[field]
        
        db.collection('users').document(user_id).update(update_data)
        
        return jsonify({"success": True, "message": "User updated successfully"}), 200
        
    except Exception as e:
        logger.error(f"Error updating user: {str(e)}")
        return jsonify({"error": str(e)}), 400

# =============================================================================
# SERVICE PACKAGE ENDPOINTS
# =============================================================================

@app.route('/api/services', methods=['GET'])
def get_services():
    """Get all active service packages"""
    try:
        query = db.collection('servicePackages').where('isActive', '==', True)
        
        # Filter by category if specified
        category = request.args.get('category')
        if category:
            query = query.where('category', '==', category)
        
        # Filter featured services for landing page
        featured_only = request.args.get('featured') == 'true'
        if featured_only:
            query = query.where('isFeatured', '==', True)
        
        docs = query.order_by('displayOrder').stream()
        services = []
        for doc in docs:
            service_data = doc.to_dict()
            service_data['id'] = doc.id
            services.append(service_data)
        
        return jsonify({"success": True, "services": services}), 200
        
    except Exception as e:
        logger.error(f"Error getting services: {str(e)}")
        return jsonify({"error": str(e)}), 400

@app.route('/api/services', methods=['POST'])
@require_auth(['admin'])
def create_service():
    """Create a new service package"""
    try:
        data = request.get_json()
        
        service_data = {
            'name': data['name'],
            'description': data['description'],
            'price': data['price'],
            'durationMinutes': data['durationMinutes'],
            'imageUrl': data.get('imageUrl', ''),
            'features': data.get('features', []),
            'category': data['category'],
            'isFeatured': data.get('isFeatured', False),
            'displayOrder': data.get('displayOrder', 0),
            'isActive': True,
            'bookingCount': 0,
            'totalRevenue': 0,
            'createdBy': request.user_id,
            'createdAt': get_current_timestamp(),
            'updatedAt': get_current_timestamp()
        }
        
        doc_ref = db.collection('servicePackages').add(service_data)
        
        return jsonify({
            "success": True,
            "serviceId": doc_ref[1].id,
            "message": "Service created successfully"
        }), 201
        
    except Exception as e:
        logger.error(f"Error creating service: {str(e)}")
        return jsonify({"error": str(e)}), 400

@app.route('/api/services/<service_id>', methods=['PUT'])
@require_auth(['admin'])
def update_service(service_id):
    """Update a service package"""
    try:
        data = request.get_json()
        
        update_data = {
            'updatedAt': get_current_timestamp()
        }
        
        allowed_fields = ['name', 'description', 'price', 'durationMinutes', 
                         'imageUrl', 'features', 'category', 'isFeatured', 
                         'displayOrder', 'isActive']
        
        for field in allowed_fields:
            if field in data:
                update_data[field] = data[field]
        
        db.collection('servicePackages').document(service_id).update(update_data)
        
        return jsonify({"success": True, "message": "Service updated successfully"}), 200
        
    except Exception as e:
        logger.error(f"Error updating service: {str(e)}")
        return jsonify({"error": str(e)}), 400

# =============================================================================
# APPOINTMENT MANAGEMENT ENDPOINTS
# =============================================================================

@app.route('/api/appointments', methods=['POST'])
@require_auth()
def create_appointment():
    """Create a new appointment"""
    try:
        data = request.get_json()
        
        # Get service details
        service_doc = db.collection('servicePackages').document(data['serviceId']).get()
        if not service_doc.exists:
            return jsonify({"error": "Service not found"}), 404
        
        service_data = service_doc.to_dict()
        
        # Get client details
        client_doc = db.collection('users').document(data['clientId']).get()
        if not client_doc.exists:
            return jsonify({"error": "Client not found"}), 404
        
        client_data = client_doc.to_dict()
        
        # Parse datetime
        appointment_datetime = parser.parse(data['dateTime'])
        
        appointment_data = {
            'client': {
                'id': data['clientId'],
                'name': f"{client_data['profile']['firstName']} {client_data['profile']['lastName']}",
                'email': client_data['email'],
                'phone': client_data['profile'].get('phone', '')
            },
            'service': {
                'id': data['serviceId'],
                'name': service_data['name'],
                'price': service_data['price'],
                'duration': service_data['durationMinutes']
            },
            'dateTime': {
                'date': appointment_datetime,
                'time': data.get('time', appointment_datetime.strftime('%H:%M')),
                'timezone': data.get('timezone', 'UTC')
            },
            'status': 'confirmed',
            'payment': {
                'status': 'pending',
                'totalPrice': service_data['price'],
                'discount': data.get('discount', {})
            },
            'addons': data.get('addons', []),
            'notes': [],
            'notifications': [],
            'timeline': [{
                'event': 'created',
                'timestamp': get_current_timestamp(),
                'userId': request.user_id,
                'notes': 'Appointment created'
            }],
            'referralSource': data.get('referralSource', ''),
            'createdAt': get_current_timestamp(),
            'updatedAt': get_current_timestamp()
        }
        
        doc_ref = db.collection('appointments').add(appointment_data)
        
        # Schedule notifications
        schedule_appointment_notifications(doc_ref[1].id, appointment_data)
        
        return jsonify({
            "success": True,
            "appointmentId": doc_ref[1].id,
            "message": "Appointment created successfully"
        }), 201
        
    except Exception as e:
        logger.error(f"Error creating appointment: {str(e)}")
        return jsonify({"error": str(e)}), 400

@app.route('/api/appointments', methods=['GET'])
@require_auth()
def get_appointments():
    """Get appointments (filtered by user role)"""
    try:
        query = db.collection('appointments')
        
        # Clients can only see their own appointments
        if request.user_role == 'client':
            query = query.where('client.id', '==', request.user_id)
        
        # Filter by date range if specified
        start_date = request.args.get('startDate')
        end_date = request.args.get('endDate')
        
        if start_date:
            start_dt = parser.parse(start_date)
            query = query.where('dateTime.date', '>=', start_dt)
        
        if end_date:
            end_dt = parser.parse(end_date)
            query = query.where('dateTime.date', '<=', end_dt)
        
        # Filter by status if specified
        status = request.args.get('status')
        if status:
            query = query.where('status', '==', status)
        
        docs = query.order_by('dateTime.date', direction=firestore.Query.DESCENDING).stream()
        appointments = []
        for doc in docs:
            appointment_data = doc.to_dict()
            appointment_data['id'] = doc.id
            appointments.append(appointment_data)
        
        return jsonify({"success": True, "appointments": appointments}), 200
        
    except Exception as e:
        logger.error(f"Error getting appointments: {str(e)}")
        return jsonify({"error": str(e)}), 400

@app.route('/api/appointments/<appointment_id>', methods=['PUT'])
@require_auth()
def update_appointment(appointment_id):
    """Update appointment details"""
    try:
        data = request.get_json()
        
        # Get current appointment
        appointment_doc = db.collection('appointments').document(appointment_id).get()
        if not appointment_doc.exists:
            return jsonify({"error": "Appointment not found"}), 404
        
        appointment_data = appointment_doc.to_dict()
        
        # Check permissions
        if (request.user_role == 'client' and 
            appointment_data['client']['id'] != request.user_id):
            return jsonify({"error": "Access denied"}), 403
        
        update_data = {
            'updatedAt': get_current_timestamp()
        }
        
        # Handle status changes
        if 'status' in data and data['status'] != appointment_data['status']:
            update_data['status'] = data['status']
            
            # Add timeline entry
            timeline_entry = {
                'event': data['status'],
                'timestamp': get_current_timestamp(),
                'userId': request.user_id,
                'notes': data.get('statusNote', '')
            }
            
            current_timeline = appointment_data.get('timeline', [])
            current_timeline.append(timeline_entry)
            update_data['timeline'] = current_timeline
            
            # Set completion/cancellation timestamps
            if data['status'] == 'completed':
                update_data['completedAt'] = get_current_timestamp()
            elif data['status'] == 'cancelled':
                update_data['cancelledAt'] = get_current_timestamp()
                update_data['cancellationReason'] = data.get('cancellationReason', '')
        
        # Handle payment updates (admin/technician only)
        if request.user_role in ['admin', 'technician'] and 'payment' in data:
            current_payment = appointment_data.get('payment', {})
            current_payment.update(data['payment'])
            update_data['payment'] = current_payment
        
        # Handle notes
        if 'note' in data:
            note_entry = {
                'type': data.get('noteType', 'service'),
                'content': data['note'],
                'isPrivate': data.get('isPrivateNote', False),
                'createdBy': request.user_id,
                'createdAt': get_current_timestamp()
            }
            
            current_notes = appointment_data.get('notes', [])
            current_notes.append(note_entry)
            update_data['notes'] = current_notes
        
        db.collection('appointments').document(appointment_id).update(update_data)
        
        return jsonify({"success": True, "message": "Appointment updated successfully"}), 200
        
    except Exception as e:
        logger.error(f"Error updating appointment: {str(e)}")
        return jsonify({"error": str(e)}), 400

# =============================================================================
# SITE SETTINGS ENDPOINTS
# =============================================================================

@app.route('/api/site-settings', methods=['GET'])
def get_site_settings():
    """Get site settings (public endpoint for landing page)"""
    try:
        settings_doc = db.collection('siteSettings').document('main').get()
        if not settings_doc.exists:
            return jsonify({"error": "Site settings not found"}), 404
        
        settings_data = settings_doc.to_dict()
        
        # Remove sensitive data for public access
        if 'integrations' in settings_data:
            integrations = settings_data['integrations']
            # Only keep public keys
            if 'stripe' in integrations:
                integrations['stripe'] = {
                    'publishableKey': integrations['stripe'].get('publishableKey', '')
                }
            # Remove other sensitive integration data
            for key in ['email', 'sms']:
                if key in integrations:
                    del integrations[key]
        
        return jsonify({"success": True, "settings": settings_data}), 200
        
    except Exception as e:
        logger.error(f"Error getting site settings: {str(e)}")
        return jsonify({"error": str(e)}), 400

@app.route('/api/site-settings', methods=['PUT'])
@require_auth(['admin'])
def update_site_settings():
    """Update site settings"""
    try:
        data = request.get_json()
        
        update_data = {
            'updatedAt': get_current_timestamp(),
            'updatedBy': request.user_id
        }
        
        # Merge with existing data
        for key, value in data.items():
            update_data[key] = value
        
        db.collection('siteSettings').document('main').set(update_data, merge=True)
        
        return jsonify({"success": True, "message": "Site settings updated successfully"}), 200
        
    except Exception as e:
        logger.error(f"Error updating site settings: {str(e)}")
        return jsonify({"error": str(e)}), 400

# =============================================================================
# TESTIMONIALS ENDPOINTS
# =============================================================================

@app.route('/api/testimonials', methods=['GET'])
def get_testimonials():
    """Get approved testimonials"""
    try:
        query = db.collection('testimonials').where('isApproved', '==', True)
        
        featured_only = request.args.get('featured') == 'true'
        if featured_only:
            query = query.where('isFeatured', '==', True)
        
        docs = query.order_by('displayOrder').stream()
        testimonials = []
        for doc in docs:
            testimonial_data = doc.to_dict()
            testimonial_data['id'] = doc.id
            testimonials.append(testimonial_data)
        
        return jsonify({"success": True, "testimonials": testimonials}), 200
        
    except Exception as e:
        logger.error(f"Error getting testimonials: {str(e)}")
        return jsonify({"error": str(e)}), 400

@app.route('/api/testimonials', methods=['POST'])
@require_auth()
def create_testimonial():
    """Create a new testimonial"""
    try:
        data = request.get_json()
        
        testimonial_data = {
            'clientName': data['clientName'],
            'rating': data['rating'],
            'reviewText': data['reviewText'],
            'serviceReceived': data.get('serviceReceived', ''),
            'appointmentId': data.get('appointmentId'),
            'isFeatured': False,
            'isApproved': request.user_role == 'admin',  # Auto-approve if admin
            'displayOrder': data.get('displayOrder', 0),
            'source': 'website',
            'createdAt': get_current_timestamp()
        }
        
        if request.user_role == 'admin':
            testimonial_data['approvedAt'] = get_current_timestamp()
            testimonial_data['approvedBy'] = request.user_id
        
        doc_ref = db.collection('testimonials').add(testimonial_data)
        
        return jsonify({
            "success": True,
            "testimonialId": doc_ref[1].id,
            "message": "Testimonial created successfully"
        }), 201
        
    except Exception as e:
        logger.error(f"Error creating testimonial: {str(e)}")
        return jsonify({"error": str(e)}), 400

# =============================================================================
# PROMO CODES ENDPOINTS
# =============================================================================

@app.route('/api/promo-codes/validate', methods=['POST'])
@require_auth()
def validate_promo_code():
    """Validate a promo code"""
    try:
        data = request.get_json()
        code = data.get('code', '').upper()
        service_ids = data.get('serviceIds', [])
        order_amount = data.get('orderAmount', 0)
        
        # Find promo code
        promo_docs = db.collection('promoCodes').where('code', '==', code).where('isActive', '==', True).stream()
        promo_doc = None
        for doc in promo_docs:
            promo_doc = doc
            break
        
        if not promo_doc:
            return jsonify({"success": False, "error": "Invalid promo code"}), 400
        
        promo_data = promo_doc.to_dict()
        now = get_current_timestamp()
        
        # Check validity period
        if promo_data['validFrom'] > now or promo_data['validUntil'] < now:
            return jsonify({"success": False, "error": "Promo code expired"}), 400
        
        # Check usage limit
        if promo_data['usageCount'] >= promo_data['usageLimit']:
            return jsonify({"success": False, "error": "Promo code usage limit reached"}), 400
        
        # Check minimum order amount
        if order_amount < promo_data.get('minOrderAmount', 0):
            return jsonify({"success": False, "error": f"Minimum order amount is ${promo_data['minOrderAmount']}"}), 400
        
        # Check applicable services
        applicable_services = promo_data.get('applicableServices', [])
        if applicable_services and not any(sid in applicable_services for sid in service_ids):
            return jsonify({"success": False, "error": "Promo code not applicable to selected services"}), 400
        
        # Calculate discount
        discount_amount = 0
        if promo_data['discountType'] == 'percentage':
            discount_amount = order_amount * (promo_data['discountValue'] / 100)
        else:  # fixed_amount
            discount_amount = promo_data['discountValue']
        
        # Apply max discount limit
        max_discount = promo_data.get('maxDiscountAmount', float('inf'))
        discount_amount = min(discount_amount, max_discount)
        
        return jsonify({
            "success": True,
            "discount": {
                "amount": discount_amount,
                "percentage": promo_data['discountValue'] if promo_data['discountType'] == 'percentage' else None,
                "code": code,
                "description": promo_data['description']
            }
        }), 200
        
    except Exception as e:
        logger.error(f"Error validating promo code: {str(e)}")
        return jsonify({"error": str(e)}), 400

# =============================================================================
# ANALYTICS ENDPOINTS
# =============================================================================

@app.route('/api/analytics/dashboard', methods=['GET'])
@require_auth(['admin', 'technician'])
def get_dashboard_analytics():
    """Get dashboard analytics data"""
    try:
        # Get date range
        end_date = datetime.utcnow()
        start_date = end_date - timedelta(days=30)  # Last 30 days
        
        # Get appointments in date range
        appointments_query = (db.collection('appointments')
                            .where('dateTime.date', '>=', start_date)
                            .where('dateTime.date', '<=', end_date))
        
        appointments = [doc.to_dict() for doc in appointments_query.stream()]
        
        # Calculate metrics
        total_appointments = len(appointments)
        total_revenue = sum(apt.get('payment', {}).get('totalPrice', 0) 
                          for apt in appointments 
                          if apt.get('payment', {}).get('status') == 'paid')
        
        completed_appointments = [apt for apt in appointments if apt.get('status') == 'completed']
        cancelled_appointments = [apt for apt in appointments if apt.get('status') == 'cancelled']
        
        completion_rate = (len(completed_appointments) / total_appointments * 100) if total_appointments > 0 else 0
        cancellation_rate = (len(cancelled_appointments) / total_appointments * 100) if total_appointments > 0 else 0
        
        # Service breakdown
        service_stats = {}
        for apt in appointments:
            service_name = apt.get('service', {}).get('name', 'Unknown')
            if service_name not in service_stats:
                service_stats[service_name] = {'bookings': 0, 'revenue': 0}
            
            service_stats[service_name]['bookings'] += 1
            if apt.get('payment', {}).get('status') == 'paid':
                service_stats[service_name]['revenue'] += apt.get('payment', {}).get('totalPrice', 0)
        
        analytics_data = {
            'totalAppointments': total_appointments,
            'totalRevenue': total_revenue,
            'averageBookingValue': total_revenue / total_appointments if total_appointments > 0 else 0,
            'completionRate': completion_rate,
            'cancellationRate': cancellation_rate,
            'serviceBreakdown': [
                {'serviceName': name, **stats} 
                for name, stats in service_stats.items()
            ]
        }
        
        return jsonify({"success": True, "analytics": analytics_data}), 200
        
    except Exception as e:
        logger.error(f"Error getting analytics: {str(e)}")
        return jsonify({"error": str(e)}), 400

# =============================================================================
# MEDIA LIBRARY ENDPOINTS
# =============================================================================

@app.route('/api/media/upload', methods=['POST'])
@require_auth(['admin'])
def upload_media():
    """Upload media file to Cloud Storage"""
    try:
        if 'file' not in request.files:
            return jsonify({"error": "No file provided"}), 400
        
        file = request.files['file']
        if file.filename == '':
            return jsonify({"error": "No file selected"}), 400
        
        # Generate unique filename
        timestamp = datetime.utcnow().strftime('%Y%m%d_%H%M%S')
        filename = f"{timestamp}_{file.filename}"
        
        # Upload to Cloud Storage
        blob = bucket.blob(f"media/{filename}")
        blob.upload_from_file(file)
        blob.make_public()
        
        # Save media info to Firestore
        media_data = {
            'filename': filename,
            'originalFilename': file.filename,
            'filePath': f"media/{filename}",
            'fileSize': blob.size,
            'mimeType': blob.content_type,
            'altText': request.form.get('altText', ''),
            'caption': request.form.get('caption', ''),
            'tags': request.form.getlist('tags'),
            'usageContext': request.form.get('usageContext', ''),
            'usageCount': 0,
            'uploadedBy': request.user_id,
            'createdAt': get_current_timestamp()
        }
        
        doc_ref = db.collection('mediaLibrary').add(media_data)
        
        return jsonify({
            "success": True,
            "mediaId": doc_ref[1].id,
            "publicUrl": blob.public_url,
            "message": "File uploaded successfully"
        }), 201
        
    except Exception as e:
        logger.error(f"Error uploading media: {str(e)}")
        return jsonify({"error": str(e)}), 400

# =============================================================================
# NOTIFICATION FUNCTIONS
# =============================================================================

def schedule_appointment_notifications(appointment_id: str, appointment_data: Dict):
    """Schedule notification reminders for an appointment"""
    try:
        client_id = appointment_data['client']['id']
        appointment_datetime = appointment_data['dateTime']['date']
        
        # Get client preferences
        client_doc = db.collection('users').document(client_id).get()
        if not client_doc.exists:
            return
        
        client_data = client_doc.to_dict()
        reminder_settings = client_data.get('preferences', {}).get('reminderSettings', {})
        hours_before = reminder_settings.get('hoursBefore', [24, 2])
        
        notifications = []
        
        for hours in hours_before:
            reminder_time = appointment_datetime - timedelta(hours=hours)
            
            if reminder_settings.get('email', True):
                notifications.append({
                    'type': f'reminder_{hours}h',
                    'method': 'email',
                    'scheduledFor': reminder_time,
                    'status': 'pending'
                })
            
            if reminder_settings.get('sms', False):
                notifications.append({
                    'type': f'reminder_{hours}h',
                    'method': 'sms',
                    'scheduledFor': reminder_time,
                    'status': 'pending'
                })
        
        # Add confirmation notification
        notifications.append({
            'type': 'confirmation',
            'method': client_data.get('preferences', {}).get('notificationMethod', 'email'),
            'scheduledFor': get_current_timestamp(),
            'status': 'pending'
        })
        
        # Update appointment with scheduled notifications
        db.collection('appointments').document(appointment_id).update({
            'notifications': notifications
        })
        
    except Exception as e:
        logger.error(f"Error scheduling notifications: {str(e)}")

def send_email_notification(to_email: str, subject: str, content: str, template_type: str = 'general'):
    """Send email notification using SendGrid"""
    try:
        # Get email settings from site settings
        settings_doc = db.collection('siteSettings').document('main').get()
        if not settings_doc.exists:
            logger.error("Site settings not found for email configuration")
            return False
        
        settings = settings_doc.to_dict()
        email_config = settings.get('integrations', {}).get('email', {})
        
        if not email_config.get('apiKey'):
            logger.error("SendGrid API key not configured")
            return False
        
        sg = SendGridAPIClient(api_key=email_config['apiKey'])
        
        message = Mail(
            from_email=email_config.get('fromEmail', 'noreply@example.com'),
            to_emails=to_email,
            subject=subject,
            html_content=content
        )
        
        response = sg.send(message)
        logger.info(f"Email sent successfully: {response.status_code}")
        return True
        
    except Exception as e:
        logger.error(f"Error sending email: {str(e)}")
        return False

def send_sms_notification(to_phone: str, message: str):
    """Send SMS notification using Twilio"""
    try:
        # Get SMS settings from site settings
        settings_doc = db.collection('siteSettings').document('main').get()
        if not settings_doc.exists:
            logger.error("Site settings not found for SMS configuration")
            return False
        
        settings = settings_doc.to_dict()
        sms_config = settings.get('integrations', {}).get('sms', {})
        
        if not sms_config.get('apiKey'):
            logger.error("Twilio API key not configured")
            return False
        
        client = TwilioClient(sms_config['apiKey'], sms_config.get('authToken'))
        
        message = client.messages.create(
            body=message,
            from_=sms_config.get('fromNumber'),
            to=to_phone
        )
        
        logger.info(f"SMS sent successfully: {message.sid}")
        return True
        
    except Exception as e:
        logger.error(f"Error sending SMS: {str(e)}")
        return False

# =============================================================================
# SCHEDULED FUNCTIONS
# =============================================================================

@scheduler_fn.on_schedule(schedule="every 15 minutes")
def process_pending_notifications(req):
    """Process pending notifications that are due to be sent"""
    try:
        current_time = get_current_timestamp()
        
        # Find appointments with pending notifications
        appointments_query = db.collection('appointments').where('notifications', '!=', [])
        appointments = appointments_query.stream()
        
        for appointment_doc in appointments:
            appointment_data = appointment_doc.to_dict()
            notifications = appointment_data.get('notifications', [])
            updated_notifications = []
            notifications_updated = False
            
            for notification in notifications:
                if (notification['status'] == 'pending' and 
                    notification['scheduledFor'] <= current_time):
                    
                    # Send the notification
                    success = False
                    
                    if notification['method'] == 'email':
                        # Generate email content based on notification type
                        subject, content = generate_notification_content(
                            notification['type'], 
                            appointment_data, 
                            'email'
                        )
                        success = send_email_notification(
                            appointment_data['client']['email'],
                            subject,
                            content,
                            notification['type']
                        )
                    
                    elif notification['method'] == 'sms':
                        # Generate SMS content
                        _, sms_content = generate_notification_content(
                            notification['type'],
                            appointment_data,
                            'sms'
                        )
                        success = send_sms_notification(
                            appointment_data['client']['phone'],
                            sms_content
                        )
                    
                    # Update notification status
                    notification['status'] = 'sent' if success else 'failed'
                    notification['sentAt'] = current_time
                    notifications_updated = True
                
                updated_notifications.append(notification)
            
            # Update appointment if notifications were processed
            if notifications_updated:
                db.collection('appointments').document(appointment_doc.id).update({
                    'notifications': updated_notifications
                })
        
        logger.info("Notification processing completed")
        return {"success": True}
        
    except Exception as e:
        logger.error(f"Error processing notifications: {str(e)}")
        return {"error": str(e)}

def generate_notification_content(notification_type: str, appointment_data: Dict, format_type: str):
    """Generate notification content based on type and format"""
    client_name = appointment_data['client']['name']
    service_name = appointment_data['service']['name']
    appointment_date = appointment_data['dateTime']['date'].strftime('%B %d, %Y')
    appointment_time = appointment_data['dateTime']['time']
    
    if notification_type == 'confirmation':
        if format_type == 'email':
            subject = f"Appointment Confirmation - {service_name}"
            content = f"""
            <html>
            <body>
                <h2>Appointment Confirmed!</h2>
                <p>Dear {client_name},</p>
                <p>Your appointment has been confirmed for:</p>
                <ul>
                    <li><strong>Service:</strong> {service_name}</li>
                    <li><strong>Date:</strong> {appointment_date}</li>
                    <li><strong>Time:</strong> {appointment_time}</li>
                </ul>
                <p>We look forward to seeing you!</p>
                <p>Best regards,<br>Your Beauty Team</p>
            </body>
            </html>
            """
        else:  # SMS
            subject = ""
            content = f"Hi {client_name}! Your {service_name} appointment is confirmed for {appointment_date} at {appointment_time}. See you soon!"
    
    elif 'reminder' in notification_type:
        hours = notification_type.split('_')[1].replace('h', '')
        if format_type == 'email':
            subject = f"Reminder: Upcoming Appointment - {service_name}"
            content = f"""
            <html>
            <body>
                <h2>Appointment Reminder</h2>
                <p>Dear {client_name},</p>
                <p>This is a friendly reminder that you have an appointment in {hours} hours:</p>
                <ul>
                    <li><strong>Service:</strong> {service_name}</li>
                    <li><strong>Date:</strong> {appointment_date}</li>
                    <li><strong>Time:</strong> {appointment_time}</li>
                </ul>
                <p>Please arrive 10 minutes early. If you need to reschedule, please contact us as soon as possible.</p>
                <p>Best regards,<br>Your Beauty Team</p>
            </body>
            </html>
            """
        else:  # SMS
            subject = ""
            content = f"Reminder: Your {service_name} appointment is in {hours} hours on {appointment_date} at {appointment_time}. Please arrive 10 mins early!"
    
    return subject, content

# =============================================================================
# ANALYTICS SCHEDULED FUNCTIONS
# =============================================================================

@scheduler_fn.on_schedule(schedule="every day 01:00")
def generate_daily_analytics(req):
    """Generate daily analytics data"""
    try:
        yesterday = datetime.utcnow().date() - timedelta(days=1)
        start_of_day = datetime.combine(yesterday, datetime.min.time())
        end_of_day = datetime.combine(yesterday, datetime.max.time())
        
        # Get appointments for yesterday
        appointments_query = (db.collection('appointments')
                            .where('dateTime.date', '>=', start_of_day)
                            .where('dateTime.date', '<=', end_of_day))
        
        appointments = [doc.to_dict() for doc in appointments_query.stream()]
        
        # Calculate metrics
        total_appointments = len(appointments)
        completed_appointments = [apt for apt in appointments if apt.get('status') == 'completed']
        cancelled_appointments = [apt for apt in appointments if apt.get('status') == 'cancelled']
        
        total_revenue = sum(apt.get('payment', {}).get('totalPrice', 0) 
                          for apt in appointments 
                          if apt.get('payment', {}).get('status') == 'paid')
        
        # Service breakdown
        service_breakdown = {}
        for apt in appointments:
            service_id = apt.get('service', {}).get('id')
            service_name = apt.get('service', {}).get('name', 'Unknown')
            
            if service_id not in service_breakdown:
                service_breakdown[service_id] = {
                    'serviceId': service_id,
                    'serviceName': service_name,
                    'bookings': 0,
                    'revenue': 0
                }
            
            service_breakdown[service_id]['bookings'] += 1
            if apt.get('payment', {}).get('status') == 'paid':
                service_breakdown[service_id]['revenue'] += apt.get('payment', {}).get('totalPrice', 0)
        
        # Payment method breakdown
        payment_methods = {'stripe': 0, 'cash': 0, 'bankTransfer': 0}
        for apt in appointments:
            payment_method = apt.get('payment', {}).get('method', 'stripe')
            if payment_method in payment_methods:
                payment_methods[payment_method] += apt.get('payment', {}).get('totalPrice', 0)
        
        analytics_data = {
            'type': 'daily',
            'date': start_of_day,
            'metrics': {
                'totalAppointments': total_appointments,
                'totalRevenue': total_revenue,
                'averageBookingValue': total_revenue / total_appointments if total_appointments > 0 else 0,
                'completionRate': (len(completed_appointments) / total_appointments * 100) if total_appointments > 0 else 0,
                'cancellationRate': (len(cancelled_appointments) / total_appointments * 100) if total_appointments > 0 else 0,
                'noShowRate': 0,  # Calculate based on no-show status
                'serviceBreakdown': list(service_breakdown.values()),
                'paymentMethodBreakdown': payment_methods
            },
            'generatedAt': get_current_timestamp()
        }
        
        # Save analytics data
        db.collection('analytics').add(analytics_data)
        
        logger.info(f"Daily analytics generated for {yesterday}")
        return {"success": True}
        
    except Exception as e:
        logger.error(f"Error generating daily analytics: {str(e)}")
        return {"error": str(e)}

# =============================================================================
# PAYMENT PROCESSING ENDPOINTS
# =============================================================================

@app.route('/api/payments/create-intent', methods=['POST'])
@require_auth()
def create_payment_intent():
    """Create Stripe payment intent for appointment"""
    try:
        data = request.get_json()
        appointment_id = data.get('appointmentId')
        
        # Get appointment details
        appointment_doc = db.collection('appointments').document(appointment_id).get()
        if not appointment_doc.exists:
            return jsonify({"error": "Appointment not found"}), 404
        
        appointment_data = appointment_doc.to_dict()
        
        # Check if user can pay for this appointment
        if (request.user_role == 'client' and 
            appointment_data['client']['id'] != request.user_id):
            return jsonify({"error": "Access denied"}), 403
        
        # Get Stripe configuration
        settings_doc = db.collection('siteSettings').document('main').get()
        if not settings_doc.exists:
            return jsonify({"error": "Payment configuration not found"}), 500
        
        stripe_config = settings_doc.to_dict().get('integrations', {}).get('stripe', {})
        if not stripe_config.get('secretKey'):
            return jsonify({"error": "Stripe not configured"}), 500
        
        stripe.api_key = stripe_config['secretKey']
        
        # Calculate total amount
        total_amount = appointment_data['payment']['totalPrice']
        discount = appointment_data['payment'].get('discount', {})
        if discount.get('amount'):
            total_amount -= discount['amount']
        
        # Create payment intent
        intent = stripe.PaymentIntent.create(
            amount=int(total_amount * 100),  # Stripe uses cents
            currency='usd',
            metadata={
                'appointment_id': appointment_id,
                'client_id': appointment_data['client']['id']
            }
        )
        
        # Update appointment with payment intent ID
        db.collection('appointments').document(appointment_id).update({
            'payment.stripePaymentIntentId': intent.id,
            'updatedAt': get_current_timestamp()
        })
        
        return jsonify({
            "success": True,
            "clientSecret": intent.client_secret,
            "amount": total_amount
        }), 200
        
    except Exception as e:
        logger.error(f"Error creating payment intent: {str(e)}")
        return jsonify({"error": str(e)}), 400

@app.route('/api/payments/webhook', methods=['POST'])
def stripe_webhook():
    """Handle Stripe webhook events"""
    try:
        payload = request.get_data()
        sig_header = request.headers.get('Stripe-Signature')
        
        # Get webhook secret from settings
        settings_doc = db.collection('siteSettings').document('main').get()
        if not settings_doc.exists:
            return jsonify({"error": "Configuration not found"}), 500
        
        webhook_secret = settings_doc.to_dict().get('integrations', {}).get('stripe', {}).get('webhookSecret')
        if not webhook_secret:
            return jsonify({"error": "Webhook secret not configured"}), 500
        
        # Verify webhook signature
        try:
            event = stripe.Webhook.construct_event(payload, sig_header, webhook_secret)
        except ValueError:
            return jsonify({"error": "Invalid payload"}), 400
        except stripe.error.SignatureVerificationError:
            return jsonify({"error": "Invalid signature"}), 400
        
        # Handle payment success
        if event['type'] == 'payment_intent.succeeded':
            payment_intent = event['data']['object']
            appointment_id = payment_intent['metadata']['appointment_id']
            
            # Update appointment payment status
            db.collection('appointments').document(appointment_id).update({
                'payment.status': 'paid',
                'payment.method': 'stripe',
                'payment.processedAt': get_current_timestamp(),
                'updatedAt': get_current_timestamp()
            })
            
            logger.info(f"Payment successful for appointment {appointment_id}")
        
        # Handle payment failure
        elif event['type'] == 'payment_intent.payment_failed':
            payment_intent = event['data']['object']
            appointment_id = payment_intent['metadata']['appointment_id']
            
            # Update appointment payment status
            db.collection('appointments').document(appointment_id).update({
                'payment.status': 'failed',
                'updatedAt': get_current_timestamp()
            })
            
            logger.warning(f"Payment failed for appointment {appointment_id}")
        
        return jsonify({"success": True}), 200
        
    except Exception as e:
        logger.error(f"Error processing webhook: {str(e)}")
        return jsonify({"error": str(e)}), 400

# =============================================================================
# CONTENT MANAGEMENT ENDPOINTS
# =============================================================================

@app.route('/api/content/<page_slug>', methods=['GET'])
def get_page_content(page_slug):
    """Get content blocks for a specific page"""
    try:
        query = (db.collection('contentBlocks')
                .where('pageSlug', '==', page_slug)
                .where('isActive', '==', True)
                .order_by('displayOrder'))
        
        docs = query.stream()
        content_blocks = []
        for doc in docs:
            block_data = doc.to_dict()
            block_data['id'] = doc.id
            content_blocks.append(block_data)
        
        return jsonify({"success": True, "contentBlocks": content_blocks}), 200
        
    except Exception as e:
        logger.error(f"Error getting page content: {str(e)}")
        return jsonify({"error": str(e)}), 400

@app.route('/api/content/<page_slug>/blocks', methods=['POST'])
@require_auth(['admin'])
def create_content_block(page_slug):
    """Create a new content block"""
    try:
        data = request.get_json()
        
        block_data = {
            'pageSlug': page_slug,
            'blockType': data['blockType'],
            'blockName': data['blockName'],
            'content': data['content'],
            'displayOrder': data.get('displayOrder', 0),
            'isActive': True,
            'responsive': data.get('responsive', {}),
            'createdAt': get_current_timestamp(),
            'updatedAt': get_current_timestamp(),
            'createdBy': request.user_id
        }
        
        doc_ref = db.collection('contentBlocks').add(block_data)
        
        return jsonify({
            "success": True,
            "blockId": doc_ref[1].id,
            "message": "Content block created successfully"
        }), 201
        
    except Exception as e:
        logger.error(f"Error creating content block: {str(e)}")
        return jsonify({"error": str(e)}), 400

# =============================================================================
# MAIN CLOUD FUNCTION ENTRY POINT
# =============================================================================

@https_fn.on_request(cors=True)
def api(req):
    """Main API entry point for Cloud Functions v2"""
    with app.request_context(req.environ):
        try:
            return app.full_dispatch_request()
        except Exception as e:
            logger.error(f"Unhandled error in API: {str(e)}")
            return jsonify({"error": "Internal server error"}), 500

# =============================================================================
# UTILITY ENDPOINTS
# =============================================================================

@app.route('/api/health', methods=['GET'])
def health_check():
    """Health check endpoint"""
    return jsonify({
        "status": "healthy",
        "timestamp": get_current_timestamp().isoformat(),
        "version": "1.0.0"
    }), 200

@app.route('/api/initialize', methods=['POST'])
def initialize_database():
    """Initialize database with default data (run once)"""
    try:
        # Create default site settings
        default_settings = {
            'brand': {
                'name': 'Lash Studio',
                'tagline': 'Beautiful Lashes, Beautiful You',
                'companyName': 'Professional Lash Studio LLC',
                'description': 'Premium eyelash extension services with certified technicians'
            },
            'hero': {
                'title': 'Transform Your Look',
                'subtitle': 'Professional Eyelash Extensions',
                'description': 'Enhance your natural beauty with our premium lash extension services',
                'ctaPrimary': 'Book Now',
                'ctaSecondary': 'Learn More'
            },
            'contact': {
                'phone': '+1 (555) 123-4567',
                'email': 'hello@lashstudio.com',
                'businessHours': {
                    'monday': {'open': '09:00', 'close': '18:00', 'closed': False},
                    'tuesday': {'open': '09:00', 'close': '18:00', 'closed': False},
                    'wednesday': {'open': '09:00', 'close': '18:00', 'closed': False},
                    'thursday': {'open': '09:00', 'close': '18:00', 'closed': False},
                    'friday': {'open': '09:00', 'close': '18:00', 'closed': False},
                    'saturday': {'open': '10:00', 'close': '16:00', 'closed': False},
                    'sunday': {'open': '10:00', 'close': '16:00', 'closed': True}
                }
            },
            'theme': {
                'primaryColor': '#8B4513',
                'secondaryColor': '#F5DEB3',
                'accentColor': '#D2691E'
            },
            'updatedAt': get_current_timestamp()
        }
        
        db.collection('siteSettings').document('main').set(default_settings)
        
        # Create default service packages
        default_services = [
            {
                'name': 'Classic Lashes',
                'description': 'Natural-looking individual lash extensions',
                'price': 120,
                'durationMinutes': 120,
                'category': 'classic',
                'features': ['1:1 ratio', 'Natural look', 'Lasting 4-6 weeks'],
                'isFeatured': True,
                'displayOrder': 1,
                'isActive': True,
                'bookingCount': 0,
                'totalRevenue': 0,
                'createdAt': get_current_timestamp(),
                'updatedAt': get_current_timestamp()
            },
            {
                'name': 'Volume Lashes',
                'description': 'Fuller, more dramatic lash extensions',
                'price': 180,
                'durationMinutes': 150,
                'category': 'volume',
                'features': ['2D-5D fans', 'Dramatic look', 'Lasting 4-6 weeks'],
                'isFeatured': True,
                'displayOrder': 2,
                'isActive': True,
                'bookingCount': 0,
                'totalRevenue': 0,
                'createdAt': get_current_timestamp(),
                'updatedAt': get_current_timestamp()
            }
        ]
        
        for service in default_services:
            db.collection('servicePackages').add(service)
        
        return jsonify({"success": True, "message": "Database initialized successfully"}), 200
        
    except Exception as e:
        logger.error(f"Error initializing database: {str(e)}")
        return jsonify({"error": str(e)}), 400

# Error handlers
@app.errorhandler(404)
def not_found(error):
    return jsonify({"error": "Endpoint not found"}), 404

@app.errorhandler(500)
def internal_error(error):
    return jsonify({"error": "Internal server error"}), 500