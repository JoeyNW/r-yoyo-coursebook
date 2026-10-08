"""Courses, weekly slots, and packages."""

import re

from sqlalchemy.engine import Connection, Engine

from app.db import many, one, run, transaction, write_audit
from app.errors import AppError
from app.services.authz import require_course, require_member, require_owner
from app.services.rules import balance_parts, is_low, ranges_overlap
from app.timeutil import iso_utc, month_start, today_shanghai

_COLOR = re.compile(r'^#[0-9a-fA-F]{6}$')
_PALETTE = (
    '#0f766e',
    '#b45309',
    '#1d4ed8',
    '#be123c',
    '#6d28d9',
    '#3f6212',
)


def _clean_color(value: str | None, fallback: str) -> str:
    if value is None or value == '':
        return fallback
    if not _COLOR.fullmatch(value):
        raise AppError('invalid', '颜色格式应为 #RRGGBB', 400)
    return value.lower()


def _assert_slot_free(
    conn: Connection,
    course_id: int,
    weekday: int,
    local_time: str,
    effective_from: str,
    effective_to: str | None,
    exclude_id: int | None = None,
) -> None:
    rows = many(
        conn,
        '''
        SELECT id, effective_from, effective_to
        FROM course_schedules
        WHERE course_id = :course_id
          AND weekday = :weekday
          AND local_time = :local_time
        ''',
        {
            'course_id': course_id,
            'weekday': weekday,
            'local_time': local_time,
        },
    )
    for row in rows:
        if exclude_id is not None and int(row['id']) == exclude_id:
            continue
        if ranges_overlap(
            effective_from,
            effective_to,
            row['effective_from'],
            row['effective_to'],
        ):
            raise AppError('duplicate_slot', '这个上课时间已经有了', 400)


def _insert_schedule(
    conn: Connection,
    course_id: int,
    weekday: int,
    local_time: str,
    effective_from: str,
    created_at: str,
) -> int:
    _assert_slot_free(
        conn,
        course_id,
        weekday,
        local_time,
        effective_from,
        None,
    )
    result = run(
        conn,
        '''
        INSERT INTO course_schedules (
            course_id, weekday, local_time, effective_from, created_at
        ) VALUES (
            :course_id, :weekday, :local_time, :effective_from, :created_at
        )
        ''',
        {
            'course_id': course_id,
            'weekday': weekday,
            'local_time': local_time,
            'effective_from': effective_from,
            'created_at': created_at,
        },
    )
    return int(result.lastrowid)


def package_consumed(conn: Connection, package_id: int) -> int:
    """Return active consumed units on one package."""
    row = one(
        conn,
        '''
        SELECT COALESCE(SUM(consumed_units), 0) AS n
        FROM lesson_records
        WHERE package_id = :package_id AND voided_at IS NULL
        ''',
        {'package_id': package_id},
    )
    return int(row['n'])


def public_package(conn: Connection, package: dict, current_id: int | None) -> dict:
    """Return package figures computed from the ledger."""
    consumed = package_consumed(conn, int(package['id']))
    parts = balance_parts(
        int(package['total_units']),
        int(package['opening_consumed_units']),
        consumed,
    )
    return {
        'id': package['id'],
        'title': package['title'],
        'total_units': parts['total_units'],
        'opening_consumed_units': int(package['opening_consumed_units']),
        'used_units': parts['used_units'],
        'remaining_units': parts['remaining_units'],
        'low_balance': is_low(parts['remaining_units']),
        'start_date': package['start_date'],
        'expiry_date': package['expiry_date'],
        'notes': package['notes'],
        'is_current': current_id is not None and package['id'] == current_id,
    }


