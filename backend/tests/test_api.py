"""Ledger, auth, and family isolation."""

import sqlite3
import threading
from concurrent.futures import ThreadPoolExecutor
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.backup import backup_database
from app.main import create_app
from app.services.lessons import check_in
from app.timeutil import plus_days, today_shanghai


@pytest.fixture()
def app(tmp_path):
    return create_app(str(tmp_path / 'test.db'))


@pytest.fixture()
def client(app):
    with TestClient(app) as test_client:
        yield test_client


def assert_status(response, status):
    assert response.status_code == status, response.text
    if status == 204:
        return None
    return response.json()


def register(client, login, display='家长'):
    return assert_status(
        client.post(
            '/api/auth/register',
            json={
                'login_name': login,
                'password': 'password1',
                'display_name': display,
            },
        ),
        201,
    )


def family_of(client, name='悠悠的家'):
    body = assert_status(
        client.post('/api/families', json={'name': name}),
        201,
    )
    return body['id']


def add_course(client, family_id, schedules, name='英语'):
    return assert_status(
        client.post(
            f'/api/families/{family_id}/courses',
            json={'name': name, 'schedules': schedules},
        ),
        201,
    )


def add_package(client, course_id, total, opening=0, title='第一期'):
    return assert_status(
        client.post(
            f'/api/courses/{course_id}/packages',
            json={
                'title': title,
                'total_units': total,
                'opening_consumed_units': opening,
            },
        ),
        201,
    )


def slot(weekday, local_time, effective_from='2020-01-01'):
    return {
        'weekday': weekday,
        'local_time': local_time,
        'effective_from': effective_from,
    }


def lesson_count(app) -> int:
    with app.state.engine.begin() as conn:
        return int(
            conn.execute(text('SELECT COUNT(*) FROM lesson_records')).scalar()
        )


def test_health(client) -> None:
    assert assert_status(client.get('/api/health'), 200) == {'ok': True}


def test_login_and_logout(client) -> None:
    register(client, 'mama', '妈妈')
    assert_status(client.post('/api/auth/logout'), 204)
    assert client.get('/api/me').status_code == 401
    assert_status(
        client.post(
            '/api/auth/login',
            json={'login_name': 'Mama', 'password': 'password1'},
        ),
        200,
    )
    bad = client.post(
        '/api/auth/login',
        json={'login_name': 'mama', 'password': 'wrong-pass'},
    )
    assert bad.status_code == 401


def test_opening_balance_identity(client) -> None:
    register(client, 'mama')
    family_id = family_of(client)
    today = today_shanghai()
    course = add_course(
        client,
        family_id,
        [
            slot(0, '16:30'),
            slot(4, '19:00'),
        ],
    )
    add_package(client, course['id'], 10, 3)
    home = assert_status(client.get(f'/api/families/{family_id}/home'), 200)
    card = home['courses'][0]
    assert card['package']['used_units'] == 3
    assert card['package']['remaining_units'] == 7
    assert (
        card['package']['used_units'] + card['package']['remaining_units']
        == card['package']['total_units']
    )
    monday = today
    while monday.weekday() != 0:
        monday = plus_days(monday, -1)
    friday = today
    while friday.weekday() != 4:
        friday = plus_days(friday, -1)
    leave = assert_status(
        client.post(
            '/api/lessons',
            json={
                'course_id': course['id'],
                'local_date': monday.isoformat(),
                'local_time': '16:30',
                'source': 'planned',
                'status': 'leave',
                'charge': False,
            },
        ),
        201,
    )
    assert leave['package']['remaining_units'] == 7
    attended = assert_status(
        client.post(
            '/api/lessons',
            json={
                'course_id': course['id'],
                'local_date': friday.isoformat(),
                'local_time': '19:00',
                'source': 'planned',
                'status': 'attended',
            },
        ),
        201,
    )
    assert attended['package']['used_units'] == 4
    assert attended['package']['remaining_units'] == 6
    assert attended['package']['used_units'] + attended['package']['remaining_units'] == 10


def test_calendar_does_not_store_plans(client, app) -> None:
    register(client, 'mama')
    family_id = family_of(client)
    add_course(
        client,
        family_id,
        [slot(0, '16:30'), slot(4, '19:00')],
    )
    today = today_shanghai()
    body = assert_status(
        client.get(
            f'/api/families/{family_id}/calendar',
            params={
                'start': plus_days(today, -10).isoformat(),
                'end': plus_days(today, 10).isoformat(),
            },
        ),
        200,
    )
    found = {
        (item['local_time'], date_row['date'])
        for date_row in body['days']
        for item in date_row['items']
        if item['state'] == 'scheduled'
    }
    assert any(time == '16:30' for time, _day in found)
    assert any(time == '19:00' for time, _day in found)
    assert lesson_count(app) == 0


