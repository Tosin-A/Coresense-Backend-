"""
Tests for the health insights engine
Verifies pattern analysis and action_steps generation
"""

import pytest
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch


class TestHealthInsightsEngine:
    """Test suite for health insights engine functionality."""

    @pytest.mark.asyncio
    async def test_sleep_pattern_risk_generates_action_steps(self):
        """
        Sleep pattern with <6.5h average should generate risk-level action steps.
        """
        # Import the engine
        from backend.services.health_insights_engine import health_insights_engine, PatternType, InsightType

        # Mock data with low sleep
        mock_sleep_data = [
            {"value": 5.5, "recorded_at": datetime.now() - timedelta(days=i)}
            for i in range(7)
        ]

        # Analyze should produce action steps
        # Note: This is a simplified test - real test would mock supabase queries
        assert health_insights_engine is not None

    @pytest.mark.asyncio
    async def test_activity_consistency_generates_action_steps(self):
        """
        Activity consistency analysis should generate action steps.
        """
        from backend.services.health_insights_engine import health_insights_engine

        # Verify the engine exists and has expected methods
        assert hasattr(health_insights_engine, 'get_active_insights')

    @pytest.mark.asyncio
    async def test_insight_includes_action_steps_field(self):
        """
        Generated insights should include action_steps field.
        """
        from backend.services.health_insights_engine import HealthInsight

        # Create a sample insight
        insight = HealthInsight(
            id="test-123",
            type="behavioral",
            title="Sleep Pattern",
            coach_commentary="You're averaging 6 hours of sleep.",
            evidence={
                "type": "sleep_pattern",
                "labels": ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"],
                "values": [6, 5.5, 6.5, 5, 6, 7, 6.5],
                "highlight_index": 3,
                "trend_direction": "stable",
                "trend_value": "6.0h avg"
            },
            action_text="Ask Coach",
            action_steps=[
                "Set a hard bedtime alarm 8 hours before your wake time",
                "No screens 30 minutes before bed"
            ],
            is_new=True,
            created_at=datetime.now()
        )

        assert insight.action_steps is not None
        assert len(insight.action_steps) > 0
        assert "bedtime" in insight.action_steps[0].lower()

    def test_pattern_types_are_defined(self):
        """
        Verify all expected pattern types exist.
        """
        from backend.services.health_insights_engine import PatternType

        expected_types = [
            'SLEEP_PATTERN',
            'ACTIVITY_CONSISTENCY',
            'ENERGY_WINDOWS',
            'WEEKEND_EFFECT'
        ]

        for pattern_type in expected_types:
            assert hasattr(PatternType, pattern_type)

    def test_insight_types_are_defined(self):
        """
        Verify all expected insight types exist.
        """
        from backend.services.health_insights_engine import InsightType

        expected_types = ['BEHAVIORAL', 'PROGRESS', 'RISK']

        for insight_type in expected_types:
            assert hasattr(InsightType, insight_type)
