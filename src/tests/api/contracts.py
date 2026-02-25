from __future__ import annotations

from typing import Iterable

from fastapi.routing import APIRoute

from ii_agent.auth.dependencies import get_current_user

RouteSpec = tuple[str, str]


def _iter_api_routes(route_holder) -> Iterable[APIRoute]:
    for route in route_holder.routes:
        if isinstance(route, APIRoute):
            yield route


def collect_route_specs(route_holder) -> set[RouteSpec]:
    specs: set[RouteSpec] = set()
    for route in _iter_api_routes(route_holder):
        for method in route.methods:
            if method in {"HEAD", "OPTIONS"}:
                continue
            specs.add((method, route.path))
    return specs


def assert_routes_present(route_holder, expected: Iterable[RouteSpec]) -> None:
    expected_set = set(expected)
    actual = collect_route_specs(route_holder)
    missing = sorted(expected_set - actual)
    assert not missing, f"Missing routes: {missing}"


def _find_route(route_holder, method: str, path: str) -> APIRoute:
    for route in _iter_api_routes(route_holder):
        if route.path != path:
            continue
        if method.upper() in route.methods:
            return route
    raise AssertionError(f"Route not found: {method.upper()} {path}")


def route_requires_auth(route: APIRoute) -> bool:
    return any(dep.call is get_current_user for dep in route.dependant.dependencies)


def assert_auth_contract(
    route_holder,
    protected: Iterable[RouteSpec] = (),
    public: Iterable[RouteSpec] = (),
) -> None:
    for method, path in protected:
        route = _find_route(route_holder, method, path)
        assert route_requires_auth(route), f"Route should require auth: {method} {path}"

    for method, path in public:
        route = _find_route(route_holder, method, path)
        assert not route_requires_auth(route), f"Route should be public: {method} {path}"