def test_quick_check_in_ignores_other_days(client, app) -> None:
    register(client, 'mama')
    family_id = family_of(client)
    today = today_shanghai()
    other = (today.weekday() + 1) % 7
    course = add_course(client, family_id, [slot(other, '16:30')])
    add_package(client, course['id'], 8)
    missed = client.post(f'/api/courses/{course["id"]}/quick-check-in')
    assert missed.status_code == 409
    assert missed.json()['detail']['code'] == 'none_today'
    assert lesson_count(app) == 0


def test_quick_repeat_and_concurrent(app) -> None:
    with TestClient(app) as client:
        register(client, 'mama')
        me = assert_status(client.get('/api/me'), 200)
        user_id = me['user']['id']
        family_id = family_of(client)
        today = today_shanghai()
        course = add_course(
            client,
            family_id,
            [slot(today.weekday(), '16:30')],
        )
        add_package(client, course['id'], 5)
        first = assert_status(
            client.post(f'/api/courses/{course["id"]}/quick-check-in'),
            201,
        )
        second = assert_status(
            client.post(f'/api/courses/{course["id"]}/quick-check-in'),
            200,
        )
        assert first['lesson']['id'] == second['lesson']['id']
        assert second['created'] is False
        assert second['package']['used_units'] == 1
        assert lesson_count(app) == 1
        course_two = add_course(
            client,
            family_id,
            [slot(today.weekday(), '19:00')],
            name='舞蹈',
        )
        add_package(client, course_two['id'], 4)
        course_id = course_two['id']

    barrier = threading.Barrier(2)

    def worker():
        barrier.wait(timeout=5)
        return check_in(
            app.state.engine,
            user_id,
            course_id,
            today.isoformat(),
            '19:00',
            'planned',
            'attended',
            False,
            '',
        )

    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(worker) for _ in range(2)]
        results = [future.result(timeout=10) for future in futures]
    created = sorted(item['created'] for item in results)
    ids = {item['lesson']['id'] for item in results}
    assert created == [False, True]
    assert len(ids) == 1
    assert results[0]['package']['remaining_units'] == 3


def test_void_then_check_in_again(client, app) -> None:
    register(client, 'mama')
    family_id = family_of(client)
    today = today_shanghai()
    course = add_course(client, family_id, [slot(today.weekday(), '16:30')])
    add_package(client, course['id'], 4, 1)
    created = assert_status(
        client.post(f'/api/courses/{course["id"]}/quick-check-in'),
        201,
    )
    refused = client.post(
        f'/api/lessons/{created["lesson"]["id"]}/void',
        json={'confirm': False},
    )
    assert refused.status_code == 400
    voided = assert_status(
        client.post(
            f'/api/lessons/{created["lesson"]["id"]}/void',
            json={'confirm': True},
        ),
        200,
    )
    assert voided['package']['used_units'] == 1
    assert voided['package']['remaining_units'] == 3
    again = assert_status(
        client.post(f'/api/courses/{course["id"]}/quick-check-in'),
        201,
    )
    assert again['lesson']['id'] != created['lesson']['id']
    assert again['package']['used_units'] == 2
    assert lesson_count(app) == 2


def test_leave_charge_and_patch(client) -> None:
    register(client, 'mama')
    family_id = family_of(client)
    today = today_shanghai()
    course = add_course(client, family_id, [slot(today.weekday(), '16:30')])
    add_package(client, course['id'], 6)
    created = assert_status(
        client.post(
            '/api/lessons',
            json={
                'course_id': course['id'],
                'local_date': today.isoformat(),
                'local_time': '16:30',
                'source': 'planned',
                'status': 'leave',
                'charge': False,
            },
        ),
        201,
    )
    assert created['package']['used_units'] == 0
    missing = client.patch(
        f'/api/lessons/{created["lesson"]["id"]}',
        json={'status': 'leave', 'charge': True, 'confirm': False},
    )
    assert missing.status_code == 400
    patched = assert_status(
        client.patch(
            f'/api/lessons/{created["lesson"]["id"]}',
            json={'status': 'leave', 'charge': True, 'confirm': True},
        ),
        200,
    )
    assert patched['package']['used_units'] == 1
    assert patched['package']['remaining_units'] == 5
    assert patched['package']['used_units'] + patched['package']['remaining_units'] == 6


