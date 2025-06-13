# Unit Tests - Lash Studio Booking System

This document provides instructions for running the comprehensive unit test suite for the Flask-based lash studio appointment booking system.

## Overview

The test suite covers all major components of the application including:
- Authentication and authorization
- User management
- Service package management
- Appointment booking and management
- Site settings
- Testimonials
- Promo codes
- Analytics dashboard

## Prerequisites

### Required Python Packages

Install the following dependencies:

```bash
pip install pytest
pip install flask
pip install firebase-admin
pip install pytz
pip install python-dotenv
```

Or install from a requirements file:

```bash
pip install -r requirements.txt
```

### Project Structure

Ensure your project has the following structure:

```
project-root/
│
├── main.py              # Main Flask application
├── test_main.py         # Unit test file
├── requirements.txt     # Python dependencies
├── .env                # Environment variables (optional)
└── README.md           # This file
```

### Environment Setup

1. **Firebase Configuration**: Ensure you have Firebase credentials configured
2. **Environment Variables**: Set up any required environment variables
3. **Database**: Mock Firestore database is used in tests (no real database needed)

## Running the Tests

### Run All Tests

Execute the entire test suite:

```bash
pytest test_main.py -v
```

### Run Specific Test Classes

Run tests for specific components:

```bash
# Test utility functions only
pytest test_main.py::TestUtilityFunctions -v

# Test authentication only
pytest test_main.py::TestAuthentication -v

# Test user management only
pytest test_main.py::TestUserManagement -v

# Test appointment management only
pytest test_main.py::TestAppointmentManagement -v
```

### Run Individual Tests

Run specific test methods:

```bash
pytest test_main.py::TestAuthentication::test_require_auth_missing_header -v
```

### Run Tests with Coverage

Generate a coverage report:

```bash
pip install pytest-cov
pytest test_main.py --cov=main --cov-report=html
```

## Test Configuration Options

### Verbose Output

Use `-v` flag for detailed test output:

```bash
pytest test_main.py -v
```

### Stop on First Failure

Stop testing after the first failure:

```bash
pytest test_main.py -x
```

### Run Tests in Parallel

Install and use pytest-xdist for parallel execution:

```bash
pip install pytest-xdist
pytest test_main.py -n auto
```

### Filter Tests by Name

Run tests matching a pattern:

```bash
# Run all authentication-related tests
pytest test_main.py -k "auth" -v

# Run all success scenario tests
pytest test_main.py -k "success" -v

# Run all failure scenario tests
pytest test_main.py -k "failure" -v
```

## Test Categories

### 1. Utility Function Tests (`TestUtilityFunctions`)
- Timestamp generation
- Token validation
- Notification content generation

**Run with:**
```bash
pytest test_main.py::TestUtilityFunctions -v
```

### 2. Authentication Tests (`TestAuthentication`)
- Missing/invalid authorization headers
- Token validation
- Permission checking
- User document verification

**Run with:**
```bash
pytest test_main.py::TestAuthentication -v
```

### 3. User Management Tests (`TestUserManagement`)
- User creation (admin only)
- User retrieval
- User updates
- Access control

**Run with:**
```bash
pytest test_main.py::TestUserManagement -v
```

### 4. Service Package Tests (`TestServicePackages`)
- Service listing
- Category filtering
- Service creation (admin only)

**Run with:**
```bash
pytest test_main.py::TestServicePackages -v
```

### 5. Appointment Management Tests (`TestAppointmentManagement`)
- Appointment creation
- Appointment retrieval with filtering
- Status updates
- Notification scheduling

**Run with:**
```bash
pytest test_main.py::TestAppointmentManagement -v
```

### 6. Site Settings Tests (`TestSiteSettings`)
- Settings retrieval
- Settings updates (admin only)
- Sensitive data filtering

**Run with:**
```bash
pytest test_main.py::TestSiteSettings -v
```

### 7. Testimonials Tests (`TestTestimonials`)
- Testimonial listing
- Testimonial creation
- Approval workflow

**Run with:**
```bash
pytest test_main.py::TestTestimonials -v
```

### 8. Promo Codes Tests (`TestPromoCodes`)
- Code validation
- Discount calculations
- Expiration handling
- Usage limits

**Run with:**
```bash
pytest test_main.py::TestPromoCodes -v
```

### 9. Analytics Tests (`TestAnalytics`)
- Dashboard metrics
- Admin-only access
- Data aggregation

**Run with:**
```bash
pytest test_main.py::TestAnalytics -v
```

## Mock Data and Fixtures

The test suite uses several pytest fixtures that provide mock data:

- `mock_user_data`: Standard client user
- `mock_admin_user_data`: Admin user
- `mock_service_data`: Lash service package
- `mock_appointment_data`: Sample appointment
- `valid_auth_token`: Mock authentication token

These fixtures automatically handle database mocking and provide consistent test data.

## Troubleshooting

### Common Issues

1. **Import Errors**: Ensure `main.py` is in the same directory and contains all expected functions
2. **Firebase Errors**: The tests use mocks, so actual Firebase credentials aren't needed
3. **Missing Dependencies**: Install all required packages listed in prerequisites

### Test Failures

If tests fail:

1. Check that `main.py` contains all the expected functions and endpoints
2. Verify the Flask app structure matches the test expectations
3. Ensure all imports in `test_main.py` resolve correctly

### Debug Mode

Run tests with Python debugging:

```bash
pytest test_main.py -v -s --pdb
```

## Continuous Integration

For CI/CD pipelines, use:

```bash
pytest test_main.py --junitxml=test-results.xml --cov=main --cov-report=xml
```

## Contributing

When adding new features to the main application:

1. Add corresponding test cases to the appropriate test class
2. Update mock data fixtures if needed
3. Ensure all tests pass before submitting changes
4. Maintain test coverage above 80%

## Test Results Interpretation

- **PASSED**: Test executed successfully
- **FAILED**: Test assertion failed - check the error message
- **ERROR**: Test couldn't run due to setup issues
- **SKIPPED**: Test was intentionally skipped

The test suite is designed to be comprehensive and should catch most regression issues during development.
