# Future Version Detection Lifecycle

## Overview

LibTrack AI tracks upcoming/future versions through a complete lifecycle from detection to release. This document explains how the system detects, confirms, and manages future versions.

---

## Version States

The system tracks future updates through 4 distinct states:

### 1. **DETECTED** (Initial State)
When a future version is first discovered from search results.

### 2. **CONFIRMED** (Manual Update)
When the future version has been verified through official sources.

### 3. **RELEASED** (Auto-Promoted)
When the future version is officially released.

### 4. **CANCELLED** (Manual Update)
When the planned version is abandoned/cancelled.

---

## Detection Flow

```
┌──────────────────────────────────────────────────────────────┐
│  Daily Check Running                                         │
└──────────────────────────────────────────────────────────────┘
                     ↓
┌──────────────────────────────────────────────────────────────┐
│  1. Serper searches for library/language/tool               │
│     - Includes "roadmap", "upcoming", "beta", "RC" queries  │
└──────────────────────────────────────────────────────────────┘
                     ↓
┌──────────────────────────────────────────────────────────────┐
│  2. Groq analyzes search results                            │
│     Looks for:                                              │
│     - is_released: false                                    │
│     - category: "future"                                    │
│     - confidence: 0-100%                                    │
│     - expected_date: "YYYY-MM-DD"                           │
└──────────────────────────────────────────────────────────────┘
                     ↓
        ┌────────────┴────────────┐
        │  is_released == false?  │
        └────────────┬────────────┘
                     │ YES
                     ↓
┌──────────────────────────────────────────────────────────────┐
│ 3. _handle_future_update() method called                    │
└──────────────────────────────────────────────────────────────┘
                     ↓
        ┌────────────┴────────────┐
        │  User wants future      │
        │  updates?               │
        │  (notify_pref)          │
        └────────────┬────────────┘
                     │ YES
                     ↓
        ┌────────────┴────────────┐
        │  Confidence >= 70%?     │
        └────────────┬────────────┘
                     │ YES
                     ↓
┌──────────────────────────────────────────────────────────────┐
│ 4. Save to FutureUpdateCache                                │
│    - Status: "detected"                                     │
│    - Confidence: 70-100%                                    │
│    - Expected date: parsed date or null                    │
│    - Features: summary                                      │
└──────────────────────────────────────────────────────────────┘
                     ↓
┌──────────────────────────────────────────────────────────────┐
│ 5. Send notification email to user                          │
│    Subject: "🔮 Future Update Alert: Python 3.15 Planned"  │
└──────────────────────────────────────────────────────────────┘
```

---

## Code Implementation

### Detection Logic (run_daily_check.py)

```python
# Lines 253-274
def _evaluate_component(self, ...):
    # Run Serper + Groq search
    serper_results = serper.search_library(name, current_version, component_type=component_type)
    analysis = groq.analyze(name, serper_results)
    
    # Extract future update fields from Groq
    is_released = analysis.get("is_released", True)
    confidence = analysis.get("confidence", 50)
    expected_date = analysis.get("expected_date", "")
    category = analysis.get("category", "major")
    
    # Route to future update handler if not released
    if category == "future" or not is_released:
        return self._handle_future_update(
            library=library,
            version=version,
            confidence=confidence,
            expected_date=expected_date,
            summary=summary,
            source=source,
            notify_pref=notify_pref,
            label=label,
            component_type=component_type,
        )
```

### Future Update Handler (run_daily_check.py, lines 355-456)

```python
def _handle_future_update(self, library, version, confidence, expected_date, ...):
    # Check user preferences
    if "future" not in notify_pref:
        return None  # User doesn't want future updates
    
    # Confidence threshold (configurable)
    MIN_CONFIDENCE = 70
    if confidence < MIN_CONFIDENCE:
        return None  # Too uncertain to notify
    
    # Get or create FutureUpdateCache entry
    future_cache, created = FutureUpdateCache.objects.get_or_create(
        library=library,
        version=version,
        defaults={
            "confidence": confidence,
            "expected_date": parsed_date,
            "features": summary,
            "source": source,
            "status": "detected",  # ⭐ Initial state
            "notification_sent": False,
        }
    )
    
    # If already notified, skip
    if not created and future_cache.notification_sent:
        return None
    
    # Update if new info available
    if not created:
        if confidence > future_cache.confidence:
            future_cache.confidence = confidence
        if summary != future_cache.features:
            future_cache.features = summary
        # ... etc
        future_cache.save()
    
    # Mark as notified
    future_cache.notification_sent = True
    future_cache.notification_sent_at = datetime.now()
    future_cache.save()
    
    # Return update dict for email notification
    return {
        "library": library,
        "version": version,
        "category": "future",
        "confidence": confidence,
        ...
    }
```

---

## State Transitions

### DETECTED → CONFIRMED

**Trigger**: Manual update via Django Admin or API

**When**: Admin/developer verifies the future version through official channels

**Action**:
```python
# In Django Admin
future_update = FutureUpdateCache.objects.get(library="Python", version="3.15.0")
future_update.status = "confirmed"
future_update.confidence = 95  # Increase confidence
future_update.save()
```

---

### DETECTED/CONFIRMED → RELEASED

**Trigger**: Automatic when actual release is detected

**When**: Daily check finds the version is now released (`is_released: true`)

**Action**:
```python
# In _evaluate_component() when handling released versions
if is_released and version:
    # Check if this was a future prediction
    try:
        future_cache = FutureUpdateCache.objects.get(
            library=library,
            version=version,
            status__in=['detected', 'confirmed']
        )
        
        # Update status
        future_cache.status = "released"
        future_cache.promoted_to_release = cache  # Link to UpdateCache
        future_cache.save()
        
    except FutureUpdateCache.DoesNotExist:
        pass  # Normal release, no future prediction existed
```

