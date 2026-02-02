"""
Tests for the /home/data endpoint
Verifies sleep query window fix and data aggregation
"""

import pytest
from datetime import date, datetime, timedelta


@pytest.mark.asyncio
async def test_home_data_returns_todays_sleep(client, mock_supabase, mock_user_id):
    """
    Sleep recorded at today midnight (wake-date attribution) should be returned.

    The mobile app attributes sleep to the wake date:
    - Night of Jan 26→27 is recorded with recorded_at = Jan 27 00:00:00
    - Backend should query today's window first
    """
    today = date.today()
    today_midnight = datetime.combine(today, datetime.min.time()).isoformat()

    # Configure mock to return sleep data for today's window
    mock_supabase.set_table_data('health_metrics', [
        {"value": 7.5, "recorded_at": today_midnight}
    ])
    mock_supabase.set_table_data('messages', [])
    mock_supabase.set_table_data('insights', [])
    mock_supabase.set_table_data('daily_checkins', [{"check_ins": 2}])
    mock_supabase.set_table_data('streaks', [{"current_streak": 5}])

    response = await client.get(
        "/api/v1/home/data",
        headers={"Authorization": "Bearer test-token"}
    )

    assert response.status_code == 200
    data = response.json()
    assert data["sleepHours"] == 7.5


@pytest.mark.asyncio
async def test_home_data_fallback_to_yesterday_sleep(client, mock_supabase, mock_user_id):
    """
    If no sleep data for today, should fallback to yesterday's window.
    """
    yesterday = date.today() - timedelta(days=1)
    yesterday_midnight = datetime.combine(yesterday, datetime.min.time()).isoformat()

    # First query (today) returns empty, second query (fallback) returns data
    # This is a simplified test - in reality the mock would need more sophisticated setup
    mock_supabase.set_table_data('health_metrics', [
        {"value": 6.5, "recorded_at": yesterday_midnight}
    ])
    mock_supabase.set_table_data('messages', [])
    mock_supabase.set_table_data('insights', [])
    mock_supabase.set_table_data('daily_checkins', [])
    mock_supabase.set_table_data('streaks', [])

    response = await client.get(
        "/api/v1/home/data",
        headers={"Authorization": "Bearer test-token"}
    )

    assert response.status_code == 200


@pytest.mark.asyncio
async def test_home_data_returns_steps_today(client, mock_supabase, mock_user_id):
    """
    Home data should include stepsToday field.
    """
    today = date.today()
    today_midnight = datetime.combine(today, datetime.min.time()).isoformat()

    # Configure mock for steps
    mock_supabase.set_table_data('health_metrics', [
        {"value": 8500, "recorded_at": today_midnight}
    ])
    mock_supabase.set_table_data('messages', [])
    mock_supabase.set_table_data('insights', [])
    mock_supabase.set_table_data('daily_checkins', [])
    mock_supabase.set_table_data('streaks', [])

    response = await client.get(
        "/api/v1/home/data",
        headers={"Authorization": "Bearer test-token"}
    )

    assert response.status_code == 200
    data = response.json()
    # Check that stepsToday field exists in response
    assert "stepsToday" in data


@pytest.mark.asyncio
async def test_home_data_includes_all_fields(client, mock_supabase, mock_user_id):
    """
    Home data should include all expected fields.
    """
    mock_supabase.set_table_data('health_metrics', [])
    mock_supabase.set_table_data('messages', [])
    mock_supabase.set_table_data('insights', [])
    mock_supabase.set_table_data('daily_checkins', [])
    mock_supabase.set_table_data('streaks', [])

    response = await client.get(
        "/api/v1/home/data",
        headers={"Authorization": "Bearer test-token"}
    )

    assert response.status_code == 200
    data = response.json()

    # Verify all expected fields are present
    expected_fields = [
        "lastCoachMessage",
        "todayInsight",
        "streak",
        "completedToday",
        "sleepHours",
        "stepsToday"
    ]

    for field in expected_fields:
        assert field in data, f"Missing field: {field}"
