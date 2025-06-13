import pytest
import json
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime, timedelta
import pytz
from flask import Flask

# Import the main module
from main import (
    app, db, get_current_timestamp, validate_auth_token,
    require_auth, send_email_notification, send_sms_notification,
    generate_notification_content, schedule_appointment_notifications
)

# Test configuration
@pytest.fixture
def client():
    """Create a test client for the Flask app"""
    app.config['TESTING'] = True
    with app.test_client() as client:
        yield client

@pytest.fixture
def mock_db():
    """Mock Firestore database"""
    with patch('main.db') as mock:
        yield mock

@pytest.fixture
def mock_auth():
    """Mock Firebase Auth"""
    with patch('main.auth') as mock:
        yield mock

@pytest.fixture
def mock_storage():
    """Mock Firebase Storage"""
    with patch('main.bucket') as mock:
        yield mock

@pytest.fixture
def valid_auth_token():
    """Mock valid auth token"""
    return "valid_token_123"

@pytest.fixture
def mock_user_data():
    """Mock user data"""
    return {
        'uid': 'user123',
        'email': 'test@example.com',
        'role': 'client',
        'profile': {
            'firstName': 'John',
            'lastName': 'Doe',
            'phone': '+1234567890'
        },
        'preferences': {
            'notificationMethod': 'email',
            'reminderSettings': {
                'email': True,
                'sms': False,
                'hoursBefore': [24, 2]
            }
        }
    }

@pytest.fixture
def mock_admin_user_data():
    """Mock admin user data"""
    return {
        'uid': 'admin123',
        'email': 'admin@example.com',
        'role': 'admin',
        'profile': {
            'firstName': 'Admin',
            'lastName': 'User'
        }
    }

@pytest.fixture
def mock_service_data():
    """Mock service package data"""
    return {
        'id': 'service123',
        'name': 'Classic Lashes',
        'description': 'Natural-looking individual lash extensions',
        'price': 120,
        'durationMinutes': 120,
        'category': 'classic',
        'features': ['1:1 ratio', 'Natural look', 'Lasting 4-6 weeks'],
        'isFeatured': True,
        'displayOrder': 1,
        'isActive': True
    }

@pytest.fixture
def mock_appointment_data():
    """Mock appointment data"""
    return {
        'id': 'appointment123',
        'client': {
            'id': 'user123',
            'name': 'John Doe',
            'email': 'test@example.com',
            'phone': '+1234567890'
        },
        'service': {
            'id': 'service123',
            'name': 'Classic Lashes',
            'price': 120,
            'duration': 120
        },
        'dateTime': {
            'date': datetime.utcnow() + timedelta(days=1),
            'time': '14:00',
            'timezone': 'UTC'
        },
        'status': 'confirmed',
        'payment': {
            'status': 'pending',
            'totalPrice': 120
        }
    }

# =============================================================================
# UTILITY FUNCTION TESTS
# =============================================================================

class TestUtilityFunctions:
    
    def test_get_current_timestamp(self):
        """Test current timestamp generation"""
        timestamp = get_current_timestamp()
        assert isinstance(timestamp, datetime)
        # Should be within 1 second of now
        assert abs((datetime.utcnow() - timestamp).total_seconds()) < 1
    
    @patch('main.auth.verify_id_token')
    def test_validate_auth_token_success(self, mock_verify):
        """Test successful token validation"""
        mock_verify.return_value = {'uid': 'user123', 'email': 'test@example.com'}
        
        result = validate_auth_token('valid_token')
        
        assert result['success'] is True
        assert result['user']['uid'] == 'user123'
        mock_verify.assert_called_once_with('valid_token')
    
    @patch('main.auth.verify_id_token')
    def test_validate_auth_token_failure(self, mock_verify):
        """Test failed token validation"""
        mock_verify.side_effect = Exception('Invalid token')
        
        result = validate_auth_token('invalid_token')
        
        assert result['success'] is False
        assert 'error' in result
    
    def test_generate_notification_content_confirmation_email(self, mock_appointment_data):
        """Test email confirmation content generation"""
        subject, content = generate_notification_content(
            'confirmation', mock_appointment_data, 'email'
        )
        
        assert 'Appointment Confirmation' in subject
        assert 'John Doe' in content
        assert 'Classic Lashes' in content
        assert '<html>' in content
    
    def test_generate_notification_content_reminder_sms(self, mock_appointment_data):
        """Test SMS reminder content generation"""
        subject, content = generate_notification_content(
            'reminder_24h', mock_appointment_data, 'sms'
        )
        
        assert subject == ""
        assert 'Reminder' in content
        assert 'John Doe' in content
        assert '24 hours' in content