def course_detail(engine: Engine, user_id: int, course_id: int) -> dict:
    """Return one course, its slots, packages, and recent lessons."""
    today = today_shanghai().isoformat()
    with transaction(engine) as conn:
        course = require_course(conn, user_id, course_id, owner=False)
        schedules = many(
            conn,
            '''
            SELECT id, weekday, local_time, effective_from, effective_to
            FROM course_schedules
            WHERE course_id = :course_id
            ORDER BY weekday, local_time, id
            ''',
            {'course_id': course_id},
        )
        packages = many(
            conn,
            '''
            SELECT * FROM course_packages
            WHERE course_id = :course_id
            ORDER BY id
            ''',
            {'course_id': course_id},
        )
        lessons = many(
            conn,
            '''
            SELECT l.*, u.display_name AS actor_name
            FROM lesson_records l
            JOIN users u ON u.id = l.created_by
            WHERE l.course_id = :course_id
            ORDER BY l.local_date DESC, l.local_time DESC, l.id DESC
            LIMIT 50
            ''',
            {'course_id': course_id},
        )
        current_id = course['current_package_id']
        return {
            'id': course['id'],
            'family_id': course['family_id'],
            'name': course['name'],
            'color': course['color'],
            'teacher': course['teacher'],
            'location': course['location'],
            'notes': course['notes'],
            'active': bool(course['active']),
            'role': course['role'],
            'schedules': [
                {
                    'id': row['id'],
                    'weekday': row['weekday'],
                    'local_time': row['local_time'],
                    'effective_from': row['effective_from'],
                    'effective_to': row['effective_to'],
                    'active_now': (
                        row['effective_to'] is None
                        or row['effective_to'] >= today
                    ),
                }
                for row in schedules
            ],
            'packages': [
                public_package(conn, dict(row), current_id) for row in packages
            ],
            'lessons': [
                {
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
                    'actor_name': row['actor_name'],
                }
                for row in lessons
            ],
        }


def list_courses(engine: Engine, user_id: int, family_id: int) -> dict:
    """List courses in a family, including inactive ones."""
    with transaction(engine) as conn:
        require_member(conn, user_id, family_id)
        rows = many(
            conn,
            '''
            SELECT id, name, color, active
            FROM courses
            WHERE family_id = :family_id
            ORDER BY active DESC, id
            ''',
            {'family_id': family_id},
        )
    return {
        'courses': [
            {
                'id': row['id'],
                'name': row['name'],
                'color': row['color'],
                'active': bool(row['active']),
            }
            for row in rows
        ]
    }


def create_course(
    engine: Engine,
    user_id: int,
    family_id: int,
    name: str,
    color: str | None,
    teacher: str,
    location: str,
    notes: str,
    schedules: list[dict],
) -> dict:
    """Create a course and its initial weekly slots."""
    moment = iso_utc()
    default_from = month_start().isoformat()
    seen: set[tuple[int, str]] = set()
    for item in schedules:
        key = (int(item['weekday']), item['local_time'])
        if key in seen:
            raise AppError('duplicate_slot', '同一时间的上课时段重复了', 400)
        seen.add(key)
    with transaction(engine) as conn:
        require_owner(conn, user_id, family_id)
        count = one(
            conn,
            'SELECT COUNT(*) AS n FROM courses WHERE family_id = :id',
            {'id': family_id},
        )
        chosen = _clean_color(color, _PALETTE[int(count['n']) % len(_PALETTE)])
        result = run(
            conn,
            '''
            INSERT INTO courses (
                family_id, name, color, teacher, location, notes,
                active, created_at
            ) VALUES (
                :family_id, :name, :color, :teacher, :location, :notes,
                1, :created_at
            )
            ''',
            {
                'family_id': family_id,
                'name': name,
                'color': chosen,
                'teacher': teacher.strip(),
                'location': location.strip(),
                'notes': notes.strip(),
                'created_at': moment,
            },
        )
        course_id = int(result.lastrowid)
        for item in schedules:
            effective = item.get('effective_from') or default_from
            _insert_schedule(
                conn,
                course_id,
                int(item['weekday']),
                item['local_time'],
                effective,
                moment,
            )
        write_audit(
            conn,
            user_id,
            family_id,
            'course',
            course_id,
            'create_course',
            f'新增课程「{name}」',
            moment,
        )
    return {'id': course_id, 'name': name, 'color': chosen}


def update_course(
    engine: Engine,
    user_id: int,
    course_id: int,
    fields: dict,
) -> dict:
    """Update course profile fields supplied by the owner."""
    allowed = ('name', 'color', 'teacher', 'location', 'notes', 'active')
    moment = iso_utc()
    with transaction(engine) as conn:
        course = require_course(conn, user_id, course_id, owner=True)
        updates = dict(course)
        if 'color' in fields and fields['color'] is not None:
            updates['color'] = _clean_color(fields['color'], course['color'])
        for key in allowed:
            if key == 'color' or key not in fields or fields[key] is None:
                continue
            if key == 'active':
                updates['active'] = 1 if fields['active'] else 0
            else:
                updates[key] = str(fields[key]).strip()
        run(
            conn,
            '''
            UPDATE courses
            SET name = :name, color = :color, teacher = :teacher,
                location = :location, notes = :notes, active = :active
            WHERE id = :id
            ''',
            {
                'id': course_id,
                'name': updates['name'],
                'color': updates['color'],
                'teacher': updates['teacher'],
                'location': updates['location'],
                'notes': updates['notes'],
                'active': updates['active'],
            },
        )
        state = '启用' if updates['active'] else '停用'
        write_audit(
            conn,
            user_id,
            int(course['family_id']),
            'course',
            course_id,
            'update_course',
            f'修改课程「{updates["name"]}」，状态{state}',
            moment,
        )
    return course_detail(engine, user_id, course_id)


