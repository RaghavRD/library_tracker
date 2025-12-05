# LibTrack AI - Test Suite Documentation

## Overview

This test suite provides comprehensive mock data and testing utilities for validating LibTrack AI's notification system, specifically:

1. **Future Update Detection** - Testing when upcoming library versions are detected and how notifications are generated
2. **Version Release Transitions** - Testing when future updates become actual releases
3. **Email Notifications** - Validating email content for both future and released versions

## Test Structure

```
tracker/tests/
├── __init__.py                 # Package initialization
├── conftest.py                 # Pytest fixtures and configuration
├── test_fixtures.py            # Mock data factories
├── test_future_updates.py      # Tests for future update scenarios
├── test_release_transition.py  # Tests for release transitions
├── test_helpers.py             # Helper utilities
└── mock_data_examples.py       # Standalone examples for manual testing
```

## Running Tests

### Run All Tests

```bash
# Run all tests
pytest tracker/tests/ -v

# Run with coverage
pytest tracker/tests/ -v --cov=tracker --cov-report=html

# Run with detailed output
pytest tracker/tests/ -vv -s
```

### Run Specific Test Files

```bash
# Test future updates only
pytest tracker/tests/test_future_updates.py -v

# Test release transitions only
pytest tracker/tests/test_release_transition.py -v
```

### Run Specific Test Classes

```bash
# Test future update detection
pytest tracker/tests/test_future_updates.py::TestFutureUpdateDetection -v

# Test complete lifecycle
pytest tracker/tests/test_release_transition.py::TestCompleteLifecycle -v
```

## Manual Testing with Mock Data

### Using Django Shell

```bash
# Start Django shell
python manage.py shell

# Import and run scenarios
from tracker.tests.mock_data_examples import *

# Run individual scenarios
create_future_update_scenario()      # Test future update detection
create_release_scenario()            # Test actual release
create_transition_scenario()         # Test future → released transition

# Or run all scenarios
run_all_scenarios()
```

### Using as Standalone Script

```bash
# Run directly (requires Django environment)
python tracker/tests/mock_data_examples.py
```

## Test Scenarios

### Scenario 1: Future Update Detection

**Purpose**: Test detection and notification of upcoming library versions

**What it tests**:
- Creating FutureUpdateCache entries
- High/low confidence filtering
- Email notification content (includes confidence %)
- Future update notice in emails
- Duplicate notification prevention

**Example**:
```python
from tracker.tests.test_fixtures import *

# Create project with future notifications enabled
project = ProjectFactory.create_future_enabled_project()

# Create a future update
future = FutureUpdateFactory.create_high_confidence_future(
    library='pandas',
    version='3.0.0',
    confidence=95
)

# Verify it was created correctly
assert future.confidence == 95
assert future.status == 'detected'
```

### Scenario 2: Actual Release

**Purpose**: Test notification of actually released versions

**What it tests**:
- Creating UpdateCache entries
- Email notification content (no future notice)
- Release date handling
- Category classification (major/minor)

**Example**:
```python
# Create project
project = ProjectFactory.create_basic_project()

# Create a released update
released = UpdateCacheFactory.create_major_release(
    project=project,
    library='django',
    version='5.0'
)

# Verify
assert released.category == 'major'
assert released.project == project
```

### Scenario 3: Future → Released Transition

**Purpose**: Test the complete lifecycle when a future update becomes released

**What it tests**:
- Promoting FutureUpdateCache to UpdateCache
- Linking via `promoted_to_release` relationship
- Status transitions (detected → released)
- Handling both notifications (future + release)

**Example**:
```python
# Build the scenario
scenario = MockDataBuilder.build_future_to_released_scenario()

future = scenario['future_update']
project = scenario['project']

# Simulate release
released = UpdateCacheFactory.create_update_cache(
    project=project,
    library=future.library,
    version=future.version
)

# Link them
future.promoted_to_release = released
future.status = 'released'
future.save()

# Verify relationship
assert future.promoted_to_release == released
assert released.future_predictions.first() == future
```

## Test Fixtures

### Project Fixtures

- `mock_project` - Factory for creating projects with custom settings
- `ProjectFactory.create_basic_project()` - Standard project
- `ProjectFactory.create_future_enabled_project()` - With future notifications
- `ProjectFactory.create_major_only_project()` - Major updates only

### Component Fixtures

- `mock_stack_component` - Factory for creating components
- `ComponentFactory.create_library()` - Create library component
- `ComponentFactory.create_language()` - Create language component
- `ComponentFactory.create_multiple_libraries()` - Batch creation

### Update Fixtures