# =============================================================================
# AUTHENTICATION TESTS
# =============================================================================

class TestAuthentication:
    
    def test_require_auth_missing_header(self, client):
        """Test authentication with missing header"""
        response = client.get('/api/users/test123')
        
        assert response.status_code == 401
        data = json.loads(response.data)
        assert 'Missing or invalid authorization header' in data['error']
    
    def test_require_auth_invalid_format(self, client):
        """Test authentication with invalid header format"""
        response = client.get('/api/users/test123', 
                            headers={'Authorization': 'InvalidFormat token123'})
        
        assert response.status_code == 401
    
    @patch('main.validate_auth_token')
    @patch('main.db')
    def test_require_auth_invalid_token(self, mock_db, mock_validate, client):
        """Test authentication with invalid token"""
        mock_validate.return_value = {'success': False, 'error': 'Invalid token'}
        
        response = client.get('/api/users/test123',
                            headers={'Authorization': 'Bearer invalid_token'})
        
        assert response.status_code == 401
    
    @patch('main.validate_auth_token')
    @patch('main.db')
    def test_require_auth_user_not_found(self, mock_db, mock_validate, client):
        """Test authentication when user document doesn't exist"""
        mock_validate.return_value = {'success': True, 'user': {'uid': 'user123'}}
        
        mock_doc = Mock()
        mock_doc.exists = False
        mock_db.collection.return_value.document.return_value.get.return_value = mock_doc
        
        response = client.get('/api/users/test123',
                            headers={'Authorization': 'Bearer valid_token'})
        
        assert response.status_code == 404
    
    @patch('main.validate_auth_token')
    @patch('main.db')
    def test_require_auth_insufficient_permissions(self, mock_db, mock_validate, client):
        """Test authentication with insufficient permissions"""
        mock_validate.return_value = {'success': True, 'user': {'uid': 'user123'}}
        
        mock_doc = Mock()
        mock_doc.exists = True
        mock_doc.to_dict.return_value = {'role': 'client'}
        mock_db.collection.return_value.document.return_value.get.return_value = mock_doc
        
        # Try to access admin-only endpoint
        response = client.post('/api/users',
                             headers={'Authorization': 'Bearer valid_token'},
                             json={'email': 'test@example.com'})
        
        assert response.status_code == 403

# =============================================================================
# USER MANAGEMENT TESTS
# =============================================================================

