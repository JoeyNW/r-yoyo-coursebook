"""Check-in, calendar expansion, and home figures."""

from datetime import date, timedelta
from uuid import uuid4

from sqlalchemy.engine import Connection, Engine
from sqlalchemy.exc import IntegrityError

from app.db import many, one, run, transaction, write_audit
from app.errors import AppError
from app.services.authz import membership, require_course, require_member
from app.services.catalog import package_consumed, public_package
from app.services.rules import (
    planned_key,
    schedule_covers,
    units_for,
)
from app.timeutil import iso_utc, today_shanghai


def _public_lesson(conn: Connection, row) -> dict:
    actor = one(
        conn,
        'SELECT display_name FROM users WHERE id = :id',
        {'id': row['created_by']},
    )
    return {
        'id': row['id'],
        'course_id': row['course_id'],
        'package_id': row['package_id'],
        'local_date': row['local_date'],
        'local_time': row['local_time'],
        'source': row['source'],
        'status': row['status'],
        'consumed_units': int(row['consumed_units']),
        'notes': row['notes'],
        'voided_at': row['voided_at'],
        'actor_name': actor['display_name'],
    }


def _active_by_key(conn: Connection, key: str):
    return one(
        conn,
        '''
        SELECT * FROM lesson_records
        WHERE idempotency_key = :key AND voided_at IS NULL
        ''',
        {'key': key},
    )


def _result(conn: Connection, row, created: bool) -> dict:
    package = one(
        conn,
        'SELECT * FROM course_packages WHERE id = :id',
        {'id': row['package_id']},
    )
    return {
        'created': created,
        'lesson': _public_lesson(conn, row),
        'package': public_package(conn, dict(package), package['id']),
    }


def _slot_exists(conn: Connection, course_id: int, day: date, local_time: str) -> bool:
    rows = many(
        conn,
        '''
        SELECT weekday, local_time, effective_from, effective_to
        FROM course_schedules
        WHERE course_id = :course_id
        ''',
        {'course_id': course_id},
    )
    for row in rows:
        if row['local_time'] != local_time:
            continue
        if schedule_covers(
            int(row['weekday']),
            row['effective_from'],
            row['effective_to'],
            day,
        ):
            return True
    return False


def _status_label(status: str, source: str) -> str:
    if source == 'manual' and status == 'attended':
        return '补课'
    return {
        'attended': '已上课',
        'leave': '请假',
        'canceled': '取消',
    }[status]


def _apply_check_in(
    conn: Connection,
    user_id: int,
    course: dict,
    local_date: str,
    local_time: str,
    source: str,
    status: str,
    charge: bool,
    notes: str,
    key: str,
) -> dict:
    today = today_shanghai()
    day = date.fromisoformat(local_date)
    units = units_for(status, charge)
    if status == 'attended' and day > today:
        raise AppError('future', '还没上的课不能提前打卡', 400)
    if source == 'planned' and not _slot_exists(
        conn, int(course['id']), day, local_time
    ):
        raise AppError('no_such_slot', '这天的课表里没有这一节课', 400)
    existing = _active_by_key(conn, key)
    if existing is not None:
        same = (
            existing['status'] == status
            and int(existing['consumed_units']) == units
        )
        if same:
            return _result(conn, existing, False)
        raise AppError('exists', '这节课已有记录，请修改或撤销后再操作', 409)
    if course['current_package_id'] is None:
        raise AppError('no_package', '请先添加课包', 409)
    package = one(
        conn,
        '''
        SELECT * FROM course_packages
        WHERE id = :id AND course_id = :course_id
        ''',
        {'id': course['current_package_id'], 'course_id': course['id']},
    )
    if package is None:
        raise AppError('no_package', '请先添加课包', 409)
    consumed = package_consumed(conn, int(package['id']))
    remaining = (
        int(package['total_units'])
        - int(package['opening_consumed_units'])
        - consumed
    )
    if units > remaining:
        raise AppError('insufficient', '当前课包剩余课时不足', 409)
    moment = iso_utc()
    result = run(
        conn,
        '''
        INSERT INTO lesson_records (
            family_id, course_id, package_id, local_date, local_time,
            source, status, consumed_units, idempotency_key, notes,
            created_by, updated_by, created_at, updated_at
        ) VALUES (
            :family_id, :course_id, :package_id, :local_date, :local_time,
            :source, :status, :consumed_units, :idempotency_key, :notes,
            :created_by, :updated_by, :created_at, :updated_at
        )
        ''',
        {
            'family_id': course['family_id'],
            'course_id': course['id'],
            'package_id': package['id'],
            'local_date': local_date,
            'local_time': local_time,
            'source': source,
            'status': status,
            'consumed_units': units,
            'idempotency_key': key,
            'notes': notes.strip(),
            'created_by': user_id,
            'updated_by': user_id,
            'created_at': moment,
            'updated_at': moment,
        },
    )
    lesson_id = int(result.lastrowid)
    label = _status_label(status, source)
    charge_text = f'，扣 {units} 课时' if units else '，不扣课时'
    write_audit(
        conn,
        user_id,
        int(course['family_id']),
        'lesson',
        lesson_id,
        'check_in',
        f'「{course["name"]}」{local_date} {local_time} {label}{charge_text}',
        moment,
    )
    stored = one(
        conn,
        'SELECT * FROM lesson_records WHERE id = :id',
        {'id': lesson_id},
    )
    return _result(conn, stored, True)


