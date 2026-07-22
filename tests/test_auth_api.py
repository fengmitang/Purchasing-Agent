"""登录相关 HTTP 契约测试。"""

from fastapi.testclient import TestClient

from app.api.dependencies import get_auth_service, get_current_user
from app.bootstrap import create_application
from app.modules.auth.schemas import CurrentUserView
from app.shared.identity import CurrentUser


class StubAuthService:
    def __init__(self) -> None:
        self.logged_out_token: str | None = None

    async def login(self, **kwargs):
        assert kwargs["identifier"] == "DEV-E0001"
        assert kwargs["password"] == "ChangeMe2026!"
        return "opaque-test-token", self.view()

    async def logout(self, token):
        self.logged_out_token = token

    async def change_password(self, actor, **kwargs):
        assert actor.account_id == 7
        assert kwargs == {
            "current_password": "ChangeMe2026!",
            "new_password": "ChangedPass2026",
        }

    @staticmethod
    def current_user_view(actor):
        assert actor.user_code == "DEV-E0001"
        return StubAuthService.view()

    @staticmethod
    def view():
        return CurrentUserView(
            account_id=7,
            employee_id=11,
            employee_no="DEV-E0001",
            name="测试员工",
            phone="13000000001",
            roles=["EMPLOYEE"],
            building_ids=[],
            must_change_password=True,
        )


def build_client(service: StubAuthService) -> TestClient:
    application = create_application()
    application.dependency_overrides[get_auth_service] = lambda: service
    application.dependency_overrides[get_current_user] = lambda: CurrentUser(
        user_code="DEV-E0001",
        roles=frozenset({"EMPLOYEE"}),
        account_id=7,
        employee_id=11,
        name="测试员工",
        phone="13000000001",
        must_change_password=True,
    )
    return TestClient(application)


def test_login_sets_http_only_cookie_and_returns_chinese_profile() -> None:
    client = build_client(StubAuthService())
    response = client.post(
        "/api/v1/auth/login",
        json={"identifier": "DEV-E0001", "password": "ChangeMe2026!"},
    )

    assert response.status_code == 200
    assert response.json()["data"]["user"]["name"] == "测试员工"
    assert "pa_session=opaque-test-token" in response.headers["set-cookie"]
    assert "HttpOnly" in response.headers["set-cookie"]
    assert "SameSite=strict" in response.headers["set-cookie"]


def test_me_change_password_and_logout_contracts() -> None:
    service = StubAuthService()
    client = build_client(service)

    me_response = client.get("/api/v1/auth/me")
    change_response = client.post(
        "/api/v1/auth/change-password",
        json={"current_password": "ChangeMe2026!", "new_password": "ChangedPass2026"},
    )
    client.cookies.set("pa_session", "opaque-test-token")
    logout_response = client.post("/api/v1/auth/logout")

    assert me_response.json()["data"]["employee_no"] == "DEV-E0001"
    assert change_response.json()["data"]["message"] == "密码已修改，请重新登录"
    assert logout_response.json()["data"]["message"] == "已安全退出"
    assert service.logged_out_token == "opaque-test-token"
