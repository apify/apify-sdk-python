from __future__ import annotations

import pytest

from apify import ActorEventTypes


@pytest.mark.parametrize(
    'member',
    [
        pytest.param('SYSTEM_INFO', id='system-info'),
        pytest.param('PERSIST_STATE', id='persist-state'),
        pytest.param('MIGRATING', id='migrating'),
        pytest.param('ABORTING', id='aborting'),
    ],
)
def test_actor_event_types_enum_member_access_points_to_migration(member: str) -> None:
    """Pre-v4 enum-member access on `ActorEventTypes` errors with a pointer to `apify.Event`, not a bare error."""
    with pytest.raises(AttributeError, match=r'apify\.Event'):
        getattr(ActorEventTypes, member)
