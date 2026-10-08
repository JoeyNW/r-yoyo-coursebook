"""Insert labeled demo data. Safe to run more than once."""

from app.main import create_app
from app.services import accounts, catalog
from app.services.accounts import find_login
from app.timeutil import month_start


def main() -> None:
    """Create the demo family when the demo login is absent."""
    app = create_app()
    engine = app.state.engine
    with engine.begin() as conn:
        existing = find_login(conn, 'demo')
    if existing is not None:
        print('示例账号已存在：demo / demo-pass-123')
        return
    owner, _token = accounts.register_user(
        engine,
        'demo',
        'demo-pass-123',
        '悠悠妈妈',
        app.state.session_days,
    )
    family = accounts.create_family(engine, owner['user']['id'], '悠悠的家')
    start = month_start().isoformat()
    course = catalog.create_course(
        engine,
        owner['user']['id'],
        family['id'],
        '英语',
        '#0f766e',
        '',
        '',
        '',
        [
            {
                'weekday': 0,
                'local_time': '16:30',
                'effective_from': start,
            },
            {
                'weekday': 4,
                'local_time': '19:00',
                'effective_from': start,
            },
        ],
    )
    catalog.create_package(
        engine,
        owner['user']['id'],
        course['id'],
        'DEMO示例课包',
        10,
        0,
        None,
        None,
        '示例数据，不是真实报名节数',
    )
    invite = accounts.create_invitation(
        engine,
        owner['user']['id'],
        family['id'],
    )
    member, _token = accounts.register_user(
        engine,
        'baba',
        'demo-pass-123',
        '悠悠爸爸',
        app.state.session_days,
    )
    accounts.accept_invitation(engine, member['user']['id'], invite['code'])
    print('已写入示例数据，不是真实报名。')
    print('家长A  demo / demo-pass-123')
    print('家长B  baba / demo-pass-123')


if __name__ == '__main__':
    main()
