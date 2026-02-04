import uuid
from dataclasses import asdict
from datetime import datetime, timedelta, timezone
from typing import Optional
from unittest.mock import MagicMock

from dstack._internal.cli.services.events import EventListFilters, EventTracker
from dstack._internal.core.models.events import Event, EventTarget, EventTargetType
from dstack._internal.server.schemas.events import LIST_EVENTS_DEFAULT_LIMIT


class TestEventTracker:
    def create_test_event(
        self,
        event_id: Optional[uuid.UUID] = None,
        recorded_at: Optional[datetime] = None,
        message: str = "Test event",
    ) -> Event:
        if event_id is None:
            event_id = uuid.uuid4()
        if recorded_at is None:
            recorded_at = datetime.now(timezone.utc)

        return Event(
            id=event_id,
            message=message,
            recorded_at=recorded_at,
            actor_user_id=uuid.uuid4(),
            actor_user="test_user",
            targets=[
                EventTarget(
                    type=EventTargetType.RUN,
                    project_id=uuid.uuid4(),
                    project_name="test_project",
                    id=uuid.uuid4(),
                    name="test_run",
                )
            ],
        )

    def test_poll_no_since(self):
        mock_client = MagicMock()
        filters = EventListFilters(target_runs=[uuid.uuid4()])

        tracker = EventTracker(
            client=mock_client,
            filters=filters,
            since=None,
            event_delay_tolerance=timedelta(seconds=20),
        )

        # First poll - requests latest existing events

        event1 = self.create_test_event(
            recorded_at=datetime(2023, 1, 1, 9, 0, tzinfo=timezone.utc)
        )
        event2 = self.create_test_event(
            recorded_at=datetime(2023, 1, 1, 10, 0, tzinfo=timezone.utc)
        )
        mock_client.list.return_value = [event2, event1]  # reversed due to ascending=False

        events = list(tracker.poll())

        assert events == [event1, event2]
        mock_client.list.assert_called_once_with(
            ascending=False,
            **asdict(filters),
        )

        # Second poll - requests events after the latest existing event

        mock_client.list.reset_mock()
        mock_client.list.return_value = []

        events = list(tracker.poll())

        assert events == []
        mock_client.list.assert_called_once_with(
            ascending=True,
            **asdict(filters),
            prev_recorded_at=event2.recorded_at - timedelta(seconds=20),
            prev_id=None,
            limit=LIST_EVENTS_DEFAULT_LIMIT,
        )

    def test_poll_with_since(self):
        mock_client = MagicMock()
        filters = EventListFilters(target_runs=[uuid.uuid4()])

        tracker = EventTracker(
            client=mock_client,
            filters=filters,
            since=datetime(2023, 1, 1, 8, 0, tzinfo=timezone.utc),
            event_delay_tolerance=timedelta(seconds=20),
        )

        # First poll - requests events after `since`

        event1 = self.create_test_event(
            recorded_at=datetime(2023, 1, 1, 9, 0, tzinfo=timezone.utc)
        )
        event2 = self.create_test_event(
            recorded_at=datetime(2023, 1, 1, 10, 0, tzinfo=timezone.utc)
        )
        mock_client.list.return_value = [event1, event2]

        events = list(tracker.poll())

        assert events == [event1, event2]
        mock_client.list.assert_called_once_with(
            ascending=True,
            **asdict(filters),
            prev_recorded_at=datetime(2023, 1, 1, 8, 0, tzinfo=timezone.utc),
            prev_id=None,
            limit=LIST_EVENTS_DEFAULT_LIMIT,
        )

        # Second poll - requests events after the latest event

        mock_client.list.reset_mock()
        mock_client.list.return_value = []

        events = list(tracker.poll())

        assert events == []
        mock_client.list.assert_called_once_with(
            ascending=True,
            **asdict(filters),
            prev_recorded_at=event2.recorded_at - timedelta(seconds=20),
            prev_id=None,
            limit=LIST_EVENTS_DEFAULT_LIMIT,
        )

    def test_poll_with_since_never_uses_prev_recorded_at_earlier_than_since(self):
        mock_client = MagicMock()
        filters = EventListFilters(target_runs=[uuid.uuid4()])
        since = datetime(2023, 1, 1, 10, 0, tzinfo=timezone.utc)

        tracker = EventTracker(
            client=mock_client,
            filters=filters,
            since=datetime(2023, 1, 1, 10, 0, tzinfo=timezone.utc),
            event_delay_tolerance=timedelta(seconds=20),
        )

        # First poll - returns an event that is 5 seconds newer than `since`

        event1 = self.create_test_event(recorded_at=since + timedelta(seconds=5))
        mock_client.list.return_value = [event1]

        events = list(tracker.poll())

        assert events == [event1]
        mock_client.list.assert_called_once_with(
            ascending=True,
            **asdict(filters),
            prev_recorded_at=since,
            prev_id=None,
            limit=LIST_EVENTS_DEFAULT_LIMIT,
        )

        # Second poll - prev_recorded_at should still be `since` (not event1 - 20s)

        mock_client.list.reset_mock()
        mock_client.list.return_value = []

        events = list(tracker.poll())

        assert events == []
        mock_client.list.assert_called_once_with(
            ascending=True,
            **asdict(filters),
            prev_recorded_at=since,
            prev_id=None,
            limit=LIST_EVENTS_DEFAULT_LIMIT,
        )

    def test_poll_no_since_always_empty_response(self):
        mock_client = MagicMock()
        filters = EventListFilters(target_runs=[uuid.uuid4()])

        tracker = EventTracker(
            client=mock_client,
            filters=filters,
            since=None,
            event_delay_tolerance=timedelta(seconds=20),
        )

        for _ in range(2):
            mock_client.list.reset_mock()
            mock_client.list.return_value = []
            events = list(tracker.poll())
            assert events == []
            mock_client.list.assert_called_once_with(
                ascending=False,
                **asdict(filters),
            )

    def test_poll_with_since_always_empty_response(self):
        mock_client = MagicMock()
        filters = EventListFilters(target_runs=[uuid.uuid4()])

        tracker = EventTracker(
            client=mock_client,
            filters=filters,
            since=datetime(2023, 1, 1, 8, 0, tzinfo=timezone.utc),
            event_delay_tolerance=timedelta(seconds=20),
        )

        for _ in range(2):
            mock_client.list.reset_mock()
            mock_client.list.return_value = []
            events = list(tracker.poll())
            assert events == []
            mock_client.list.assert_called_once_with(
                ascending=True,
                **asdict(filters),
                prev_recorded_at=datetime(2023, 1, 1, 8, 0, tzinfo=timezone.utc),
                prev_id=None,
                limit=LIST_EVENTS_DEFAULT_LIMIT,
            )

    def test_poll_event_deduplication(self):
        mock_client = MagicMock()
        filters = EventListFilters(target_runs=[uuid.uuid4()])

        tracker = EventTracker(
            client=mock_client,
            filters=filters,
            since=datetime(2023, 1, 1, 8, 0, tzinfo=timezone.utc),
            event_delay_tolerance=timedelta(seconds=20),
        )

        # First poll - returns event1 and event2

        event1 = self.create_test_event(
            recorded_at=datetime(2023, 1, 1, 9, 0, tzinfo=timezone.utc)
        )
        event2 = self.create_test_event(
            recorded_at=datetime(2023, 1, 1, 10, 0, tzinfo=timezone.utc)
        )
        mock_client.list.return_value = [event1, event2]

        events = list(tracker.poll())

        assert events == [event1, event2]
        mock_client.list.assert_called_once_with(
            ascending=True,
            **asdict(filters),
            prev_recorded_at=datetime(2023, 1, 1, 8, 0, tzinfo=timezone.utc),
            prev_id=None,
            limit=LIST_EVENTS_DEFAULT_LIMIT,
        )

        # Second poll - returns event2 (duplicate) and event3 (new)

        mock_client.list.reset_mock()
        event3 = self.create_test_event(
            recorded_at=datetime(2023, 1, 1, 11, 0, tzinfo=timezone.utc)
        )
        mock_client.list.return_value = [event2, event3]

        events = list(tracker.poll())

        assert events == [event3]  # does not return duplicate event2
        mock_client.list.assert_called_once_with(
            ascending=True,
            **asdict(filters),
            prev_recorded_at=event2.recorded_at - timedelta(seconds=20),
            prev_id=None,
            limit=LIST_EVENTS_DEFAULT_LIMIT,
        )

    def test_poll_respects_pagination(self):
        mock_client = MagicMock()
        filters = EventListFilters(target_runs=[uuid.uuid4()])

        tracker = EventTracker(
            client=mock_client,
            filters=filters,
            since=datetime(2023, 1, 1, 8, 0, tzinfo=timezone.utc),
            event_delay_tolerance=timedelta(seconds=20),
        )

        ###
        # First poll - create (1.5 * default limit) events
        ###

        num_events = int(LIST_EVENTS_DEFAULT_LIMIT * 1.5)
        events = [
            self.create_test_event(
                recorded_at=datetime(2023, 1, 1, 9, 0, tzinfo=timezone.utc) + timedelta(seconds=i)
            )
            for i in range(num_events)
        ]

        # Mock pagination: first call returns first batch, second call returns remaining events
        call_count = 0

        def mock_list(**kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return events[:LIST_EVENTS_DEFAULT_LIMIT]  # First batch
            elif call_count == 2:
                return events[LIST_EVENTS_DEFAULT_LIMIT:]  # Remaining events
            else:
                return []

        mock_client.list.side_effect = mock_list

        result_events = list(tracker.poll())

        assert result_events == events
        assert mock_client.list.call_count == 2

        # Verify first call
        first_call = mock_client.list.call_args_list[0]
        assert first_call[1]["ascending"] == True
        assert first_call[1]["prev_recorded_at"] == datetime(2023, 1, 1, 8, 0, tzinfo=timezone.utc)
        assert first_call[1]["prev_id"] is None
        assert first_call[1]["limit"] == LIST_EVENTS_DEFAULT_LIMIT

        # Verify second call (pagination)
        second_call = mock_client.list.call_args_list[1]
        assert second_call[1]["ascending"] == True
        assert (
            second_call[1]["prev_recorded_at"] == events[LIST_EVENTS_DEFAULT_LIMIT - 1].recorded_at
        )
        assert second_call[1]["prev_id"] == events[LIST_EVENTS_DEFAULT_LIMIT - 1].id
        assert second_call[1]["limit"] == LIST_EVENTS_DEFAULT_LIMIT

        ###
        # Second poll - should make one call for new events
        ###

        mock_client.reset_mock()
        mock_client.list.return_value = []

        result_events = list(tracker.poll())

        assert result_events == []
        mock_client.list.assert_called_once_with(
            ascending=True,
            **asdict(filters),
            prev_recorded_at=events[-1].recorded_at - timedelta(seconds=20),
            prev_id=None,
            limit=LIST_EVENTS_DEFAULT_LIMIT,
        )