def test_future_attended_blocked(client, app) -> None:
    register(client, 'mama')
    family_id = family_of(client)
    tomorrow = plus_days(today_shanghai(), 1)
    course = add_course(
        client,
        family_id,
        [slot(tomorrow.weekday(), '10:00')],
    )
    add_package(client, course['id'], 5)
    refused = client.post(
        '/api/lessons',
        json={
            'course_id': course['id'],
            'local_date': tomorrow.isoformat(),
            'local_time': '10:00',
            'source': 'planned',
            'status': 'attended',
        },
    )
    assert refused.status_code == 400
    assert refused.json()['detail']['code'] == 'future'
    allowed = assert_status(
        client.post(
            '/api/lessons',
            json={
                'course_id': course['id'],
                'local_date': tomorrow.isoformat(),
                'local_time': '10:00',
                'source': 'planned',
                'status': 'leave',
            },
        ),
        201,
    )
    assert allowed['package']['remaining_units'] == 5
    assert lesson_count(app) == 1


def test_backfill_and_two_makeups(client) -> None:
    register(client, 'mama')
    family_id = family_of(client)
    today = today_shanghai()
    course = add_course(client, family_id, [slot(0, '16:30')])
    add_package(client, course['id'], 10)
    past = plus_days(today, -3)
    while past.weekday() != 0:
        past = plus_days(past, -1)
    assert_status(
        client.post(
            '/api/lessons',
            json={
                'course_id': course['id'],
                'local_date': past.isoformat(),
                'local_time': '16:30',
                'source': 'planned',
                'status': 'attended',
            },
        ),
        201,
    )
    for local_time in ('09:00', '15:00'):
        assert_status(
            client.post(
                '/api/lessons',
                json={
                    'course_id': course['id'],
                    'local_date': past.isoformat(),
                    'local_time': local_time,
                    'source': 'manual',
                    'status': 'attended',
                },
            ),
            201,
        )
    home = assert_status(client.get(f'/api/families/{family_id}/home'), 200)
    assert home['courses'][0]['package']['used_units'] == 3
    assert home['courses'][0]['package']['remaining_units'] == 7


def test_schedule_change_keeps_history(client) -> None:
    register(client, 'mama')
    family_id = family_of(client)
    today = today_shanghai()
    course = add_course(client, family_id, [slot(0, '16:30')])
    add_package(client, course['id'], 10)
    monday = today
    while monday.weekday() != 0:
        monday = plus_days(monday, -1)
    assert_status(
        client.post(
            '/api/lessons',
            json={
                'course_id': course['id'],
                'local_date': monday.isoformat(),
                'local_time': '16:30',
                'source': 'planned',
                'status': 'attended',
            },
        ),
        201,
    )
    detail = assert_status(client.get(f'/api/courses/{course["id"]}'), 200)
    schedule_id = detail['schedules'][0]['id']
    effective_on = plus_days(today, 1).isoformat()
    assert_status(
        client.post(
            f'/api/schedules/{schedule_id}/replace',
            json={
                'weekday': 0,
                'local_time': '17:00',
                'effective_on': effective_on,
            },
        ),
        200,
    )
    detail = assert_status(client.get(f'/api/courses/{course["id"]}'), 200)
    kept = [
        row
        for row in detail['lessons']
        if row['local_date'] == monday.isoformat() and row['voided_at'] is None
    ]
    assert kept[0]['local_time'] == '16:30'
    next_monday = monday
    while True:
        next_monday = plus_days(next_monday, 7)
        if next_monday.isoformat() >= effective_on:
            break
    calendar = assert_status(
        client.get(
            f'/api/families/{family_id}/calendar',
            params={
                'start': next_monday.isoformat(),
                'end': next_monday.isoformat(),
            },
        ),
        200,
    )
    times = [item['local_time'] for item in calendar['days'][0]['items']]
    assert times == ['17:00']