def check_in(
    engine: Engine,
    user_id: int,
    course_id: int,
    local_date: str,
    local_time: str,
    source: str,
    status: str,
    charge: bool,
    notes: str,
) -> dict:
    """Insert one attendance fact, or return the active row for that slot."""
    if source == 'manual':
        key = f'manual:{uuid4()}'
    else:
        key = planned_key(course_id, local_date, local_time)
    try:
        with transaction(engine) as conn:
            course = require_course(conn, user_id, course_id, owner=False)
            return _apply_check_in(
                conn,
                user_id,
                course,
                local_date,
                local_time,
                source,
                status,
                charge,
                notes,
                key,
            )
    except IntegrityError:
        with transaction(engine) as conn:
            existing = _active_by_key(conn, key)
            if existing is None:
                raise
            require_course(conn, user_id, course_id, owner=False)
            return _result(conn, existing, False)


def _planned_times(conn: Connection, course_id: int, day: date) -> list[str]:
    rows = many(
        conn,
        '''
        SELECT weekday, local_time, effective_from, effective_to
        FROM course_schedules
        WHERE course_id = :course_id
        ''',
        {'course_id': course_id},
    )
    times = []
    for row in rows:
        if schedule_covers(
            int(row['weekday']),
            row['effective_from'],
            row['effective_to'],
            day,
        ):
            times.append(row['local_time'])
    return sorted(set(times))


def _open_times(conn: Connection, course_id: int, day: date) -> list[str]:
    return [
        local_time
        for local_time in _planned_times(conn, course_id, day)
        if _active_by_key(
            conn,
            planned_key(course_id, day.isoformat(), local_time),
        )
        is None
    ]


def quick_check_in(engine: Engine, user_id: int, course_id: int) -> dict:
    """Check in today's only open slot. Never touches another date."""
    today = today_shanghai()
    try:
        with transaction(engine) as conn:
            course = require_course(conn, user_id, course_id, owner=False)
            if course['current_package_id'] is None:
                raise AppError('no_package', '请先添加课包', 409)
            planned = _planned_times(conn, course_id, today)
            times = _open_times(conn, course_id, today)
            if len(times) > 1:
                raise AppError(
                    'multiple_today',
                    '今天有多节课，请到日历里选择',
                    409,
                    extra={
                        'slots': [
                            {
                                'local_date': today.isoformat(),
                                'local_time': item,
                            }
                            for item in times
                        ]
                    },
                )
            if len(times) == 1:
                local_time = times[0]
            elif len(planned) == 1:
                local_time = planned[0]
            else:
                raise AppError('none_today', '今天没有待打卡的课', 409)
            key = planned_key(course_id, today.isoformat(), local_time)
            return _apply_check_in(
                conn,
                user_id,
                course,
                today.isoformat(),
                local_time,
                'planned',
                'attended',
                False,
                '',
                key,
            )
    except IntegrityError:
        with transaction(engine) as conn:
            planned = _planned_times(conn, course_id, today)
            if len(planned) != 1:
                raise
            key = planned_key(course_id, today.isoformat(), planned[0])
            existing = _active_by_key(conn, key)
            if existing is None:
                raise
            require_course(conn, user_id, course_id, owner=False)
            return _result(conn, existing, False)