class TestUserManagement:
    
    @patch('main.validate_auth_token')
    @patch('main.db')
    @patch('main.auth')
    def test_create_user_success(self, mock_auth_module, mock_db, mock_validate, client):
        """Test successful user creation"""
        # Mock admin authentication
        mock_validate.return_value = {'success': True, 'user': {'uid': 'admin123'}}
        mock_admin_doc = Mock()
        mock_admin_doc.exists = True
        mock_admin_doc.to_dict.return_value = {'role': 'admin'}
        mock_db.collection.return_value.document.return_value.get.return_value = mock_admin_doc
        
        # Mock user creation
        mock_user_record = Mock()
        mock_user_record.uid = 'new_user123'
        mock_auth_module.create_user.return_value = mock_user_record
        
        mock_db.collection.return_value.document.return_value.set.return_value = None
        
        user_data = {
            'email': 'newuser@example.com',
            'password': 'password123',
            'role': 'client',
            'profile': {
                'firstName': 'New',
                'lastName': 'User'
            }
        }
        
        response = client.post('/api/users',
                             headers={'Authorization': 'Bearer admin_token'},
                             json=user_data)
        
        assert response.status_code == 201
        data = json.loads(response.data)
        assert data['success'] is True
        assert data['userId'] == 'new_user123'
    
    @patch('main.validate_auth_token')
    @patch('main.db')
    def test_get_user_success(self, mock_db, mock_validate, client, mock_user_data):
        """Test successful user retrieval"""
        mock_validate.return_value = {'success': True, 'user': {'uid': 'user123'}}
        
        # Mock user document
        mock_doc = Mock()
        mock_doc.exists = True
        mock_doc.to_dict.return_value = mock_user_data
        mock_db.collection.return_value.document.return_value.get.return_value = mock_doc
        
        response = client.get('/api/users/user123',
                            headers={'Authorization': 'Bearer valid_token'})
        
        assert response.status_code == 200
        data = json.loads(response.data)
        assert data['success'] is True
        assert data['user']['email'] == 'test@example.com'
    
    @patch('main.validate_auth_token')
    @patch('main.db')
    def test_get_user_access_denied(self, mock_db, mock_validate, client, mock_user_data):
        """Test user access denial for other users"""
        mock_validate.return_value = {'success': True, 'user': {'uid': 'user123'}}
        mock_doc = Mock()
        mock_doc.exists = True
        mock_doc.to_dict.return_value = mock_user_data
        mock_db.collection.return_value.document.return_value.get.return_value = mock_doc
        
        # Try to access different user's data
        response = client.get('/api/users/different_user',
                            headers={'Authorization': 'Bearer valid_token'})
        
        assert response.status_code == 403
    
    @patch('main.validate_auth_token')
    @patch('main.db')
    def test_update_user_success(self, mock_db, mock_validate, client, mock_user_data):
        """Test successful user update"""
        mock_validate.return_value = {'success': True, 'user': {'uid': 'user123'}}
        mock_doc = Mock()
        mock_doc.exists = True
        mock_doc.to_dict.return_value = mock_user_data
        mock_db.collection.return_value.document.return_value.get.return_value = mock_doc
        mock_db.collection.return_value.document.return_value.update.return_value = None
        
        update_data = {
            'profile': {
                'firstName': 'Updated',
                'lastName': 'Name'
            }
        }
        
        response = client.put('/api/users/user123',
                            headers={'Authorization': 'Bearer valid_token'},
                            json=update_data)
        
        assert response.status_code == 200
        data = json.loads(response.data)
        assert data['success'] is True

# =============================================================================
# SERVICE PACKAGE TESTS
# =============================================================================

class TestServicePackages:
    
    @patch('main.db')
    def test_get_services_success(self, mock_db, client, mock_service_data):
        """Test successful service retrieval"""
        mock_doc = Mock()
        mock_doc.id = 'service123'
        mock_doc.to_dict.return_value = mock_service_data
        
        mock_query = Mock()
        mock_query.order_by.return_value.stream.return_value = [mock_doc]
        mock_db.collection.return_value.where.return_value = mock_query
        
        response = client.get('/api/services')
        
        assert response.status_code == 200
        data = json.loads(response.data)
        assert data['success'] is True
        assert len(data['services']) == 1
        assert data['services'][0]['name'] == 'Classic Lashes'
    
    @patch('main.db')
    def test_get_services_with_category_filter(self, mock_db, client, mock_service_data):
        """Test service retrieval with category filter"""
        mock_doc = Mock()
        mock_doc.id = 'service123'
        mock_doc.to_dict.return_value = mock_service_data
        
        mock_query = Mock()
        mock_query.where.return_value.order_by.return_value.stream.return_value = [mock_doc]
        mock_db.collection.return_value.where.return_value = mock_query
        
        response = client.get('/api/services?category=classic')
        
        assert response.status_code == 200
        data = json.loads(response.data)
        assert data['success'] is True
    
    @patch('main.validate_auth_token')
    @patch('main.db')
    def test_create_service_success(self, mock_db, mock_validate, client, mock_admin_user_data):
        """Test successful service creation"""
        mock_validate.return_value = {'success': True, 'user': {'uid': 'admin123'}}
        mock_doc = Mock()
        mock_doc.exists = True
        mock_doc.to_dict.return_value = mock_admin_user_data
        mock_db.collection.return_value.document.return_value.get.return_value = mock_doc
        
        mock_doc_ref = Mock()
        mock_doc_ref.id = 'new_service123'
        mock_db.collection.return_value.add.return_value = (None, mock_doc_ref)
        
        service_data = {
            'name': 'Volume Lashes',
            'description': 'Fuller, more dramatic lash extensions',
            'price': 180,
            'durationMinutes': 150,
            'category': 'volume'
        }
        
        response = client.post('/api/services',
                             headers={'Authorization': 'Bearer admin_token'},
                             json=service_data)
        
        assert response.status_code == 201
        data = json.loads(response.data)
        assert data['success'] is True
        assert data['serviceId'] == 'new_service123'

