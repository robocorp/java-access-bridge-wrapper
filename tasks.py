from pathlib import Path


REPO_ROOT = Path(__file__).parent.resolve()
CONFIG = REPO_ROOT / "config"
FLAKE8_CONFIG = CONFIG / "flake8"


from invoke import Context, task


def poetry(ctx: Context, command: str, **kwargs):
    """Executes Poetry commands on the shell."""
    return ctx.run(f"poetry {command}", **kwargs)


@task(
    help={
        "verbose": "Display detailed information with this on.",
        "install": "Also installs the package in development mode at the end."
    },
)
def update(ctx, verbose: bool = False, install: bool = True):
    """Updates the lock file based on the pinned versions."""
    poetry_opts = "-vvv" if verbose else ""
    poetry(ctx, f"update {poetry_opts}")
    if install:
        poetry(ctx, f"install {poetry_opts}")


@task(
    help={
        "apply": "Apply linting recommendations where possible."
    }
)
def lint(ctx, apply: bool = False):
    """Run linters to check code formatting."""
    warn = not apply
    sources = "src tests"

    isort_opts = "--diff" if not apply else ""
    poetry(ctx, f"run isort {isort_opts} {sources}", warn=warn)

    black_opts = "--diff --check" if not apply else ""
    poetry(ctx, f"run black {black_opts} {sources}", warn=warn)

    poetry(ctx, f"run flake8 --config {FLAKE8_CONFIG} {sources}", warn=warn)