def void_lesson(engine: Engine, user_id: int, lesson_id: int, confirm: bool) -> dict:
    """Mark a lesson void. The row stays so the audit trail remains."""
    if not confirm:
        raise AppError('confirm', '请确认后再撤销', 400)
    moment = iso_utc()
    with transaction(engine) as conn:
        lesson = one(
            conn,
            'SELECT * FROM lesson_records WHERE id = :id',
            {'id': lesson_id},
        )
        if lesson is None or membership(
            conn, user_id, int(lesson['family_id'])
        ) is None:
            raise AppError('not_found', '找不到内容', 404)
        if lesson['voided_at'] is not None:
            return _result(conn, lesson, False)
        run(
            conn,
            '''
            UPDATE lesson_records
            SET voided_at = :voided_at,
                voided_by = :voided_by,
                updated_by = :updated_by,
                updated_at = :updated_at
            WHERE id = :id
            ''',
            {
                'id': lesson_id,
                'voided_at': moment,
                'voided_by': user_id,
                'updated_by': user_id,
                'updated_at': moment,
            },
        )
        course = one(
            conn,
            'SELECT name FROM courses WHERE id = :id',
            {'id': lesson['course_id']},
        )
        write_audit(
            conn,
            user_id,
            int(lesson['family_id']),
            'lesson',
            lesson_id,
            'void_lesson',
            (
                f'撤销「{course["name"]}」{lesson["local_date"]} '
                f'{lesson["local_time"]}，恢复 {int(lesson["consumed_units"])} 课时'
            ),
            moment,
        )
        stored = one(
            conn,
            'SELECT * FROM lesson_records WHERE id = :id',
            {'id': lesson_id},
        )
        return _result(conn, stored, False)


def update_lesson(
    engine: Engine,
    user_id: int,
    lesson_id: int,
    status: str,
    charge: bool,
    notes: str | None,
    confirm: bool,
) -> dict:
    """Change the status of an active lesson inside one transaction."""
    if not confirm:
        raise AppError('confirm', '请确认后再修改', 400)
    moment = iso_utc()
    today = today_shanghai()
    units = units_for(status, charge)
    with transaction(engine) as conn:
        lesson = one(
            conn,
            'SELECT * FROM lesson_records WHERE id = :id',
            {'id': lesson_id},
        )
        if lesson is None or membership(
            conn, user_id, int(lesson['family_id'])
        ) is None:
            raise AppError('not_found', '找不到内容', 404)
        if lesson['voided_at'] is not None:
            raise AppError('void', '已撤销的记录不能修改', 400)
        day = date.fromisoformat(lesson['local_date'])
        if status == 'attended' and day > today:
            raise AppError('future', '还没上的课不能提前打卡', 400)
        package = one(
            conn,
            'SELECT * FROM course_packages WHERE id = :id',
            {'id': lesson['package_id']},
        )
        others = one(
            conn,
            '''
            SELECT COALESCE(SUM(consumed_units), 0) AS n
            FROM lesson_records
            WHERE package_id = :package_id
              AND voided_at IS NULL
              AND id != :lesson_id
            ''',
            {'package_id': package['id'], 'lesson_id': lesson_id},
        )
        room = (
            int(package['total_units'])
            - int(package['opening_consumed_units'])
            - int(others['n'])
        )
        if units > room:
            raise AppError('insufficient', '当前课包剩余课时不足', 409)
        note_value = lesson['notes'] if notes is None else notes.strip()
        run(
            conn,
            '''
            UPDATE lesson_records
            SET status = :status,
                consumed_units = :consumed_units,
                notes = :notes,
                updated_by = :updated_by,
                updated_at = :updated_at
            WHERE id = :id
            ''',
            {
                'id': lesson_id,
                'status': status,
                'consumed_units': units,
                'notes': note_value,
                'updated_by': user_id,
                'updated_at': moment,
            },
        )
        course = one(
            conn,
            'SELECT name FROM courses WHERE id = :id',
            {'id': lesson['course_id']},
        )
        write_audit(
            conn,
            user_id,
            int(lesson['family_id']),
            'lesson',
            lesson_id,
            'update_lesson',
            (
                f'修改「{course["name"]}」{lesson["local_date"]} '
                f'{lesson["local_time"]}，扣 {units} 课时'
            ),
            moment,
        )
        stored = one(
            conn,
            'SELECT * FROM lesson_records WHERE id = :id',
            {'id': lesson_id},
        )
        return _result(conn, stored, False)


def _virtual_times(schedules, day: date) -> list[str]:
    times = []
    for row in schedules:
        if schedule_covers(
            int(row['weekday']),
            row['effective_from'],
            row['effective_to'],
            day,
        ):
            times.append(row['local_time'])
    return sorted(set(times))


