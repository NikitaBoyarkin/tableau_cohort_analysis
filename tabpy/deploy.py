#!/usr/bin/env python3
"""Deploy the cohort-analysis endpoints to a running TabPy server.

Order of operations matters:

1. Start the server first (a separate terminal):

       tabpy --config=tabpy/tabpy.conf

2. Then deploy the endpoints (this script):

       uv run python tabpy/deploy.py --dry-run          # plan only, no network
       uv run python tabpy/deploy.py --url http://localhost:9004/
       uv run python tabpy/deploy.py --override         # redeploy, version +1

The endpoint functions live in ``tabpy_functions.py`` at the project root and
are exposed through its ``ENDPOINTS`` dict. This project is not a package
(``package = false``), so the project root is added to ``sys.path`` before that
module is imported.

The TabPy client is imported lazily inside functions, so ``--help`` and
``--dry-run`` keep working when the optional ``tabpy`` dependency is not
installed (``uv sync --extra tabpy`` or ``pip install tabpy``).
"""

from __future__ import annotations

import argparse
import os
import sys
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, NoReturn

DEFAULT_URL = "http://localhost:9004/"
PROJECT_ROOT = Path(__file__).resolve().parent.parent


@dataclass(frozen=True)
class EndpointSpec:
    """Everything needed to deploy one endpoint: sample data and docs.

    ``generate_schema`` infers JSON types from the sample values, so the
    samples are part of the contract, not decoration.
    """

    name: str
    description: str
    sample_input: dict[str, Any]
    sample_output: Any
    input_description: dict[str, str]
    output_description: str


SPECS: tuple[EndpointSpec, ...] = (
    EndpointSpec(
        name="retention_rate",
        description="Cohort retention rate: active users / cohort size, per period.",
        sample_input={
            "active": [100, 80, 60],
            "cohort_size": [1000, 1000, 1000],
        },
        sample_output=[0.1, 0.08, 0.06],
        input_description={
            "active": "Active users per period (same length as cohort_size).",
            "cohort_size": "Cohort size per period; non-positive values yield null.",
        },
        output_description="Retention rate per period; null where cohort_size <= 0.",
    ),
    EndpointSpec(
        name="wilson_lower",
        description="Lower bound of the Wilson score interval for a proportion.",
        sample_input={
            "successes": [10, 20],
            "trials": [100, 200],
            "level": 0.95,
        },
        sample_output=[0.0552, 0.0657],
        input_description={
            "successes": "Number of successes per row.",
            "trials": "Number of trials per row.",
            "level": "Confidence level, default 0.95.",
        },
        output_description="Lower confidence bound per row.",
    ),
    EndpointSpec(
        name="wilson_upper",
        description="Upper bound of the Wilson score interval for a proportion.",
        sample_input={
            "successes": [10, 20],
            "trials": [100, 200],
            "level": 0.95,
        },
        sample_output=[0.1744, 0.1494],
        input_description={
            "successes": "Number of successes per row.",
            "trials": "Number of trials per row.",
            "level": "Confidence level, default 0.95.",
        },
        output_description="Upper confidence bound per row.",
    ),
    EndpointSpec(
        name="ztest_two_proportions",
        description="Two-proportion z-test; returns the p-value per row.",
        sample_input={
            "successes_a": [10],
            "trials_a": [100],
            "successes_b": [15],
            "trials_b": [100],
        },
        sample_output=[0.285],
        input_description={
            "successes_a": "Successes in group A.",
            "trials_a": "Trials in group A.",
            "successes_b": "Successes in group B.",
            "trials_b": "Trials in group B.",
        },
        output_description="Two-sided p-value per row; null when undefined.",
    ),
    EndpointSpec(
        name="retention_forecast",
        description="Smoothed continuation of the retention curve over periods.",
        sample_input={
            "rates": [1.0, 0.8, 0.65],
            "periods": [3, 4, 5],
        },
        sample_output=[1.0, 0.79, 0.65],
        input_description={
            "rates": "Observed retention rates, ordered by period.",
            "periods": "Periods to forecast; defaults to the observed grid.",
        },
        output_description="Forecast retention rate per requested period.",
    ),
    EndpointSpec(
        name="ltv_at_horizon",
        description="Extrapolated LTV per user at a given horizon.",
        sample_input={
            "revenue_by_period": [1000, 800, 600],
            "users": 100,
            "horizon": 12,
        },
        sample_output=[42.75],
        input_description={
            "revenue_by_period": "Revenue observed per period, starting at period 0.",
            "users": "Number of users the revenue is attributed to (scalar).",
            "horizon": "Periods to extrapolate to.",
        },
        output_description="Single-element list with LTV per user at the horizon.",
    ),
)