def test_second_package_and_no_overdraft(client) -> None:
    register(client, 'mama')
    family_id = family_of(client)
    today = today_shanghai()
    course = add_course(client, family_id, [slot(today.weekday(), '16:30')])
    first = add_package(client, course['id'], 1, title='第一期')
    assert_status(client.post(f'/api/courses/{course["id"]}/quick-check-in'), 201)
    second = add_package(client, course['id'], 5, title='第二期')
    detail = assert_status(client.get(f'/api/courses/{course["id"]}'), 200)
    current = [row for row in detail['packages'] if row['is_current']]
    assert current[0]['id'] == first['id']
    blocked = client.post(
        '/api/lessons',
        json={
            'course_id': course['id'],
            'local_date': today.isoformat(),
            'local_time': '09:30',
            'source': 'manual',
            'status': 'attended',
        },
    )
    assert blocked.status_code == 409
    assert blocked.json()['detail']['code'] == 'insufficient'
    assert_status(
        client.post(f'/api/packages/{second["id"]}/make-current'),
        200,
    )
    made = assert_status(
        client.post(
            '/api/lessons',
            json={
                'course_id': course['id'],
                'local_date': today.isoformat(),
                'local_time': '09:30',
                'source': 'manual',
                'status': 'attended',
            },
        ),
        201,
    )
    assert made['package']['remaining_units'] == 4
    detail = assert_status(client.get(f'/api/courses/{course["id"]}'), 200)
    first_row = [row for row in detail['packages'] if row['id'] == first['id']][0]
    assert first_row['remaining_units'] == 0
    assert any(
        row['package_id'] == first['id'] and row['voided_at'] is None
        for row in detail['lessons']
    )


def test_two_slots_today_do_not_auto_pick(client, app) -> None:
    register(client, 'mama')
    family_id = family_of(client)
    today = today_shanghai()
    course = add_course(
        client,
        family_id,
        [
            slot(today.weekday(), '16:30'),
            slot(today.weekday(), '19:00'),
        ],
    )
    add_package(client, course['id'], 4)
    response = client.post(f'/api/courses/{course["id"]}/quick-check-in')
    assert response.status_code == 409
    assert response.json()['detail']['code'] == 'multiple_today'
    assert lesson_count(app) == 0


def test_member_permissions_and_isolation(app) -> None:
    with TestClient(app) as owner, TestClient(app) as member, TestClient(app) as other:
        register(owner, 'mama', '妈妈')
        family_id = family_of(owner)
        today = today_shanghai()
        course = add_course(owner, family_id, [slot(today.weekday(), '16:30')])
        add_package(owner, course['id'], 6)
        invite = assert_status(
            owner.post(f'/api/families/{family_id}/invitations'),
            201,
        )
        register(member, 'baba', '爸爸')
        assert_status(
            member.post(
                '/api/invitations/accept',
                json={'code': invite['code'].lower()},
            ),
            200,
        )
        forbidden = member.post(
            f'/api/families/{family_id}/courses',
            json={'name': '偷偷加的课', 'schedules': []},
        )
        assert forbidden.status_code == 403
        checked = assert_status(
            member.post(f'/api/courses/{course["id"]}/quick-check-in'),
            201,
        )
        home = assert_status(owner.get(f'/api/families/{family_id}/home'), 200)
        assert home['courses'][0]['package']['used_units'] == 1
        assert home['recent'][0]['actor_name'] == '爸爸'
        register(other, 'stranger', '外人')
        other_family = family_of(other, '别人的家')
        hidden = other.get(f'/api/families/{family_id}/home')
        assert hidden.status_code == 404
        hidden_course = other.get(f'/api/courses/{course["id"]}')
        assert hidden_course.status_code == 404
        assert other.get(f'/api/families/{other_family}/home').status_code == 200
        assert checked['package']['remaining_units'] == 5


def test_export_requires_login_and_backup_restores(client, app, tmp_path) -> None:
    register(client, 'mama')
    family_id = family_of(client)
    exported = client.get(f'/api/families/{family_id}/export')
    assert exported.status_code == 200
    assert '悠悠的家' in exported.text
    dest = tmp_path / 'backup.db'
    backup_database(app.state.database_path, str(dest))
    connection = sqlite3.connect(dest)
    try:
        count = connection.execute('SELECT COUNT(*) FROM families').fetchone()[0]
    finally:
        connection.close()
    assert count == 1
    assert_status(client.post('/api/auth/logout'), 204)
    assert client.get(f'/api/families/{family_id}/export').status_code == 401


def test_quick_today_multiple_guard_uses_package(client) -> None:
    register(client, 'mama')
    family_id = family_of(client)
    today = today_shanghai()
    course = add_course(client, family_id, [slot(today.weekday(), '16:30')])
    missing = client.post(f'/api/courses/{course["id"]}/quick-check-in')
    assert missing.status_code == 409
    assert missing.json()['detail']['code'] == 'no_package'