# =============================================================================
# APPOINTMENT MANAGEMENT TESTS
# =============================================================================

class TestAppointmentManagement:
    
    @patch('main.validate_auth_token')
    @patch('main.db')
    @patch('main.schedule_appointment_notifications')
    def test_create_appointment_success(self, mock_schedule, mock_db, mock_validate, 
                                      client, mock_user_data, mock_service_data):
        """Test successful appointment creation"""
        mock_validate.return_value = {'success': True, 'user': {'uid': 'user123'}}
        mock_user_doc = Mock()
        mock_user_doc.exists = True
        mock_user_doc.to_dict.return_value = mock_user_data
        
        mock_service_doc = Mock()
        mock_service_doc.exists = True
        mock_service_doc.to_dict.return_value = mock_service_data
        
        mock_db.collection.return_value.document.return_value.get.side_effect = [
            mock_user_doc,  # First call for user auth
            mock_service_doc,  # Second call for service
            mock_user_doc   # Third call for client
        ]
        
        mock_doc_ref = Mock()
        mock_doc_ref.id = 'appointment123'
        mock_db.collection.return_value.add.return_value = (None, mock_doc_ref)
        
        appointment_data = {
            'clientId': 'user123',
            'serviceId': 'service123',
            'dateTime': '2024-12-15T14:00:00Z'
        }
        
        response = client.post('/api/appointments',
                             headers={'Authorization': 'Bearer valid_token'},
                             json=appointment_data)
        
        assert response.status_code == 201
        data = json.loads(response.data)
        assert data['success'] is True
        assert data['appointmentId'] == 'appointment123'
        mock_schedule.assert_called_once()
    
    @patch('main.validate_auth_token')
    @patch('main.db')
    def test_get_appointments_client_filter(self, mock_db, mock_validate, 
                                          client, mock_user_data, mock_appointment_data):
        """Test appointment retrieval with client filtering"""
        mock_validate.return_value = {'success': True, 'user': {'uid': 'user123'}}
        mock_user_doc = Mock()
        mock_user_doc.exists = True
        mock_user_doc.to_dict.return_value = mock_user_data
        mock_db.collection.return_value.document.return_value.get.return_value = mock_user_doc
        
        mock_doc = Mock()
        mock_doc.id = 'appointment123'
        mock_doc.to_dict.return_value = mock_appointment_data
        
        mock_query = Mock()
        mock_query.where.return_value.order_by.return_value.stream.return_value = [mock_doc]
        mock_db.collection.return_value = mock_query
        
        response = client.get('/api/appointments',
                            headers={'Authorization': 'Bearer valid_token'})
        
        assert response.status_code == 200
        data = json.loads(response.data)
        assert data['success'] is True
        assert len(data['appointments']) == 1
    
    @patch('main.validate_auth_token')
    @patch('main.db')
    def test_update_appointment_status(self, mock_db, mock_validate, 
                                     client, mock_user_data, mock_appointment_data):
        """Test appointment status update"""
        mock_validate.return_value = {'success': True, 'user': {'uid': 'user123'}}
        mock_user_doc = Mock()
        mock_user_doc.exists = True
        mock_user_doc.to_dict.return_value = mock_user_data
        mock_db.collection.return_value.document.return_value.get.side_effect = [
            mock_user_doc  # Auth check
        ]
        
        mock_appointment_doc = Mock()
        mock_appointment_doc.exists = True
        mock_appointment_doc.to_dict.return_value = mock_appointment_data
        mock_db.collection.return_value.document.return_value.get.return_value = mock_appointment_doc
        mock_db.collection.return_value.document.return_value.update.return_value = None
        
        update_data = {
            'status': 'completed',
            'statusNote': 'Service completed successfully'
        }
        
        response = client.put('/api/appointments/appointment123',
                            headers={'Authorization': 'Bearer valid_token'},
                            json=update_data)
        
        assert response.status_code == 200
        data = json.loads(response.data)
        assert data['success'] is True