def home(engine: Engine, user_id: int, family_id: int) -> dict:
    """Return course cards. Balances are computed, never stored."""
    today = today_shanghai()
    prefix = today.strftime('%Y-%m') + '%'
    with transaction(engine) as conn:
        role = require_member(conn, user_id, family_id)
        family = one(
            conn,
            'SELECT id, name FROM families WHERE id = :id',
            {'id': family_id},
        )
        courses = many(
            conn,
            '''
            SELECT * FROM courses
            WHERE family_id = :family_id AND active = 1
            ORDER BY id
            ''',
            {'family_id': family_id},
        )
        attended = one(
            conn,
            '''
            SELECT COUNT(*) AS n
            FROM lesson_records
            WHERE family_id = :family_id
              AND status = 'attended'
              AND voided_at IS NULL
              AND local_date LIKE :prefix
            ''',
            {'family_id': family_id, 'prefix': prefix},
        )
        recent = many(
            conn,
            '''
            SELECT a.id, a.action, a.summary, a.created_at,
                   u.display_name AS actor_name
            FROM audit_logs a
            JOIN users u ON u.id = a.actor_user_id
            WHERE a.family_id = :family_id
            ORDER BY a.id DESC
            LIMIT 8
            ''',
            {'family_id': family_id},
        )
        cards = []
        for course in courses:
            schedules = many(
                conn,
                '''
                SELECT weekday, local_time, effective_from, effective_to
                FROM course_schedules
                WHERE course_id = :course_id
                ''',
                {'course_id': course['id']},
            )
            recorded = many(
                conn,
                '''
                SELECT local_date, local_time
                FROM lesson_records
                WHERE course_id = :course_id AND voided_at IS NULL
                  AND source = 'planned'
                ''',
                {'course_id': course['id']},
            )
            taken = {
                (row['local_date'], row['local_time']) for row in recorded
            }
            next_lesson = None
            for offset in range(21):
                day = today + timedelta(days=offset)
                for local_time in _virtual_times(schedules, day):
                    if (day.isoformat(), local_time) in taken:
                        continue
                    next_lesson = {
                        'local_date': day.isoformat(),
                        'local_time': local_time,
                    }
                    break
                if next_lesson is not None:
                    break
            today_open = [
                local_time
                for local_time in _virtual_times(schedules, today)
                if (today.isoformat(), local_time) not in taken
            ]
            package_body = None
            if course['current_package_id'] is not None:
                package = one(
                    conn,
                    'SELECT * FROM course_packages WHERE id = :id',
                    {'id': course['current_package_id']},
                )
                if package is not None:
                    full = public_package(
                        conn, dict(package), package['id']
                    )
                    package_body = {
                        'id': full['id'],
                        'title': full['title'],
                        'total_units': full['total_units'],
                        'used_units': full['used_units'],
                        'remaining_units': full['remaining_units'],
                        'low_balance': full['low_balance'],
                    }
            cards.append(
                {
                    'id': course['id'],
                    'name': course['name'],
                    'color': course['color'],
                    'active': True,
                    'package': package_body,
                    'next_lesson': next_lesson,
                    'today_open_count': len(today_open),
                }
            )
    return {
        'family': {
            'id': family['id'],
            'name': family['name'],
            'role': role,
        },
        'today': today.isoformat(),
        'attended_this_month': int(attended['n']),
        'courses': cards,
        'recent': [dict(row) for row in recent],
    }