**Database Schema**:
```python
class FutureUpdateCache(models.Model):
    # ... fields ...
    
    # Links to actual release
    promoted_to_release = models.ForeignKey(
        'UpdateCache',
        null=True,
        on_delete=models.SET_NULL,
        help_text="Links to UpdateCache entry when released"
    )
```

---

### DETECTED/CONFIRMED → CANCELLED

**Trigger**: Manual update

**When**: Official announcement that planned version is cancelled

**Action**:
```python
# Via Django Admin or management command
future_update = FutureUpdateCache.objects.get(library="React", version="19.0.0")
future_update.status = "cancelled"
future_update.save()

# Optionally notify users
send_cancellation_email(future_update)
```

---

## Confidence Scoring

The system uses `confidence` scores from Groq to determine reliability:

| Confidence | Source Type | Action |
|------------|-------------|---------|
| 90-100% | Official blog/docs from maintainers | ✅ Notify immediately |
| 70-89% | Reputable tech news sites | ✅ Notify |
| 50-69% | Community forums, Reddit | ⚠️ Store but don't notify |
| 0-49% | Speculation, rumors | ❌ Ignore |

**Threshold**: Default minimum is **70%** (configurable in code)

---

## Database Schema

```python
class FutureUpdateCache(TimeStampedModel):
    # Core fields
    library = CharField(max_length=200, db_index=True)
    version = CharField(max_length=100)
    expected_date = DateField(null=True)  # When it's expected
    confidence = IntegerField(0-100)  # Reliability score
    features = TextField()  # Summary of planned features
    source = URLField()  # Announcement/roadmap link
    
    # Status tracking
    STATUS_CHOICES = [
        ('detected', 'Detected'),      # ⭐ Initial
        ('confirmed', 'Confirmed'),    # ✅ Verified
        ('released', 'Released'),      # 🚀 Now available
        ('cancelled', 'Cancelled'),    # ❌ Abandoned
    ]
    status = CharField(choices=STATUS_CHOICES, default='detected')
    
    # Release linking
    promoted_to_release = ForeignKey('UpdateCache', null=True)
    
    # Notification tracking
    notification_sent = BooleanField(default=False)
    notification_sent_at = DateTimeField(null=True)
    
    class Meta:
        unique_together = [['library', 'version']]
```

---

## Example Scenarios

### Scenario 1: Python 3.15 Announced

**Day 1: Future version detected**
```
🔍 Serper finds: "Python 3.15 planned for October 2025"
🤖 Groq analyzes:
   - is_released: false
   - confidence: 85%
   - expected_date: "2025-10-01"
   - category: "future"

💾 Stored in FutureUpdateCache:
   - library: "python"
   - version: "3.15.0"
   - status: "detected"
   - confidence: 85%

📧 Email sent: "🔮 Future Update Alert: Python 3.15 Planned"
```

**Day 30: More info available**
```
🔍 Serper finds updated roadmap
🤖 Groq analyzes:
   - confidence: 92% (increased!)
   - expected_date: "2025-10-02" (more specific)

💾 Updated FutureUpdateCache:
   - confidence: 92%
   - expected_date: "2025-10-02"

📧 No new email (already notified)
```

**Day 60: Official release**
```
🔍 Serper finds: "Python 3.15.0 released!"
🤖 Groq analyzes:
   - is_released: true
   - version: "3.15.0"

💾 Updates:
   - FutureUpdateCache.status = "released"
   - FutureUpdateCache.promoted_to_release → links to UpdateCache
   - UpdateCache created for the actual release

📧 Email sent: "Python 3.15.0 Released" (normal release notification)
```

---

### Scenario 2: Cancelled Feature

**Day 1: Detected**
```
Library: React
Version: 19.0.0
Status: detected
Confidence: 78%
```

**Day 45: Cancelled**
```
🔍 Admin manually updates via Django Admin
💾 FutureUpdateCache.status = "cancelled"
📧 Optional: Cancellation notification email
```

---

## Querying Future Updates

### View all detected future updates
```python
future_updates = FutureUpdateCache.objects.filter(status='detected')
for update in future_updates:
    print(f"{update.library} {update.version} - {update.confidence}% - {update.expected_date}")
```

### View high-confidence predictions
```python
high_confidence = FutureUpdate Cache.objects.filter(
    status__in=['detected', 'confirmed'],
    confidence__gte=90
)
```

### View releases that were predicted
```python
successful_predictions = FutureUpdateCache.objects.filter(
    status='released',
    promoted_to_release__isnull=False
)
```

---

## Configuration

### Enable/Disable Future Updates

**Per User (Project-level):**
```python
# In Project model
notification_type = "future"  # or "both" (normal + future)
```

**System-wide Threshold:**
```python
# In run_daily_check.py, line 375
MIN_CONFIDENCE = 70  # Only notify if >= 70%
```

---

## Benefits

✅ **Early Warning**: Know about updates months before release  
✅ **Planning Time**: Schedule upgrades proactively  
✅ **Confidence Scoring**: Filter out rumors and speculation  
✅ **Full Lifecycle**: Track from announcement → release → adoption  
✅ **No Duplicates**: Only notify once per future version  
✅ **Automatic Promotion**: Auto-links predictions to actual releases  

---

## Future Enhancements

1. **Cancellation Detection**: Auto-detect when announced versions are cancelled
2. **Confidence Updates**: Adjust confidence as release date approaches
3. **Comparison Reports**: "We predicted X, what actually happened?"
4. **Breaking Changes Preview**: Highlight breaking changes in future versions
5. **Beta/RC Tracking**: Track progression through beta → RC → stable

---

**Questions?** Check the logs at `libtrack.log` for future update detection events!
