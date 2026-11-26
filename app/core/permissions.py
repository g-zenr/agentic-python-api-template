"""Role-based access control: map roles to permissions and check them."""

from app.core.constants import Permission, Role

ROLE_PERMISSIONS: dict[Role, frozenset[Permission]] = {
    Role.USER: frozenset(),
    Role.ADMIN: frozenset(Permission),
}


def has_permission(role: Role, perm: Permission) -> bool:
    return perm in ROLE_PERMISSIONS.get(role, frozenset())
