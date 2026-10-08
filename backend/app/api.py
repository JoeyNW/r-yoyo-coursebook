"""HTTP routes. Authorization is enforced in the services."""

from typing import Annotated, Any

from fastapi import APIRouter, Depends, Request, Response
from fastapi.responses import JSONResponse

from app.errors import AppError
from app.schemas import (
    ConfirmIn,
    CourseIn,
    CoursePatch,
    EndScheduleIn,
    FamilyIn,
    InviteAcceptIn,
    LessonIn,
    LessonPatch,
    LoginIn,
    PackageIn,
    PackagePatch,
    RegisterIn,
    ReplaceScheduleIn,
    ScheduleIn,
)
from app.services import accounts, catalog, lessons

router = APIRouter()


def current_user(request: Request) -> dict[str, Any]:
    """Load the user from the session cookie."""
    token = request.cookies.get('session')
    if not token:
        raise AppError('unauthorized', '请先登录', 401)
    with request.app.state.engine.begin() as conn:
        user = accounts.user_from_token(conn, token)
    if user is None:
        raise AppError('unauthorized', '请先登录', 401)
    return dict(user)


CurrentUser = Annotated[dict[str, Any], Depends(current_user)]


def _set_cookie(response: Response, request: Request, token: str) -> None:
    response.set_cookie(
        key='session',
        value=token,
        httponly=True,
        samesite='lax',
        secure=bool(request.app.state.cookie_secure),
        max_age=int(request.app.state.session_days) * 24 * 3600,
        path='/',
    )


def _status_body(result: dict, response: Response) -> dict:
    response.status_code = 201 if result['created'] else 200
    return result


@router.get('/api/health')
def health() -> dict:
    return {'ok': True}


@router.post('/api/auth/register', status_code=201)
def register(body: RegisterIn, request: Request, response: Response) -> dict:
    profile, token = accounts.register_user(
        request.app.state.engine,
        body.login_name,
        body.password,
        body.display_name,
        request.app.state.session_days,
    )
    _set_cookie(response, request, token)
    return profile


@router.post('/api/auth/login')
def login(body: LoginIn, request: Request, response: Response) -> dict:
    profile, token = accounts.login_user(
        request.app.state.engine,
        body.login_name,
        body.password,
        request.app.state.session_days,
    )
    _set_cookie(response, request, token)
    return profile


@router.post('/api/auth/logout', status_code=204)
def logout(request: Request) -> Response:
    token = request.cookies.get('session')
    if token:
        accounts.logout(request.app.state.engine, token)
    outgoing = Response(status_code=204)
    outgoing.delete_cookie('session', path='/')
    return outgoing


@router.get('/api/me')
def me(request: Request, user: CurrentUser) -> dict:
    return accounts.profile_for(request.app.state.engine, int(user['id']))


@router.post('/api/families', status_code=201)
def create_family(
    body: FamilyIn,
    request: Request,
    user: CurrentUser,
) -> dict:
    return accounts.create_family(
        request.app.state.engine,
        int(user['id']),
        body.name,
    )


@router.post('/api/families/{family_id}/invitations', status_code=201)
def invite(family_id: int, request: Request, user: CurrentUser) -> dict:
    return accounts.create_invitation(
        request.app.state.engine,
        int(user['id']),
        family_id,
    )


@router.post('/api/invitations/accept')
def accept(
    body: InviteAcceptIn,
    request: Request,
    user: CurrentUser,
) -> dict:
    return accounts.accept_invitation(
        request.app.state.engine,
        int(user['id']),
        body.code,
    )


@router.get('/api/families/{family_id}/members')
def members(family_id: int, request: Request, user: CurrentUser) -> dict:
    return accounts.list_members(
        request.app.state.engine,
        int(user['id']),
        family_id,
    )


@router.delete(
    '/api/families/{family_id}/members/{member_user_id}',
    status_code=204,
)
def remove_member(
    family_id: int,
    member_user_id: int,
    request: Request,
    user: CurrentUser,
) -> Response:
    accounts.remove_member(
        request.app.state.engine,
        int(user['id']),
        family_id,
        member_user_id,
    )
    return Response(status_code=204)


@router.get('/api/families/{family_id}/home')
def home(family_id: int, request: Request, user: CurrentUser) -> dict:
    return lessons.home(
        request.app.state.engine,
        int(user['id']),
        family_id,
    )


@router.get('/api/families/{family_id}/calendar')
def calendar(
    family_id: int,
    request: Request,
    user: CurrentUser,
    start: str,
    end: str,
) -> dict:
    return lessons.calendar_view(
        request.app.state.engine,
        int(user['id']),
        family_id,
        start,
        end,
    )


@router.get('/api/families/{family_id}/export')
def export_family(family_id: int, request: Request, user: CurrentUser) -> Response:
    payload = lessons.export_family(
        request.app.state.engine,
        int(user['id']),
        family_id,
    )
    import json

    return Response(
        content=json.dumps(payload, ensure_ascii=False, indent=2),
        media_type='application/json',
        headers={
            'Content-Disposition': 'attachment; filename="yoyo-export.json"',
        },
    )