def _fail(message: str) -> NoReturn:
    """Print an error and exit non-zero. Never swallow failures silently."""
    print(f"[error] {message}", file=sys.stderr)
    sys.exit(1)


def resolve_password(args: argparse.Namespace) -> str | None:
    """CLI flag wins over the TABPY_PASSWORD environment variable."""
    if args.password:
        return args.password
    return os.environ.get("TABPY_PASSWORD") or None


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="deploy.py",
        description="Deploy cohort-analysis endpoints to a running TabPy server.",
    )
    parser.add_argument(
        "--url",
        default=DEFAULT_URL,
        help=f"TabPy server URL (default: {DEFAULT_URL})",
    )
    parser.add_argument("--username", help="Username when TabPy auth is enabled.")
    parser.add_argument(
        "--password",
        help="Password when TabPy auth is enabled. Falls back to $TABPY_PASSWORD.",
    )
    parser.add_argument(
        "--override",
        action="store_true",
        help="Redeploy existing endpoints (their version is incremented).",
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--dry-run",
        action="store_true",
        help="List what would be deployed. No network calls, no tabpy import needed.",
    )
    mode.add_argument(
        "--list",
        action="store_true",
        help="Print endpoints currently deployed on the server.",
    )
    return parser.parse_args(argv)


def make_client(url: str, username: str | None, password: str | None) -> Any:
    """Build a TabPy Client, importing the optional dependency lazily."""
    try:
        from tabpy.tabpy_tools.client import Client
    except ImportError as exc:
        _fail(
            f"TabPy client is not installed ({exc}). "
            "Install it with 'uv sync --extra tabpy' or 'pip install tabpy'."
        )
    client = Client(url)
    if username:
        client.set_credentials(username, password)
    return client


def build_schema(spec: EndpointSpec) -> dict[str, Any]:
    """Generate the endpoint schema from the spec's sample values."""
    try:
        from tabpy.tabpy_tools.schema import generate_schema
    except ImportError as exc:
        _fail(f"TabPy client is not installed ({exc}).")
    return generate_schema(
        input=spec.sample_input,
        output=spec.sample_output,
        input_description=spec.input_description,
        output_description=spec.output_description,
    )


def probe_functions_module() -> tuple[dict[str, Callable[..., Any]] | None, str | None]:
    """Try to import tabpy_functions.ENDPOINTS without failing the dry run."""
    if str(PROJECT_ROOT) not in sys.path:
        sys.path.insert(0, str(PROJECT_ROOT))
    try:
        import tabpy_functions
    except Exception as exc:  # noqa: BLE001 - dry run reports, never raises
        return None, f"{type(exc).__name__}: {exc}"
    endpoints = getattr(tabpy_functions, "ENDPOINTS", None)
    if not isinstance(endpoints, dict):
        return None, "tabpy_functions.ENDPOINTS is missing or is not a dict"
    return endpoints, None


def load_endpoint_functions() -> dict[str, Callable[..., Any]]:
    """Import ENDPOINTS for a real deploy; abort with a clear message on failure."""
    endpoints, error = probe_functions_module()
    if endpoints is None:
        _fail(f"cannot load ENDPOINTS from {PROJECT_ROOT / 'tabpy_functions.py'}: {error}")
    register_by_value()
    return endpoints


