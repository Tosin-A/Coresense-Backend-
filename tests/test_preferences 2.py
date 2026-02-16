"""
Tests for user preferences endpoints
Verifies notification preference columns and preference updates
"""

import pytest


@pytest.mark.asyncio
async def test_get_preferences_returns_notification_fields(client, mock_supabase, mock_user_id):
    """
    Preferences response should include notification preference fields.
    """
    mock_supabase.set_table_data('user_preferences', [{
        "id": "pref-123",
        "user_id": mock_user_id,
        "messaging_frequency": 3,
        "messaging_style": "balanced",
        "response_length": "medium",
        "quiet_hours_enabled": False,
        "quiet_hours_start": "22:00",
        "quiet_hours_end": "07:00",
        "quiet_hours_days": [0, 1, 2, 3, 4, 5, 6],
        "accountability_level": 5,
        "goals": [],
        "healthkit_enabled": True,
        "healthkit_sync_frequency": "daily",
        "push_notifications": True,
        "task_reminders": True,
        "weekly_reports": False,
    }])

    response = await client.get(
        "/api/v1/preferences",
        headers={"Authorization": "Bearer test-token"}
    )

    assert response.status_code == 200
    data = response.json()

    # Verify notification fields are present
    assert "push_notifications" in data or "pushNotifications" in str(data)
    assert "task_reminders" in data or "taskReminders" in str(data)
    assert "weekly_reports" in data or "weeklyReports" in str(data)


@pytest.mark.asyncio
async def test_update_preferences_accepts_notification_fields(client, mock_supabase, mock_user_id):
    """
    Preferences update should accept notification preference fields.
    """
    mock_supabase.set_table_data('user_preferences', [{
        "id": "pref-123",
        "user_id": mock_user_id,
        "messaging_frequency": 3,
        "push_notifications": True,
        "task_reminders": True,
        "weekly_reports": True,
    }])

    response = await client.put(
        "/api/v1/preferences",
        headers={"Authorization": "Bearer test-token"},
        json={
            "push_notifications": False,
            "task_reminders": False,
            "weekly_reports": True,
        }
    )

    # Should succeed (either 200 or create/update response)
    assert response.status_code in [200, 201]


@pytest.mark.asyncio
async def test_update_preferences_accepts_healthkit_enabled(client, mock_supabase, mock_user_id):
    """
    Preferences update should accept healthkit_enabled toggle.
    """
    mock_supabase.set_table_data('user_preferences', [{
        "id": "pref-123",
        "user_id": mock_user_id,
        "healthkit_enabled": True,
    }])

    response = await client.put(
        "/api/v1/preferences",
        headers={"Authorization": "Bearer test-token"},
        json={
            "healthkit_enabled": False,
        }
    )

    assert response.status_code in [200, 201]


@pytest.mark.asyncio
async def test_get_preferences_returns_defaults_when_none_exist(client, mock_supabase, mock_user_id):
    """
    When no preferences exist, should return sensible defaults.
    """
    mock_supabase.set_table_data('user_preferences', [])

    response = await client.get(
        "/api/v1/preferences",
        headers={"Authorization": "Bearer test-token"}
    )

    # Should still return successfully with defaults
    assert response.status_code == 200
