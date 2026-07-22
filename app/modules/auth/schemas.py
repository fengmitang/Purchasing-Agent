"""登录、当前用户和修改密码接口的数据结构。"""

from pydantic import BaseModel, Field, field_validator


class LoginRequest(BaseModel):
    """员工使用工号或电话登录。"""

    identifier: str = Field(min_length=1, max_length=191, description="员工工号或联系电话")
    password: str = Field(min_length=1, max_length=256, description="登录密码")

    @field_validator("identifier")
    @classmethod
    def clean_identifier(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("请输入员工工号或联系电话")
        return value


class ChangePasswordRequest(BaseModel):
    """当前登录员工修改自己的密码。"""

    current_password: str = Field(min_length=1, max_length=256, description="当前密码")
    new_password: str = Field(min_length=10, max_length=128, description="新密码，至少 10 位")


class CurrentUserView(BaseModel):
    """前端恢复登录状态和显示角色菜单所需的信息。"""

    account_id: int
    employee_id: int
    employee_no: str
    name: str
    phone: str | None
    roles: list[str]
    building_ids: list[int]
    must_change_password: bool


class LoginResult(BaseModel):
    """登录成功后的当前用户信息。"""

    user: CurrentUserView


class MessageResult(BaseModel):
    """无业务对象写操作的确认信息。"""

    message: str
