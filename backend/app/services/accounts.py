"""Account, session, family, and invitation services."""

from datetime import timedelta

from sqlalchemy.engine import Engine

from app.db import many, one, run, transaction, write_audit
from app.errors import AppError
from app.security import (
    dummy_verify,
    hash_password,
    hash_token,
    new_invite_code,
    new_session_token,
    verify_password,
)
from app.services.authz import require_member, require_owner
from app.timeutil import iso_utc, now_utc

INVITE_DAYS = 7


def _profile(conn, user_id: int) -> dict:
    user = one(
        conn,
        '''
        SELECT id, display_name, login_name
        FROM users WHERE id = :id
        ''',
        {'id': user_id},
    )
    families = many(
        conn,
        '''
        SELECT f.id, f.name, m.role
        FROM family_members m
        JOIN families f ON f.id = m.family_id
        WHERE m.user_id = :user_id
        ORDER BY m.joined_at, f.id
        ''',
        {'user_id': user_id},
    )
    return {
        'user': {
            'id': user['id'],
            'display_name': user['display_name'],
            'login_name': user['login_name'],
        },
        'families': [dict(row) for row in families],
    }


def _insert_session(conn, user_id: int, session_days: int) -> str:
    token = new_session_token()
    moment = now_utc()
    run(
        conn,
        '''
        INSERT INTO sessions (user_id, token_hash, expires_at, created_at)
        VALUES (:user_id, :token_hash, :expires_at, :created_at)
        ''',
        {
            'user_id': user_id,
            'token_hash': hash_token(token),
            'expires_at': iso_utc(moment + timedelta(days=session_days)),
            'created_at': iso_utc(moment),
        },
    )
    return token


def find_login(conn, login_name: str):
    """Return the user row for a normalized login name."""
    return one(
        conn,
        'SELECT * FROM users WHERE login_name = :login_name',
        {'login_name': login_name},
    )


def user_from_token(conn, token: str):
    """Return the user bound to a live session token."""
    return one(
        conn,
        '''
        SELECT u.id, u.display_name, u.login_name
        FROM sessions s
        JOIN users u ON u.id = s.user_id
        WHERE s.token_hash = :token_hash AND s.expires_at > :now
        ''',
        {'token_hash': hash_token(token), 'now': iso_utc()},
    )


def register_user(
    engine: Engine,
    login_name: str,
    password: str,
    display_name: str,
    session_days: int,
) -> tuple[dict, str]:
    """Create a user and a session. The token is not part of the profile."""
    created_at = iso_utc()
    try:
        with transaction(engine) as conn:
            result = run(
                conn,
                '''
                INSERT INTO users (
                    display_name, login_name, password_hash, created_at
                ) VALUES (
                    :display_name, :login_name, :password_hash, :created_at
                )
                ''',
                {
                    'display_name': display_name,
                    'login_name': login_name,
                    'password_hash': hash_password(password),
                    'created_at': created_at,
                },
            )
            user_id = int(result.lastrowid)
            token = _insert_session(conn, user_id, session_days)
            profile = _profile(conn, user_id)
    except IntegrityError as exc:
        raise AppError('taken', '这个用户名已经注册', 409) from exc
    return profile, token


def login_user(
    engine: Engine,
    login_name: str,
    password: str,
    session_days: int,
) -> tuple[dict, str]:
    """Open a session when the password matches."""
    with transaction(engine) as conn:
        user = find_login(conn, login_name)
        if user is None:
            dummy_verify(password)
            raise AppError('invalid_login', '用户名或密码不正确', 401)
        if not verify_password(user['password_hash'], password):
            raise AppError('invalid_login', '用户名或密码不正确', 401)
        token = _insert_session(conn, int(user['id']), session_days)
        profile = _profile(conn, int(user['id']))
    return profile, token


def logout(engine: Engine, token: str) -> None:
    """Delete the session for a raw cookie token."""
    with transaction(engine) as conn:
        run(
            conn,
            'DELETE FROM sessions WHERE token_hash = :token_hash',
            {'token_hash': hash_token(token)},
        )


def profile_for(engine: Engine, user_id: int) -> dict:
    """Return the current user and their families."""
    with transaction(engine) as conn:
        return _profile(conn, user_id)


def _already_in_family(conn, user_id: int) -> bool:
    row = one(
        conn,
        '''
        SELECT family_id FROM family_members
        WHERE user_id = :user_id LIMIT 1
        ''',
        {'user_id': user_id},
    )
    return row is not None


def create_family(engine: Engine, user_id: int, name: str) -> dict:
    """Create a family and make the caller its owner."""
    moment = iso_utc()
    with transaction(engine) as conn:
        if _already_in_family(conn, user_id):
            raise AppError('one_family', '目前只支持加入一个家庭', 400)
        result = run(
            conn,
            '''
            INSERT INTO families (name, owner_user_id, created_at)
            VALUES (:name, :owner_user_id, :created_at)
            ''',
            {
                'name': name,
                'owner_user_id': user_id,
                'created_at': moment,
            },
        )
        family_id = int(result.lastrowid)
        run(
            conn,
            '''
            INSERT INTO family_members (family_id, user_id, role, joined_at)
            VALUES (:family_id, :user_id, 'owner', :joined_at)
            ''',
            {
                'family_id': family_id,
                'user_id': user_id,
                'joined_at': moment,
            },
        )
        write_audit(
            conn,
            user_id,
            family_id,
            'family',
            family_id,
            'create_family',
            f'创建家庭「{name}」',
            moment,
        )
    return {'id': family_id, 'name': name, 'role': 'owner'}


