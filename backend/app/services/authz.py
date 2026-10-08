"""Membership checks shared by the write services."""

from sqlalchemy.engine import Connection

from app.db import one
from app.errors import AppError


def membership(conn: Connection, user_id: int, family_id: int) -> str | None:
    """Return the role, or None when the user is outside the family."""
    row = one(
        conn,
        '''
        SELECT role FROM family_members
        WHERE user_id = :user_id AND family_id = :family_id
        ''',
        {'user_id': user_id, 'family_id': family_id},
    )
    if row is None:
        return None
    return str(row['role'])


def require_member(conn: Connection, user_id: int, family_id: int) -> str:
    """Return the role or hide the family from non-members."""
    role = membership(conn, user_id, family_id)
    if role is None:
        raise AppError('not_found', '找不到内容', 404)
    return role


def require_owner(conn: Connection, user_id: int, family_id: int) -> None:
    """Allow only the family owner to change structure."""
    role = require_member(conn, user_id, family_id)
    if role != 'owner':
        raise AppError('forbidden', '只有创建者可以修改课程和成员', 403)


def require_course(
    conn: Connection,
    user_id: int,
    course_id: int,
    *,
    owner: bool,
) -> dict:
    """Load a course the user can see.

    A course in another family uses the same not-found response as a
    missing id, so ids cannot be probed.
    """
    course = one(
        conn,
        'SELECT * FROM courses WHERE id = :id',
        {'id': course_id},
    )
    if course is None:
        raise AppError('not_found', '找不到内容', 404)
    role = membership(conn, user_id, int(course['family_id']))
    if role is None:
        raise AppError('not_found', '找不到内容', 404)
    if owner and role != 'owner':
        raise AppError('forbidden', '只有创建者可以修改课程和成员', 403)
    data = dict(course)
    data['role'] = role
    return data