def calendar_view(
    engine: Engine,
    user_id: int,
    family_id: int,
    start: str,
    end: str,
) -> dict:
    """Expand schedules and overlay stored facts. Plans are not inserted."""
    try:
        start_day = date.fromisoformat(start)
        end_day = date.fromisoformat(end)
    except ValueError as exc:
        raise AppError('bad_date', '日期格式应为 YYYY-MM-DD', 400) from exc
    if end_day < start_day or (end_day - start_day).days > 41:
        raise AppError('range', '一次最多查看 42 天', 400)
    with transaction(engine) as conn:
        require_member(conn, user_id, family_id)
        courses = many(
            conn,
            'SELECT * FROM courses WHERE family_id = :family_id',
            {'family_id': family_id},
        )
        course_map = {int(row['id']): row for row in courses}
        schedules = many(
            conn,
            '''
            SELECT s.*
            FROM course_schedules s
            JOIN courses c ON c.id = s.course_id
            WHERE c.family_id = :family_id
            ''',
            {'family_id': family_id},
        )
        records = many(
            conn,
            '''
            SELECT * FROM lesson_records
            WHERE family_id = :family_id
              AND voided_at IS NULL
              AND local_date >= :start
              AND local_date <= :end
            ''',
            {'family_id': family_id, 'start': start, 'end': end},
        )
    by_slot = {
        (int(row['course_id']), row['local_date'], row['local_time']): row
        for row in records
        if row['source'] == 'planned'
    }
    days: dict[str, list[dict]] = {}
    seen: set[tuple[int, str, str]] = set()
    cursor = start_day
    while cursor <= end_day:
        iso = cursor.isoformat()
        for schedule in schedules:
            course = course_map[int(schedule['course_id'])]
            if not course['active']:
                continue
            if not schedule_covers(
                int(schedule['weekday']),
                schedule['effective_from'],
                schedule['effective_to'],
                cursor,
            ):
                continue
            key = (int(course['id']), iso, schedule['local_time'])
            seen.add(key)
            record = by_slot.get(key)
            days.setdefault(iso, []).append(_calendar_item(course, schedule['local_time'], record))
        cursor += timedelta(days=1)
    for record in records:
        key = (
            int(record['course_id']),
            record['local_date'],
            record['local_time'],
        )
        if record['source'] == 'planned' and key in seen:
            continue
        course = course_map.get(int(record['course_id']))
        if course is None:
            continue
        days.setdefault(record['local_date'], []).append(
            _calendar_item(course, record['local_time'], record)
        )
    payload = []
    for iso in sorted(days):
        items = days[iso]
        items.sort(key=lambda item: (item['local_time'], item['course_name']))
        payload.append({'date': iso, 'items': items})
    return {'days': payload}


def _calendar_item(course, local_time: str, record) -> dict:
    if record is None:
        return {
            'course_id': course['id'],
            'course_name': course['name'],
            'color': course['color'],
            'local_time': local_time,
            'state': 'scheduled',
            'lesson_id': None,
            'source': None,
            'consumed_units': 0,
            'notes': '',
        }
    return {
        'course_id': course['id'],
        'course_name': course['name'],
        'color': course['color'],
        'local_time': local_time,
        'state': record['status'],
        'lesson_id': record['id'],
        'source': record['source'],
        'consumed_units': int(record['consumed_units']),
        'notes': record['notes'],
    }


def export_family(engine: Engine, user_id: int, family_id: int) -> dict:
    """Return a JSON snapshot of one family's ledger."""
    with transaction(engine) as conn:
        require_member(conn, user_id, family_id)
        family = one(
            conn,
            'SELECT id, name, created_at FROM families WHERE id = :id',
            {'id': family_id},
        )
        members = many(
            conn,
            '''
            SELECT u.display_name, m.role, m.joined_at
            FROM family_members m
            JOIN users u ON u.id = m.user_id
            WHERE m.family_id = :family_id
            ORDER BY m.joined_at
            ''',
            {'family_id': family_id},
        )
        courses = many(
            conn,
            'SELECT * FROM courses WHERE family_id = :family_id ORDER BY id',
            {'family_id': family_id},
        )
        exported = []
        for course in courses:
            schedules = many(
                conn,
                '''
                SELECT weekday, local_time, effective_from, effective_to
                FROM course_schedules
                WHERE course_id = :course_id
                ORDER BY id
                ''',
                {'course_id': course['id']},
            )
            packages = many(
                conn,
                '''
                SELECT id, title, total_units, opening_consumed_units,
                       start_date, expiry_date, notes, created_at
                FROM course_packages
                WHERE course_id = :course_id
                ORDER BY id
                ''',
                {'course_id': course['id']},
            )
            lessons = many(
                conn,
                '''
                SELECT local_date, local_time, source, status,
                       consumed_units, notes, voided_at, package_id, created_at
                FROM lesson_records
                WHERE course_id = :course_id
                ORDER BY id
                ''',
                {'course_id': course['id']},
            )
            exported.append(
                {
                    'name': course['name'],
                    'color': course['color'],
                    'teacher': course['teacher'],
                    'location': course['location'],
                    'notes': course['notes'],
                    'active': bool(course['active']),
                    'current_package_id': course['current_package_id'],
                    'schedules': [dict(row) for row in schedules],
                    'packages': [dict(row) for row in packages],
                    'lessons': [dict(row) for row in lessons],
                }
            )
    return {
        'exported_at': iso_utc(),
        'family': dict(family),
        'members': [dict(row) for row in members],
        'courses': exported,
    }