# =============================================================================
# SITE SETTINGS TESTS
# =============================================================================

class TestSiteSettings:
    
    @patch('main.db')
    def test_get_site_settings_success(self, mock_db, client):
        """Test successful site settings retrieval"""
        settings_data = {
            'brand': {
                'name': 'Lash Studio',
                'tagline': 'Beautiful Lashes, Beautiful You'
            },
            'integrations': {
                'stripe': {
                    'publishableKey': 'pk_test_123',
                    'secretKey': 'sk_test_secret'  # Should be filtered out
                },
                'email': {
                    'apiKey': 'secret_email_key'  # Should be filtered out
                }
            }
        }
        
        mock_doc = Mock()
        mock_doc.exists = True
        mock_doc.to_dict.return_value = settings_data
        mock_db.collection.return_value.document.return_value.get.return_value = mock_doc
        
        response = client.get('/api/site-settings')
        
        assert response.status_code == 200
        data = json.loads(response.data)
        assert data['success'] is True
        assert 'brand' in data['settings']
        # Check that sensitive data is filtered
        assert 'secretKey' not in str(data['settings']['integrations']['stripe'])
        assert 'email' not in data['settings']['integrations']
    
    @patch('main.validate_auth_token')
    @patch('main.db')
    def test_update_site_settings_success(self, mock_db, mock_validate, 
                                        client, mock_admin_user_data):
        """Test successful site settings update"""
        mock_validate.return_value = {'success': True, 'user': {'uid': 'admin123'}}
        mock_doc = Mock()
        mock_doc.exists = True
        mock_doc.to_dict.return_value = mock_admin_user_data
        mock_db.collection.return_value.document.return_value.get.return_value = mock_doc
        mock_db.collection.return_value.document.return_value.set.return_value = None
        
        update_data = {
            'brand': {
                'name': 'Updated Studio Name'
            }
        }
        
        response = client.put('/api/site-settings',
                            headers={'Authorization': 'Bearer admin_token'},
                            json=update_data)
        
        assert response.status_code == 200
        data = json.loads(response.data)
        assert data['success'] is True

# =============================================================================
# TESTIMONIALS TESTS
# =============================================================================

class TestTestimonials:
    
    @patch('main.db')
    def test_get_testimonials_success(self, mock_db, client):
        """Test successful testimonials retrieval"""
        testimonial_data = {
            'clientName': 'Jane Smith',
            'rating': 5,
            'reviewText': 'Amazing service!',
            'isApproved': True,
            'isFeatured': True
        }
        
        mock_doc = Mock()
        mock_doc.id = 'testimonial123'
        mock_doc.to_dict.return_value = testimonial_data
        
        mock_query = Mock()
        mock_query.order_by.return_value.stream.return_value = [mock_doc]
        mock_db.collection.return_value.where.return_value = mock_query
        
        response = client.get('/api/testimonials')
        
        assert response.status_code == 200
        data = json.loads(response.data)
        assert data['success'] is True
        assert len(data['testimonials']) == 1
        assert data['testimonials'][0]['clientName'] == 'Jane Smith'
    
    @patch('main.validate_auth_token')
    @patch('main.db')
    def test_create_testimonial_success(self, mock_db, mock_validate, 
                                      client, mock_user_data):
        """Test successful testimonial creation"""
        mock_validate.return_value = {'success': True, 'user': {'uid': 'user123'}}
        mock_doc = Mock()
        mock_doc.exists = True
        mock_doc.to_dict.return_value = mock_user_data
        mock_db.collection.return_value.document.return_value.get.return_value = mock_doc
        
        mock_doc_ref = Mock()
        mock_doc_ref.id = 'testimonial123'
        mock_db.collection.return_value.add.return_value = (None, mock_doc_ref)
        
        testimonial_data = {
            'clientName': 'John Doe',
            'rating': 5,
            'reviewText': 'Excellent service!',
            'serviceReceived': 'Classic Lashes'
        }
        
        response = client.post('/api/testimonials',
                             headers={'Authorization': 'Bearer valid_token'},
                             json=testimonial_data)
        
        assert response.status_code == 201
        data = json.loads(response.data)
        assert data['success'] is True
        assert data['testimonialId'] == 'testimonial123'

