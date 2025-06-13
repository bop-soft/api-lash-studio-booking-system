# Firebase Cloud Functions Python API - Lash Studio Booking System

## 📋 Overview

A comprehensive Firebase Cloud Functions API built with Python and Flask for managing a beauty business, specifically focused on eyelash extension services. The system provides complete functionality for appointment booking, user management, payment processing, notifications, and analytics.

## 🏗️ Architecture Design

### System Architecture
```
┌─────────────────┐    ┌──────────────────┐    ┌─────────────────┐
│   Client Apps   │    │   Cloud Functions│    │   Firebase      │
│                 │    │                  │    │   Services      │
│ • Web App       │◄──►│ • Flask API      │◄──►│ • Firestore     │
│ • Mobile App    │    │ • Authentication │    │ • Auth          │
│ • Admin Panel   │    │ • Validation     │    │ • Storage       │
└─────────────────┘    └──────────────────┘    └─────────────────┘
                              │
                              ▼
                    ┌──────────────────┐
                    │  External APIs   │
                    │ • Stripe         │
                    │ • SendGrid       │
                    │ • Twilio         │
                    └──────────────────┘
```

### Technology Stack
- **Runtime**: Python 3.9+
- **Framework**: Flask 2.3.3 with CORS support
- **Database**: Google Cloud Firestore
- **Authentication**: Firebase Authentication
- **Storage**: Google Cloud Storage
- **Payments**: Stripe API
- **Email**: SendGrid API
- **SMS**: Twilio API
- **Deployment**: Firebase Cloud Functions v2

## 🚀 Features

### Core Functionality
- **User Management**: Registration, authentication, role-based access control
- **Service Management**: CRUD operations for service packages
- **Appointment System**: Booking, scheduling, status management
- **Payment Processing**: Stripe integration with webhook support
- **Notification System**: Email/SMS reminders and confirmations
- **Content Management**: Dynamic page content blocks
- **Analytics**: Dashboard metrics and scheduled reporting
- **Media Library**: File upload and management
- **Promo Codes**: Discount validation and management
- **Testimonials**: Review collection and display

### User Roles
- **Admin**: Full system access
- **Technician**: Service management and appointment handling
- **Client**: Personal bookings and profile management

## 📁 Project Structure

```
.
├── main.py                 # Main API implementation
├── requirements.txt        # Python dependencies
├── firebase.json          # Firebase configuration
└── .firebaserc           # Firebase project settings
```

## 🔧 Installation & Setup

### Prerequisites
- Python 3.9 or higher
- Firebase CLI
- Google Cloud Project with billing enabled
- Firebase project with Firestore and Authentication enabled

### Environment Setup

1. **Clone and install dependencies:**
```bash
pip install -r requirements.txt
```

2. **Firebase Configuration:**
```bash
firebase login
firebase init functions
```

3. **Environment Variables:**
Set up the following in Firebase Functions configuration:
```bash
firebase functions:config:set \
  stripe.secret_key="sk_test_..." \
  stripe.publishable_key="pk_test_..." \
  stripe.webhook_secret="whsec_..." \
  sendgrid.api_key="SG...." \
  twilio.account_sid="AC..." \
  twilio.auth_token="..." \
  twilio.phone_number="+1..."
```

4. **Deploy:**
```bash
firebase deploy --only functions
```

## 🗄️ Database Schema

### Collections Structure

#### Users Collection (`users`)
```json
{
  "email": "client@example.com",
  "role": "client|technician|admin",
  "profile": {
    "firstName": "Jane",
    "lastName": "Doe",
    "phone": "+1234567890",
    "dateOfBirth": "1990-01-01"
  },
  "preferences": {
    "notificationMethod": "email|sms",
    "marketingConsent": false,
    "reminderSettings": {
      "email": true,
      "sms": false,
      "hoursBefore": [24, 2]
    }
  },
  "medicalInfo": {
    "allergies": [],
    "skinSensitivity": "normal|sensitive|very_sensitive"
  },
  "isActive": true,
  "createdAt": "timestamp",
  "updatedAt": "timestamp"
}
```

#### Service Packages Collection (`servicePackages`)
```json
{
  "name": "Classic Lashes",
  "description": "Natural-looking individual lash extensions",
  "price": 120,
  "durationMinutes": 120,
  "category": "classic|volume|hybrid",
  "features": ["1:1 ratio", "Natural look", "Lasting 4-6 weeks"],
  "imageUrl": "https://...",
  "isFeatured": true,
  "displayOrder": 1,
  "isActive": true,
  "bookingCount": 0,
  "totalRevenue": 0,
  "createdBy": "userId",
  "createdAt": "timestamp",
  "updatedAt": "timestamp"
}
```

#### Appointments Collection (`appointments`)
```json
{
  "client": {
    "id": "userId",
    "name": "Jane Doe",
    "email": "jane@example.com",
    "phone": "+1234567890"
  },
  "service": {
    "id": "serviceId",
    "name": "Classic Lashes",
    "price": 120,
    "duration": 120
  },
  "dateTime": {
    "date": "timestamp",
    "time": "14:30",
    "timezone": "America/New_York"
  },
  "status": "confirmed|completed|cancelled|no_show",
  "payment": {
    "status": "pending|paid|failed|refunded",
    "method": "stripe|cash|bank_transfer",
    "totalPrice": 120,
    "discount": {
      "code": "WELCOME10",
      "amount": 12
    },
    "stripePaymentIntentId": "pi_...",
    "processedAt": "timestamp"
  },
  "addons": [],
  "notes": [
    {
      "type": "service|medical|general",
      "content": "Client prefers natural curl",
      "isPrivate": false,
      "createdBy": "userId",
      "createdAt": "timestamp"
    }
  ],
  "notifications": [
    {
      "type": "confirmation|reminder_24h|reminder_2h",
      "method": "email|sms",
      "scheduledFor": "timestamp",
      "status": "pending|sent|failed",
      "sentAt": "timestamp"
    }
  ],
  "timeline": [
    {
      "event": "created|confirmed|completed|cancelled",
      "timestamp": "timestamp",
      "userId": "userId",
      "notes": "Appointment created"
    }
  ],
  "referralSource": "website|instagram|referral",
  "createdAt": "timestamp",
  "updatedAt": "timestamp"
}
```

