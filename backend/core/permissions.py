from rest_framework.permissions import BasePermission


def role_of(user):
    p = getattr(user, "profile", None) if user.is_authenticated else None
    return p.role if p else None


class IsStaff(BasePermission):
    def has_permission(self, request, view):
        return role_of(request.user) in ("sales_head", "executive")


class IsSalesHead(BasePermission):
    def has_permission(self, request, view):
        return role_of(request.user) == "sales_head"