def register_by_value() -> None:
    """Make cloudpickle serialise ``tabpy_functions`` by value, not by reference.

    With the default reference pickling the server has to import the module when
    it loads the endpoint, and fails with "No module named 'tabpy_functions'"
    because the project root is not on its ``sys.path``. Registering the module
    by value embeds the code in the deployed endpoint, so the server needs no
    project checkout at all.
    """
    try:
        import cloudpickle

        import tabpy_functions
    except ImportError as exc:
        _fail(f"cannot register tabpy_functions for by-value pickling: {exc}")
    cloudpickle.register_pickle_by_value(tabpy_functions)


def dry_run(url: str) -> None:
    """Print the deployment plan. Touches neither the network nor TabPy."""
    print(f"TabPy deployment plan (dry run, no network calls)\n  target: {url}\n")
    for spec in SPECS:
        print(f"  [plan] {spec.name}: {spec.description}")
    print(f"\n{len(SPECS)} endpoint(s) would be deployed.")

    endpoints, error = probe_functions_module()
    if endpoints is None:
        print(f"[info] tabpy_functions.ENDPOINTS not loadable yet: {error}")
        return
    missing = sorted(spec.name for spec in SPECS if not callable(endpoints.get(spec.name)))
    if missing:
        print(f"[info] tabpy_functions.ENDPOINTS is missing: {', '.join(missing)}")
    else:
        print("[info] tabpy_functions.ENDPOINTS provides every planned endpoint.")


def get_endpoints(client: Any, url: str) -> dict[str, Any]:
    """Fetch deployed endpoints, converting transport failures into a clear exit."""
    try:
        return client.get_endpoints()
    except Exception as exc:  # TabPy reports HTTP failures as rest.ResponseError
        _fail(
            f"cannot reach TabPy at {url}: {exc}. "
            "Is the server running ('tabpy --config=tabpy/tabpy.conf')? "
            "Are credentials valid if auth is enabled?"
        )


def list_endpoints(client: Any, url: str) -> None:
    endpoints = get_endpoints(client, url)
    if not endpoints:
        print("no endpoints deployed")
        return
    print(f"{len(endpoints)} endpoint(s) on {url}:")
    for name in sorted(endpoints):
        endpoint = endpoints[name]
        description = endpoint.description or "(no description)"
        print(f"  {name}  v{endpoint.version}  {description}")


def deploy(client: Any, url: str, override: bool) -> int:
    """Deploy every spec; returns the number of failures."""
    functions = load_endpoint_functions()
    existing = get_endpoints(client, url)
    versions = {name: endpoint.version for name, endpoint in existing.items()}

    failures = 0
    skipped = 0
    deployed = 0

    for spec in SPECS:
        function = functions.get(spec.name)
        if not callable(function):
            print(f"[missing] {spec.name}: no callable in tabpy_functions.ENDPOINTS")
            failures += 1
            continue

        if spec.name in versions and not override:
            print(
                f"[skip] {spec.name}: already deployed (v{versions[spec.name]}); "
                "use --override to redeploy"
            )
            skipped += 1
            continue

        next_version = versions.get(spec.name, 0) + 1
        try:
            schema = build_schema(spec)
        except Exception as exc:  # TabPy reports HTTP failures as rest.ResponseError
            print(f"[fail] {spec.name}: schema generation failed: {exc}", file=sys.stderr)
            failures += 1
            continue

        try:
            client.deploy(
                spec.name,
                function,
                spec.description,
                override=override,
                schema=schema,
            )
        except Exception as exc:  # TabPy reports HTTP failures as rest.ResponseError
            print(f"[fail] {spec.name}: {exc}", file=sys.stderr)
            failures += 1
            continue

        print(f"[ok] {spec.name} -> v{next_version}")
        deployed += 1
        versions[spec.name] = next_version

    print(f"\nsummary: {deployed} deployed, {skipped} skipped, {failures} failed")
    return failures


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    password = resolve_password(args)

    if args.username and not password:
        _fail("--username given without a password: use --password or $TABPY_PASSWORD")
    if password and not args.username:
        _fail("a password was provided but --username is missing")

    if args.dry_run:
        dry_run(args.url)
        return 0

    client = make_client(args.url, args.username, password)
    if args.list:
        list_endpoints(client, args.url)
        return 0

    return 1 if deploy(client, args.url, args.override) else 0


if __name__ == "__main__":
    sys.exit(main())