- `FutureUpdateFactory.create_future_update()` - Generic future update
- `FutureUpdateFactory.create_high_confidence_future()` - 90%+ confidence
- `FutureUpdateFactory.create_low_confidence_future()` - Below threshold
- `FutureUpdateFactory.create_notified_future()` - Already notified
- `UpdateCacheFactory.create_update_cache()` - Generic released update
- `UpdateCacheFactory.create_major_release()` - Major version
- `UpdateCacheFactory.create_minor_release()` - Minor version

### API Mock Fixtures

- `mock_serper_response` - Mock Serper API responses
- `mock_groq_analysis` - Mock Groq analyzer responses
- `mock_mailtrap_success` - Mock successful email sending

## Helper Utilities

### EmailContentValidator

Validate email HTML content:

```python
from tracker.tests.test_helpers import EmailContentValidator

validator = EmailContentValidator()

# For future updates
results = validator.validate_future_update_email(html_content)
# Returns: {'has_future_notice': True, 'has_confidence': True, ...}

# For released versions
results = validator.validate_released_email(html_content)
# Returns: {'has_release_summary': True, 'no_future_notice': True, ...}
```

### NotificationPreferenceChecker

Check notification preferences:

```python
from tracker.tests.test_helpers import NotificationPreferenceChecker

checker = NotificationPreferenceChecker()

# Check if should notify
should_notify = checker.should_notify_for_category('major, minor, future', 'future')
# Returns: True

# Check if future enabled
is_enabled = checker.is_future_enabled('major, minor, future')
# Returns: True
```

### VersionComparer

Compare version numbers:

```python
from tracker.tests.test_helpers import VersionComparer

comparer = VersionComparer()

# Check if newer
is_newer = comparer.is_newer('2.0.0', '1.24.0')
# Returns: True

# Validate version
is_valid = comparer.is_valid_version('2.0.0')
# Returns: True
```

## Email Notification Testing

### Future Update Email

Expected content:
- ✓ Subject: "🔮 Future Update Alert: {library} {version} Planned"
- ✓ Future Update Notice banner (yellow background)
- ✓ Confidence percentage in table
- ✓ Expected release date
- ✓ Warning: "NOT been officially released yet"
- ✓ Planned/upcoming terminology

### Released Update Email

Expected content:
- ✓ Subject: "{library} {version} Released"
- ✓ Release summary section
- ✓ Actual release date
- ✓ No future notice banner
- ✓ Released/official terminology

## Confidence Threshold

The system uses a confidence threshold to filter future updates:

```python
MIN_CONFIDENCE = 70  # In run_daily_check.py

# Only future updates with confidence >= 70% are notified
```

Test this with:
```python
low_conf = FutureUpdateFactory.create_low_confidence_future(confidence=40)
high_conf = FutureUpdateFactory.create_high_confidence_future(confidence=95)

# low_conf would be filtered out
# high_conf would trigger notification
```

## Database Models

### FutureUpdateCache

Stores planned/upcoming updates:
- `library` - Library name
- `version` - Planned version
- `confidence` - Confidence % (0-100)
- `expected_date` - Expected release date
- `features` - Planned features
- `status` - detected | confirmed | released | cancelled
- `promoted_to_release` - Link to UpdateCache when released
- `notification_sent` - Prevent duplicates

### UpdateCache

Stores actually released updates:
- `project` - Associated project (ForeignKey)
- `library` - Library name
- `version` - Released version
- `category` - major | minor | future
- `release_date` - Actual release date
- `summary` - Release summary
- `future_predictions` - Related FutureUpdateCache entries

## Example Test Run Output

```bash
$ pytest tracker/tests/ -v

tracker/tests/test_future_updates.py::TestFutureUpdateDetection::test_detect_future_update PASSED
tracker/tests/test_future_updates.py::TestFutureUpdateDetection::test_future_update_cache_creation PASSED
tracker/tests/test_future_updates.py::TestFutureUpdateNotifications::test_future_update_email_content PASSED
tracker/tests/test_release_transition.py::TestFutureToReleasedTransition::test_promote_future_to_released PASSED
tracker/tests/test_release_transition.py::TestCompleteLifecycle::test_complete_future_to_release_flow PASSED

======================== 15 passed in 2.34s ========================
```

## Troubleshooting

### Tests fail with database errors

Make sure you're using the test database:
```bash
pytest tracker/tests/ --create-db
```

### Email tests fail

Check that `TEST_MODE=True` in your `.env` file for testing.

### Import errors

Make sure you're in the project root directory:
```bash
cd /path/to/LibTrack_AI_11Nov
pytest tracker/tests/ -v
```

## Next Steps

After running tests, you can:

1. Review generated email HTML in test output
2. Manually test with mock data examples
3. Verify notification preferences work correctly
4. Test confidence threshold filtering
5. Validate complete lifecycle flows