def add_schedule(
    engine: Engine,
    user_id: int,
    course_id: int,
    weekday: int,
    local_time: str,
    effective_from: str | None,
) -> dict:
    """Add one weekly slot."""
    moment = iso_utc()
    start = effective_from or month_start().isoformat()
    with transaction(engine) as conn:
        course = require_course(conn, user_id, course_id, owner=True)
        schedule_id = _insert_schedule(
            conn,
            course_id,
            weekday,
            local_time,
            start,
            moment,
        )
        write_audit(
            conn,
            user_id,
            int(course['family_id']),
            'schedule',
            schedule_id,
            'add_schedule',
            f'「{course["name"]}」增加上课时间',
            moment,
        )
    return course_detail(engine, user_id, course_id)


def replace_schedule(
    engine: Engine,
    user_id: int,
    schedule_id: int,
    weekday: int,
    local_time: str,
    effective_on: str,
) -> dict:
    """End a slot the day before effective_on and insert the new time.

    Existing lesson rows keep the date and time they were written with.
    """
    moment = iso_utc()
    with transaction(engine) as conn:
        current = one(
            conn,
            '''
            SELECT s.*, c.family_id, c.name AS course_name
            FROM course_schedules s
            JOIN courses c ON c.id = s.course_id
            WHERE s.id = :id
            ''',
            {'id': schedule_id},
        )
        if current is None:
            raise AppError('not_found', '找不到内容', 404)
        require_owner(conn, user_id, int(current['family_id']))
        new_end = _day_before(effective_on)
        if current['effective_to'] is not None and current['effective_to'] < new_end:
            new_end = current['effective_to']
        run(
            conn,
            '''
            UPDATE course_schedules
            SET effective_to = :effective_to
            WHERE id = :id
            ''',
            {'effective_to': new_end, 'id': schedule_id},
        )
        new_id = _insert_schedule(
            conn,
            int(current['course_id']),
            weekday,
            local_time,
            effective_on,
            moment,
        )
        write_audit(
            conn,
            user_id,
            int(current['family_id']),
            'schedule',
            new_id,
            'replace_schedule',
            (
                f'「{current["course_name"]}」从 {effective_on} 起'
                f'改为周时段 {local_time}'
            ),
            moment,
        )
        course_id = int(current['course_id'])
    return course_detail(engine, user_id, course_id)


def end_schedule(
    engine: Engine,
    user_id: int,
    schedule_id: int,
    last_date: str,
) -> dict:
    """Stop generating a slot after last_date."""
    moment = iso_utc()
    with transaction(engine) as conn:
        current = one(
            conn,
            '''
            SELECT s.*, c.family_id, c.name AS course_name
            FROM course_schedules s
            JOIN courses c ON c.id = s.course_id
            WHERE s.id = :id
            ''',
            {'id': schedule_id},
        )
        if current is None:
            raise AppError('not_found', '找不到内容', 404)
        require_owner(conn, user_id, int(current['family_id']))
        effective_to = last_date
        if (
            current['effective_to'] is not None
            and current['effective_to'] < effective_to
        ):
            effective_to = current['effective_to']
        run(
            conn,
            '''
            UPDATE course_schedules
            SET effective_to = :effective_to
            WHERE id = :id
            ''',
            {'effective_to': effective_to, 'id': schedule_id},
        )
        write_audit(
            conn,
            user_id,
            int(current['family_id']),
            'schedule',
            schedule_id,
            'end_schedule',
            f'「{current["course_name"]}」的一个时段上到 {effective_to}',
            moment,
        )
        course_id = int(current['course_id'])
    return course_detail(engine, user_id, course_id)


def _day_before(iso_day: str) -> str:
    from datetime import date, timedelta

    return (date.fromisoformat(iso_day) - timedelta(days=1)).isoformat()


def _ensure_package_fits(total: int, opening: int, consumed: int) -> None:
    if opening > total or opening + consumed > total:
        raise AppError('invalid', '已用课时不能大于总课时', 400)


