"""Test-only factories that preserve current workspace invariants."""

import uuid

from django.contrib.auth import get_user_model

from .ownership import create_space_with_owner


def create_test_space(*, organization, owner=None, **fields):
    """Create a fully valid workspace for tests not concerned with ownership."""

    if owner is None:
        suffix = uuid.uuid4().hex
        owner = get_user_model().objects.create_user(
            username=f"workspace-fixture-{suffix}",
            email=f"workspace-fixture-{suffix}@example.test",
            password=None,
        )
    return create_space_with_owner(
        organization=organization,
        owner=owner,
        **fields,
    )