# =============================================================================
# PROMO CODES TESTS
# =============================================================================

class TestPromoCodes:
    
    @patch('main.validate_auth_token')
    @patch('main.db')
    def test_validate_promo_code_success(self, mock_db, mock_validate, 
                                       client, mock_user_data):
        """Test successful promo code validation"""
        mock_validate.return_value = {'success': True, 'user': {'uid': 'user123'}}
        mock_user_doc = Mock()
        mock_user_doc.exists = True
        mock_user_doc.to_dict.return_value = mock_user_data
        mock_db.collection.return_value.document.return_value.get.return_value = mock_user_doc
        
        promo_data = {
            'code': 'SAVE20',
            'discountType': 'percentage',
            'discountValue': 20,
            'validFrom': datetime.utcnow() - timedelta(days=1),
            'validUntil': datetime.utcnow() + timedelta(days=30),
            'usageCount': 0,
            'usageLimit': 100,
            'minOrderAmount': 50,
            'isActive': True
        }
        
        mock_promo_doc = Mock()
        mock_promo_doc.to_dict.return_value = promo_data
        mock_db.collection.return_value.where.return_value.where.return_value.stream.return_value = [mock_promo_doc]
        
        request_data = {
            'code': 'SAVE20',
            'serviceIds': ['service123'],
            'orderAmount': 100
        }
        
        response = client.post('/api/promo-codes/validate',
                             headers={'Authorization': 'Bearer valid_token'},
                             json=request_data)
        
        assert response.status_code == 200
        data = json.loads(response.data)
        assert data['success'] is True
        assert data['discount']['amount'] == 20  # 20% of 100
        assert data['discount']['code'] == 'SAVE20'
    
    @patch('main.validate_auth_token')
    @patch('main.db')
    def test_validate_promo_code_expired(self, mock_db, mock_validate, 
                                       client, mock_user_data):
        """Test expired promo code validation"""
        mock_validate.return_value = {'success': True, 'user': {'uid': 'user123'}}
        mock_user_doc = Mock()
        mock_user_doc.exists = True
        mock_user_doc.to_dict.return_value = mock_user_data
        mock_db.collection.return_value.document.return_value.get.return_value = mock_user_doc
        
        promo_data = {
            'code': 'EXPIRED',
            'validFrom': datetime.utcnow() - timedelta(days=30),
            'validUntil': datetime.utcnow() - timedelta(days=1),  # Expired
            'usageCount': 0,
            'usageLimit': 100,
            'isActive': True
        }
        
        mock_promo_doc = Mock()
        mock_promo_doc.to_dict.return_value = promo_data
        mock_db.collection.return_value.where.return_value.where.return_value.stream.return_value = [mock_promo_doc]
        
        request_data = {
            'code': 'EXPIRED',
            'orderAmount': 100
        }
        
        response = client.post('/api/promo-codes/validate',
                             headers={'Authorization': 'Bearer valid_token'},
                             json=request_data)
        
        assert response.status_code == 400
        data = json.loads(response.data)
        assert data['success'] is False
        assert 'expired' in data['error'].lower()

# =============================================================================
# ANALYTICS TESTS
# =============================================================================