def create_package(
    engine: Engine,
    user_id: int,
    course_id: int,
    title: str,
    total_units: int,
    opening_consumed_units: int,
    start_date: str | None,
    expiry_date: str | None,
    notes: str,
) -> dict:
    """Add a package. The first one becomes current; later ones do not."""
    moment = iso_utc()
    _ensure_package_fits(total_units, opening_consumed_units, 0)
    with transaction(engine) as conn:
        course = require_course(conn, user_id, course_id, owner=True)
        result = run(
            conn,
            '''
            INSERT INTO course_packages (
                course_id, title, total_units, opening_consumed_units,
                start_date, expiry_date, notes, created_at
            ) VALUES (
                :course_id, :title, :total_units, :opening_consumed_units,
                :start_date, :expiry_date, :notes, :created_at
            )
            ''',
            {
                'course_id': course_id,
                'title': title,
                'total_units': total_units,
                'opening_consumed_units': opening_consumed_units,
                'start_date': start_date,
                'expiry_date': expiry_date,
                'notes': notes.strip(),
                'created_at': moment,
            },
        )
        package_id = int(result.lastrowid)
        if course['current_package_id'] is None:
            run(
                conn,
                '''
                UPDATE courses
                SET current_package_id = :package_id
                WHERE id = :course_id
                ''',
                {'package_id': package_id, 'course_id': course_id},
            )
        write_audit(
            conn,
            user_id,
            int(course['family_id']),
            'package',
            package_id,
            'create_package',
            (
                f'「{course["name"]}」新增课包「{title}」'
                f'共 {total_units} 节，启用前已用 {opening_consumed_units} 节'
            ),
            moment,
        )
    return {'id': package_id}


def update_package(
    engine: Engine,
    user_id: int,
    package_id: int,
    fields: dict,
) -> dict:
    """Change package text or opening use, and write an audit row."""
    moment = iso_utc()
    with transaction(engine) as conn:
        package = one(
            conn,
            'SELECT * FROM course_packages WHERE id = :id',
            {'id': package_id},
        )
        if package is None:
            raise AppError('not_found', '找不到内容', 404)
        course = require_course(
            conn,
            user_id,
            int(package['course_id']),
            owner=True,
        )
        total = int(fields.get('total_units') or package['total_units'])
        opening = package['opening_consumed_units']
        if 'opening_consumed_units' in fields and fields['opening_consumed_units'] is not None:
            opening = int(fields['opening_consumed_units'])
        title = package['title']
        if fields.get('title'):
            title = fields['title']
        notes = package['notes']
        if fields.get('notes') is not None:
            notes = str(fields['notes']).strip()
        start_date = package['start_date']
        expiry_date = package['expiry_date']
        if 'start_date' in fields:
            start_date = fields['start_date']
        if 'expiry_date' in fields:
            expiry_date = fields['expiry_date']
        consumed = package_consumed(conn, package_id)
        _ensure_package_fits(total, int(opening), consumed)
        run(
            conn,
            '''
            UPDATE course_packages
            SET title = :title,
                total_units = :total_units,
                opening_consumed_units = :opening,
                start_date = :start_date,
                expiry_date = :expiry_date,
                notes = :notes
            WHERE id = :id
            ''',
            {
                'id': package_id,
                'title': title,
                'total_units': total,
                'opening': int(opening),
                'start_date': start_date,
                'expiry_date': expiry_date,
                'notes': notes,
            },
        )
        write_audit(
            conn,
            user_id,
            int(course['family_id']),
            'package',
            package_id,
            'update_package',
            (
                f'修改课包「{title}」：总 {total}，'
                f'启用前已用 {int(opening)}'
            ),
            moment,
        )
        course_id = int(package['course_id'])
    return course_detail(engine, user_id, course_id)


def make_current(engine: Engine, user_id: int, package_id: int) -> dict:
    """Point the course at a package without moving old lessons."""
    moment = iso_utc()
    with transaction(engine) as conn:
        package = one(
            conn,
            'SELECT * FROM course_packages WHERE id = :id',
            {'id': package_id},
        )
        if package is None:
            raise AppError('not_found', '找不到内容', 404)
        course = require_course(
            conn,
            user_id,
            int(package['course_id']),
            owner=True,
        )
        run(
            conn,
            '''
            UPDATE courses
            SET current_package_id = :package_id
            WHERE id = :course_id
            ''',
            {'package_id': package_id, 'course_id': package['course_id']},
        )
        write_audit(
            conn,
            user_id,
            int(course['family_id']),
            'package',
            package_id,
            'make_current',
            f'把「{package["title"]}」设为当前课包',
            moment,
        )
        course_id = int(package['course_id'])
    return course_detail(engine, user_id, course_id)
