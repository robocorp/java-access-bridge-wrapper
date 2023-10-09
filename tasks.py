from pathlib import Path
from typing import Optional

REPO_ROOT = Path(__file__).parent.resolve()
CONFIG = REPO_ROOT / "config"
FLAKE8_CONFIG = CONFIG / "flake8"
DEVPI_URL = "https://devpi.robocorp.cloud/ci/test"


from invoke import Context, ParseError, task


def poetry(ctx: Context, command: str, **kwargs):
    """Executes Poetry commands on the shell."""
    return ctx.run(f"poetry {command}", **kwargs)


def invoke(ctx: Context, command: str, **kwargs):
    """Executes Invoke commands on the shell."""
    return ctx.run(f"invoke {command}", **kwargs)


@task(
    help={
        "username": (
            "Configures credentials for PyPI or a devpi repository."
            " The username will be stored by Poetry in the system keyring."
        ),
        "password": (
            "Configures credentials for PyPI or a devpi repository."
            " The password will be stored by Poetry in the system keyring."
        ),
        "token": ("Can be used in place of '--username' and '--password'," " the token must be prefixed by 'pypi-'."),
        "ci": (
            "Configures the CI DevPI instead of the production PyPI. This is required" " when publishing with '--ci'."
        ),
    }
)
def setup(
    ctx, username: Optional[str] = None, password: Optional[str] = None, token: Optional[str] = None, ci: bool = False
):
    """Setup Poetry with the right configuration for library development."""
    config_cmd = "config --no-interaction --local"
    poetry(ctx, f"{config_cmd} virtualenvs.in-project true")
    poetry(ctx, f"{config_cmd} virtualenvs.create true")
    poetry(ctx, f"{config_cmd} virtualenvs.path null")
    poetry(ctx, f"{config_cmd} installer.parallel true")

    if ci:
        repo = "devpi"
        poetry(ctx, f"{config_cmd} repositories.{repo} {DEVPI_URL}")
    else:
        repo = "pypi"
    if username and password:
        creds = f"http-basic.{repo} {username} {password}"
    elif token:
        creds = f"pypi-token.{repo} {token}"
    else:
        raise ParseError("You have to provide either both 'username' & 'password' or a 'token'")
    poetry(ctx, f"{config_cmd} {creds}", echo=False)


@task(
    help={
        "verbose": "Display detailed information with this on.",
        "install": "Also installs the package in development mode at the end.",
    },
)
def update(ctx, verbose: bool = False, install: bool = True):
    """Update the dependency lock file based on the pinned versions."""
    poetry_opts = "-vvv" if verbose else ""
    poetry(ctx, f"update {poetry_opts}")
    if install:
        poetry(ctx, f"install {poetry_opts}")


@task(help={"apply": "Apply linting recommendations where possible."})
def lint(ctx, apply: bool = False):
    """Run linters to check code formatting."""
    warn = not apply
    sources = "src tests"

    isort_opts = "--diff" if not apply else ""
    poetry(ctx, f"run isort {isort_opts} {sources}", warn=warn)

    black_opts = "--diff --check" if not apply else ""
    poetry(ctx, f"run black {black_opts} {sources}", warn=warn)

    poetry(ctx, f"run flake8 --config {FLAKE8_CONFIG} {sources}", warn=warn)


@task(
    help={
        "verbose": "Display detailed information with this on.",
        "capture_output": "Display printed information in the console.",
        "test": "Run specific test. (e.g.: 'test_jab_wrapper.py::test_app_flow')",
        "simple": "Test a single title-based scenario with disabled callbacks."
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

    poetry(ctx, f"run pytest {pytest_opts} {target}")


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

    poetry(ctx, "build -vv -f sdist")
    poetry(ctx, "build -vv -f wheel")

    if build_only:
        return

    publish_opts = "-v --no-interaction --repository devpi" if ci else ""
    poetry(ctx, f"publish {publish_opts}")