## 🔌 API Endpoints

### Authentication
All protected endpoints require `Authorization: Bearer <firebase_token>` header.

### User Management
- `POST /api/users` - Create user (Admin only)
- `GET /api/users/<user_id>` - Get user details
- `PUT /api/users/<user_id>` - Update user profile

### Service Management
- `GET /api/services` - List active services
- `POST /api/services` - Create service (Admin only)
- `PUT /api/services/<service_id>` - Update service (Admin only)

### Appointment Management
- `POST /api/appointments` - Create appointment
- `GET /api/appointments` - List appointments (filtered by role)
- `PUT /api/appointments/<appointment_id>` - Update appointment

### Payment Processing
- `POST /api/payments/create-intent` - Create Stripe payment intent
- `POST /api/payments/webhook` - Handle Stripe webhooks

### Content Management
- `GET /api/content/<page_slug>` - Get page content blocks
- `POST /api/content/<page_slug>/blocks` - Create content block (Admin only)

### Site Settings
- `GET /api/site-settings` - Get public site settings
- `PUT /api/site-settings` - Update site settings (Admin only)

### Analytics
- `GET /api/analytics/dashboard` - Get dashboard metrics (Admin/Technician)

### Utility
- `GET /api/health` - Health check
- `POST /api/initialize` - Initialize database with default data

## 🔐 Security Features

### Authentication & Authorization
- Firebase Authentication integration
- Role-based access control (RBAC)
- JWT token validation
- Request context user injection

### Data Protection
- Input validation and sanitization
- SQL injection prevention through Firestore
- Sensitive data filtering in responses
- CORS configuration

### Payment Security
- Stripe webhook signature verification
- PCI compliance through Stripe
- Secure payment intent creation

## 📧 Notification System

### Email Notifications (SendGrid)
- Appointment confirmations
- Reminder notifications (24h, 2h before)
- Status change notifications
- HTML email templates

### SMS Notifications (Twilio)
- Text message reminders
- Appointment confirmations
- Real-time status updates

### Scheduled Processing
- Cloud Scheduler integration
- Automatic notification processing every 15 minutes
- Failed notification retry logic

## 📊 Analytics & Reporting

### Real-time Metrics
- Total appointments and revenue
- Completion and cancellation rates
- Service breakdown analysis
- Payment method distribution

### Scheduled Analytics
- Daily analytics generation
- Historical data aggregation
- Performance trend analysis

## 🎨 Content Management

### Dynamic Content Blocks
- Page-specific content management
- Block types: hero, text, image, service grid
- Responsive content configuration
- Display order management

### Media Library
- Google Cloud Storage integration
- File upload and management
- Image optimization and serving
- Usage tracking and metadata

## 💳 Payment Integration

### Stripe Features
- Payment intent creation
- Webhook event handling
- Multiple payment methods
- Refund processing

### Promo Code System
- Percentage and fixed amount discounts
- Usage limits and expiration
- Service-specific applicability
- Minimum order requirements

## 🚀 Deployment

### Firebase Functions Deployment
```bash
# Deploy all functions
firebase deploy --only functions

# Deploy specific function
firebase deploy --only functions:api

# Set environment variables
firebase functions:config:set stripe.secret_key="sk_..."
```

### Environment Configuration
```javascript
// firebase.json
{
  "functions": {
    "runtime": "python39",
    "source": ".",
    "ignore": ["venv", ".git"]
  }
}
```

## 🧪 Testing

### Local Development
```bash
# Install Firebase CLI
npm install -g firebase-tools

# Start local emulators
firebase emulators:start --only functions,firestore,auth

# Test endpoints
curl -X GET http://localhost:5001/project-id/us-central1/api/health
```

### Testing Strategy
- Unit tests for utility functions
- Integration tests for API endpoints
- Authentication flow testing
- Payment webhook testing

## 📈 Performance Optimization

### Caching Strategy
- Firestore query optimization
- Static content caching
- API response caching

### Scalability Features
- Automatic scaling with Cloud Functions
- Connection pooling for external APIs
- Efficient database queries
- Background task processing

## 🔄 Monitoring & Logging

### Logging Configuration
```python
import logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
```

### Monitoring Tools
- Firebase Functions logs
- Cloud Monitoring integration
- Error tracking and alerting
- Performance metrics

## 🤝 Contributing

### Development Guidelines
1. Follow Python PEP 8 style guide
2. Add type hints for function parameters
3. Include comprehensive error handling
4. Write descriptive commit messages
5. Update documentation for new features

### Code Review Process
1. Feature branch development
2. Pull request with description
3. Code review and testing
4. Deployment to staging
5. Production deployment

## 📝 License

This project is proprietary software for beauty clinic booking management.

## 📞 Support

For technical support:
- Open an issue on GitHub