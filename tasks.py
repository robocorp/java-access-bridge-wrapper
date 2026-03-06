from pathlib import Path
from typing import Optional

REPO_ROOT = Path(__file__).parent.resolve()
CONFIG = REPO_ROOT / "config"
FLAKE8_CONFIG = CONFIG / "flake8"
DEVPI_URL = "https://devpi.robocorp.cloud/ci/test"


from invoke import Context, task


def uv(ctx: Context, command: str, **kwargs):
    """Executes uv commands on the shell."""
    return ctx.run(f"uv {command}", **kwargs)


def invoke(ctx: Context, command: str, **kwargs):
    """Executes Invoke commands on the shell."""
    return ctx.run(f"invoke {command}", **kwargs)


@task(
    help={
        "verbose": "Display detailed information with this on.",
    },
)
def update(ctx, verbose: bool = False):
    """Update the dependency lock file and install dependencies."""
    uv_opts = "-v" if verbose else ""
    uv(ctx, f"lock {uv_opts}")
    uv(ctx, f"sync --all-groups {uv_opts}")


@task(help={"apply": "Apply linting recommendations where possible."})
def lint(ctx, apply: bool = False):
    """Run linters to check code formatting."""
    warn = not apply
    sources = "src tests"

    isort_opts = "" if apply else "--check --diff"
    uv(ctx, f"run isort {isort_opts} {sources}", warn=warn)

    black_opts = "" if apply else "--check --diff"
    uv(ctx, f"run black {black_opts} {sources}", warn=warn)

    uv(ctx, f"run flake8 --config {FLAKE8_CONFIG} {sources}", warn=warn)


@task(
    help={
        "verbose": "Display detailed information with this on.",
        "capture_output": "Display printed information in the console.",
        "test": "Run specific test. (e.g.: 'test_jab_wrapper.py::test_app_flow')",
        "simple": "Test a single title-based scenario with disabled callbacks.",
    },
)
def test(ctx, verbose: bool = False, capture_output: bool = False, test: Optional[str] = None, simple: bool = False):
    """Run tests."""
    pytest_args = []
    if verbose:
        pytest_args.append("-vv")
        log_level = "DEBUG"
    else:
        log_level = "INFO"
    pytest_args.append(f"-o log_level={log_level}")
    if capture_output:
        pytest_args.extend(["-s", "-o log_cli=true", f"-o log_cli_level={log_level}"])
    if simple:
        pytest_args.append("--simple")
    pytest_opts = " ".join(pytest_args)
    target = "tests"
    if test:
        parts = test.split("::", 1)
        target = f"{Path(target) / parts[0]}"
        if len(parts) == 2:
            target = f"{target}::{parts[1]}"

    uv(ctx, f"run pytest {pytest_opts} {target}")


@task(
    help={
        "build_only": "Stop after building and do not publish the package.",
        "ci": "Publish the package into our DevPI CI instead of the production PyPI.",
    }
)
def publish(ctx, build_only: bool = False, ci: bool = False):
    """Build and publish the library to the configured packages index."""
    if not (build_only or ci):
        invoke(ctx, "update")
        invoke(ctx, "lint")
        invoke(ctx, "test")

    uv(ctx, "build")

    if build_only:
        return

    if ci:
        uv(ctx, f"publish --publish-url {DEVPI_URL}")
    else:
        uv(ctx, "publish")