def create_invitation(engine: Engine, user_id: int, family_id: int) -> dict:
    """Issue a one-time invite code. The plaintext is returned once."""
    moment = now_utc()
    expires = iso_utc(moment + timedelta(days=INVITE_DAYS))
    created_at = iso_utc(moment)
    with transaction(engine) as conn:
        require_owner(conn, user_id, family_id)
        code = new_invite_code()
        run(
            conn,
            '''
            INSERT INTO invitations (
                family_id, code_hash, expires_at,
                created_by, created_at
            ) VALUES (
                :family_id, :code_hash, :expires_at,
                :created_by, :created_at
            )
            ''',
            {
                'family_id': family_id,
                'code_hash': hash_token(code),
                'expires_at': expires,
                'created_by': user_id,
                'created_at': created_at,
            },
        )
        write_audit(
            conn,
            user_id,
            family_id,
            'invitation',
            None,
            'invite',
            '生成了邀请码',
            created_at,
        )
    return {'code': code, 'expires_at': expires}


def accept_invitation(engine: Engine, user_id: int, code: str) -> dict:
    """Join the family named by a live invite code."""
    moment = iso_utc()
    with transaction(engine) as conn:
        if _already_in_family(conn, user_id):
            raise AppError('one_family', '目前只支持加入一个家庭', 400)
        invite = one(
            conn,
            '''
            SELECT * FROM invitations
            WHERE code_hash = :code_hash
            ''',
            {'code_hash': hash_token(code)},
        )
        if invite is None:
            raise AppError('bad_invite', '邀请码不正确', 400)
        if invite['used_at'] is not None:
            raise AppError('bad_invite', '邀请码已使用', 400)
        if invite['expires_at'] <= moment:
            raise AppError('bad_invite', '邀请码已过期', 400)
        family_id = int(invite['family_id'])
        run(
            conn,
            '''
            UPDATE invitations
            SET used_by = :used_by, used_at = :used_at
            WHERE id = :id
            ''',
            {'used_by': user_id, 'used_at': moment, 'id': invite['id']},
        )
        run(
            conn,
            '''
            INSERT INTO family_members (family_id, user_id, role, joined_at)
            VALUES (:family_id, :user_id, 'member', :joined_at)
            ''',
            {
                'family_id': family_id,
                'user_id': user_id,
                'joined_at': moment,
            },
        )
        family = one(
            conn,
            'SELECT name FROM families WHERE id = :id',
            {'id': family_id},
        )
        user = one(
            conn,
            'SELECT display_name FROM users WHERE id = :id',
            {'id': user_id},
        )
        write_audit(
            conn,
            user_id,
            family_id,
            'family',
            family_id,
            'accept_invite',
            f'{user["display_name"]}加入了家庭',
            moment,
        )
    return {
        'id': family_id,
        'name': family['name'],
        'role': 'member',
    }


def list_members(engine: Engine, user_id: int, family_id: int) -> dict:
    """Return members of a family the caller belongs to."""
    with transaction(engine) as conn:
        require_member(conn, user_id, family_id)
        rows = many(
            conn,
            '''
            SELECT u.id AS user_id, u.display_name, m.role, m.joined_at
            FROM family_members m
            JOIN users u ON u.id = m.user_id
            WHERE m.family_id = :family_id
            ORDER BY m.joined_at, u.id
            ''',
            {'family_id': family_id},
        )
    return {'members': [dict(row) for row in rows]}


def remove_member(
    engine: Engine,
    user_id: int,
    family_id: int,
    member_user_id: int,
) -> None:
    """Remove a non-owner member."""
    moment = iso_utc()
    with transaction(engine) as conn:
        require_owner(conn, user_id, family_id)
        member = one(
            conn,
            '''
            SELECT m.role, u.display_name
            FROM family_members m
            JOIN users u ON u.id = m.user_id
            WHERE m.family_id = :family_id AND m.user_id = :member_id
            ''',
            {'family_id': family_id, 'member_id': member_user_id},
        )
        if member is None:
            raise AppError('not_found', '找不到内容', 404)
        if member['role'] == 'owner':
            raise AppError('forbidden', '不能移除创建者', 400)
        run(
            conn,
            '''
            DELETE FROM family_members
            WHERE family_id = :family_id AND user_id = :member_id
            ''',
            {'family_id': family_id, 'member_id': member_user_id},
        )
        write_audit(
            conn,
            user_id,
            family_id,
            'member',
            member_user_id,
            'remove_member',
            f'移除了成员{member["display_name"]}',
            moment,
        )