@router.get('/api/families/{family_id}/courses')
def list_courses(family_id: int, request: Request, user: CurrentUser) -> dict:
    return catalog.list_courses(
        request.app.state.engine,
        int(user['id']),
        family_id,
    )


@router.post('/api/families/{family_id}/courses', status_code=201)
def create_course(
    family_id: int,
    body: CourseIn,
    request: Request,
    user: CurrentUser,
) -> dict:
    return catalog.create_course(
        request.app.state.engine,
        int(user['id']),
        family_id,
        body.name,
        body.color,
        body.teacher,
        body.location,
        body.notes,
        [item.model_dump() for item in body.schedules],
    )


@router.get('/api/courses/{course_id}')
def get_course(course_id: int, request: Request, user: CurrentUser) -> dict:
    return catalog.course_detail(
        request.app.state.engine,
        int(user['id']),
        course_id,
    )


@router.patch('/api/courses/{course_id}')
def patch_course(
    course_id: int,
    body: CoursePatch,
    request: Request,
    user: CurrentUser,
) -> dict:
    return catalog.update_course(
        request.app.state.engine,
        int(user['id']),
        course_id,
        body.model_dump(exclude_unset=True),
    )


@router.post('/api/courses/{course_id}/schedules', status_code=201)
def add_schedule(
    course_id: int,
    body: ScheduleIn,
    request: Request,
    user: CurrentUser,
) -> dict:
    return catalog.add_schedule(
        request.app.state.engine,
        int(user['id']),
        course_id,
        body.weekday,
        body.local_time,
        body.effective_from,
    )


@router.post('/api/schedules/{schedule_id}/replace')
def replace_schedule(
    schedule_id: int,
    body: ReplaceScheduleIn,
    request: Request,
    user: CurrentUser,
) -> dict:
    return catalog.replace_schedule(
        request.app.state.engine,
        int(user['id']),
        schedule_id,
        body.weekday,
        body.local_time,
        body.effective_on,
    )


@router.post('/api/schedules/{schedule_id}/end')
def end_schedule(
    schedule_id: int,
    body: EndScheduleIn,
    request: Request,
    user: CurrentUser,
) -> dict:
    return catalog.end_schedule(
        request.app.state.engine,
        int(user['id']),
        schedule_id,
        body.last_date,
    )


@router.post('/api/courses/{course_id}/packages', status_code=201)
def create_package(
    course_id: int,
    body: PackageIn,
    request: Request,
    user: CurrentUser,
) -> dict:
    return catalog.create_package(
        request.app.state.engine,
        int(user['id']),
        course_id,
        body.title,
        body.total_units,
        body.opening_consumed_units,
        body.start_date,
        body.expiry_date,
        body.notes,
    )


@router.patch('/api/packages/{package_id}')
def patch_package(
    package_id: int,
    body: PackagePatch,
    request: Request,
    user: CurrentUser,
) -> dict:
    return catalog.update_package(
        request.app.state.engine,
        int(user['id']),
        package_id,
        body.model_dump(exclude_unset=True),
    )


@router.post('/api/packages/{package_id}/make-current')
def make_current(
    package_id: int,
    request: Request,
    user: CurrentUser,
) -> dict:
    return catalog.make_current(
        request.app.state.engine,
        int(user['id']),
        package_id,
    )


@router.post('/api/courses/{course_id}/quick-check-in')
def quick_check_in(
    course_id: int,
    request: Request,
    response: Response,
    user: CurrentUser,
) -> dict:
    result = lessons.quick_check_in(
        request.app.state.engine,
        int(user['id']),
        course_id,
    )
    return _status_body(result, response)


@router.post('/api/lessons')
def create_lesson(
    body: LessonIn,
    request: Request,
    response: Response,
    user: CurrentUser,
) -> dict:
    result = lessons.check_in(
        request.app.state.engine,
        int(user['id']),
        body.course_id,
        body.local_date,
        body.local_time,
        body.source,
        body.status,
        body.charge,
        body.notes,
    )
    return _status_body(result, response)


@router.post('/api/lessons/{lesson_id}/void')
def void_lesson(
    lesson_id: int,
    body: ConfirmIn,
    request: Request,
    user: CurrentUser,
) -> dict:
    return lessons.void_lesson(
        request.app.state.engine,
        int(user['id']),
        lesson_id,
        body.confirm,
    )


@router.patch('/api/lessons/{lesson_id}')
def patch_lesson(
    lesson_id: int,
    body: LessonPatch,
    request: Request,
    user: CurrentUser,
) -> dict:
    return lessons.update_lesson(
        request.app.state.engine,
        int(user['id']),
        lesson_id,
        body.status,
        body.charge,
        body.notes,
        body.confirm,
    )


def app_error_handler(_request: Request, exc: AppError) -> JSONResponse:
    """Render a service error as JSON."""
    payload = dict(exc.extra)
    payload['code'] = exc.code
    payload['message'] = exc.message
    return JSONResponse(status_code=exc.status, content={'detail': payload})
