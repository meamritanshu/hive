"""Skill base class and decorator.

Provides the interface for creating skills -- reusable capabilities
that extend the agent's functionality without modifying core code.

Skills can be:
- Simple decorated functions
- Full classes with lifecycle management
- Packaged with a skill.toml manifest

Security model
--------------
Skills declare the permissions they need via the ``permissions`` list in
their manifest or decorator.  Valid permission tokens are:

    network       – outbound HTTP/socket connections
    filesystem    – read/write access outside the sandbox temp dir
    shell         – ability to spawn subprocesses
    secrets:<KEY> – access to a specific secret/API-key by env-var name
                    e.g. ``secrets:OPENAI_API_KEY``

At load time the SkillLoader checks declared permissions against the
allow-list in ``skill_name.toml`` (if present) or the global
``[skills] default_permissions`` setting.  Undeclared permissions are
denied; attempting to use one at runtime raises ``PermissionError``.

Secrets / API keys are delivered via a ``SkillContext`` object that is
injected into the subprocess environment – the raw ``config.toml`` is
never exposed to skill code.

Requirements header
-------------------
Skill files may declare pip dependencies in a comment header::

    # Requirements: requests>=2.31, beautifulsoup4

HiveCore parses this on first load and installs missing packages into an
isolated virtual environment dedicated to that skill before execution.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

from hivecore.core.tools.base import FunctionTool


# ---------------------------------------------------------------------------
# Valid permission tokens
# ---------------------------------------------------------------------------

VALID_PERMISSIONS = frozenset({
    "network",
    "filesystem",
    "shell",
})

# secrets:<KEY_NAME> is also valid; validated separately


def _validate_permission(perm: str) -> bool:
    """Return True if *perm* is a recognised permission token."""
    if perm in VALID_PERMISSIONS:
        return True
    if perm.startswith("secrets:") and len(perm) > len("secrets:"):
        return True
    return False


# ---------------------------------------------------------------------------
# SkillContext – the only view of secrets/config a skill subprocess sees
# ---------------------------------------------------------------------------

@dataclass
class SkillContext:
    """A minimal, filtered view of configuration passed to a skill subprocess.

    The skill subprocess receives *only* the keys listed in the skill's
    ``permissions`` manifest field (e.g. ``secrets:OPENAI_API_KEY``).
    The full ``config.toml`` and ``HiveSettings`` object are never exposed.

    Attributes:
        skill_name: Name of the skill being executed.
        secrets: Mapping of requested secret names to their values.
            Only secrets explicitly declared as ``secrets:<KEY>`` in the
            skill manifest are populated.
        extra: Any additional non-sensitive context the caller wants to pass.
    """

    skill_name: str
    secrets: dict[str, str] = field(default_factory=dict)
    extra: dict[str, Any] = field(default_factory=dict)

    def to_env(self) -> dict[str, str]:
        """Return env-var overrides suitable for subprocess.Popen(env=...)."""
        env: dict[str, str] = {}
        for key, value in self.secrets.items():
            env[key] = value
        return env

    @classmethod
    def build(
        cls,
        skill_name: str,
        declared_permissions: list[str],
        secrets_source: dict[str, str],
    ) -> "SkillContext":
        """Build a SkillContext by filtering *secrets_source* to only the
        secrets the skill has declared it needs.

        Args:
            skill_name: The skill's name.
            declared_permissions: The ``permissions`` list from the manifest.
            secrets_source: A flat mapping of secret names to values
                (typically derived from ``HiveSettings`` or ``os.environ``).

        Returns:
            A ``SkillContext`` containing only allowed secrets.
        """
        allowed_secrets: dict[str, str] = {}
        for perm in declared_permissions:
            if perm.startswith("secrets:"):
                key = perm[len("secrets:"):]
                if key in secrets_source:
                    allowed_secrets[key] = secrets_source[key]
        return cls(skill_name=skill_name, secrets=allowed_secrets)


# ---------------------------------------------------------------------------
# Requirements parsing
# ---------------------------------------------------------------------------

_REQUIREMENTS_RE = re.compile(
    r"^#\s*[Rr]equirements?\s*:\s*(.+)$", re.MULTILINE
)


def parse_requirements_header(source: str) -> list[str]:
    """Parse a ``# Requirements: pkg1, pkg2>=1.0`` header from skill source.

    Args:
        source: The full text of a skill Python file.

    Returns:
        List of pip requirement specifiers found in the header.
        Returns an empty list if no header is present.
    """
    match = _REQUIREMENTS_RE.search(source)
    if not match:
        return []
    raw = match.group(1)
    return [r.strip() for r in raw.split(",") if r.strip()]


def ensure_requirements(
    requirements: list[str],
    skill_name: str,
    venv_dir: Optional[str] = None,
) -> None:
    """Install *requirements* into the skill's isolated virtual environment.

    Uses ``pip`` (via ``subprocess``) to install any missing packages.
    The virtual environment is created at *venv_dir* (or a default path
    inside ``~/.hivecore/skill_envs/<skill_name>/``) if it does not exist.

    Args:
        requirements: List of pip requirement specifiers.
        skill_name: The skill name (used to name the venv directory).
        venv_dir: Optional override for the venv location.
    """
    import logging
    import subprocess
    import sys
    import venv
    from pathlib import Path

    if not requirements:
        return

    logger = logging.getLogger(__name__)

    # Determine venv path
    if venv_dir:
        venv_path = Path(venv_dir)
    else:
        base = Path.home() / ".hivecore" / "skill_envs" / skill_name
        venv_path = base

    # Create venv if needed
    if not venv_path.exists():
        logger.info("Creating skill venv for '%s' at %s", skill_name, venv_path)
        venv.create(str(venv_path), with_pip=True, clear=False)

    # Resolve the pip executable inside the venv
    if sys.platform == "win32":
        pip_exe = venv_path / "Scripts" / "pip.exe"
    else:
        pip_exe = venv_path / "bin" / "pip"

    logger.info("Installing requirements for skill '%s': %s", skill_name, requirements)
    try:
        subprocess.run(
            [str(pip_exe), "install", "--quiet", "--upgrade"] + requirements,
            check=True,
            capture_output=True,
            text=True,
        )
        logger.info("Requirements installed successfully for skill '%s'", skill_name)
    except subprocess.CalledProcessError as exc:
        logger.error(
            "Failed to install requirements for skill '%s': %s\n%s",
            skill_name,
            exc.returncode,
            exc.stderr,
        )
        raise RuntimeError(
            f"Skill '{skill_name}' requires packages {requirements} but installation failed. "
            f"Run manually: pip install {' '.join(requirements)}"
        ) from exc


# ---------------------------------------------------------------------------
# SkillManifest
# ---------------------------------------------------------------------------

@dataclass
class SkillManifest:
    """Metadata about a skill, loaded from skill.toml or decorator args."""

    name: str
    description: str = ""
    version: str = "0.1.0"
    author: str = "unknown"
    dependencies: list[str] = field(default_factory=list)
    config_schema: dict[str, Any] = field(default_factory=dict)
    permissions: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    status: str = "active"

    def __post_init__(self) -> None:
        """Validate permission tokens at manifest creation time."""
        invalid = [p for p in self.permissions if not _validate_permission(p)]
        if invalid:
            raise ValueError(
                f"Skill '{self.name}' declares unknown permissions: {invalid}. "
                f"Valid tokens: {sorted(VALID_PERMISSIONS)} or 'secrets:<KEY_NAME>'."
            )


# ---------------------------------------------------------------------------
# Skill class
# ---------------------------------------------------------------------------

class Skill:
    """A skill is a packaged capability for the agent.

    Skills wrap one or more tools/functions and provide:
    - Manifest metadata (name, version, deps, permissions)
    - Lifecycle hooks (on_load, on_unload)
    - Configuration
    - Multiple related tools grouped together
    """

    def __init__(
        self,
        manifest: SkillManifest,
        tools: Optional[list[FunctionTool]] = None,
        config: Optional[dict[str, Any]] = None,
    ) -> None:
        self.manifest = manifest
        self.tools = tools or []
        self.config = config or {}

    @property
    def name(self) -> str:
        return self.manifest.name

    @property
    def description(self) -> str:
        return self.manifest.description

    @property
    def version(self) -> str:
        return self.manifest.version

    @property
    def author(self) -> str:
        return self.manifest.author

    @property
    def dependencies(self) -> list[str]:
        return self.manifest.dependencies

    @property
    def permissions(self) -> list[str]:
        return self.manifest.permissions

    @property
    def status(self) -> str:
        return self.manifest.status

    def has_permission(self, perm: str) -> bool:
        """Return True if this skill has declared *perm*."""
        return perm in self.manifest.permissions

    def requires_network(self) -> bool:
        return "network" in self.manifest.permissions

    def requires_filesystem(self) -> bool:
        return "filesystem" in self.manifest.permissions

    def requires_shell(self) -> bool:
        return "shell" in self.manifest.permissions

    def required_secrets(self) -> list[str]:
        """Return the list of secret/env-var names this skill needs."""
        return [
            p[len("secrets:"):] for p in self.manifest.permissions
            if p.startswith("secrets:")
        ]

    async def on_load(self) -> None:
        """Called when the skill is loaded. Override for setup logic."""

    async def on_unload(self) -> None:
        """Called when the skill is unloaded. Override for cleanup."""

    def get_tools(self) -> list[FunctionTool]:
        """Return all tools provided by this skill."""
        return self.tools


# ---------------------------------------------------------------------------
# @skill decorator
# ---------------------------------------------------------------------------

def skill(
    name: Optional[str] = None,
    description: Optional[str] = None,
    version: str = "0.1.0",
    author: str = "unknown",
    dependencies: Optional[list[str]] = None,
    permissions: Optional[list[str]] = None,
    tags: Optional[list[str]] = None,
) -> Callable:
    """Decorator to create a Skill from a Python function.

    This is the simplest way to create a skill -- just decorate a function::

        @skill(
            name="weather",
            description="Get weather for a city",
            permissions=["network"],
        )
        def get_weather(city: str) -> str:
            import httpx
            resp = httpx.get(f"https://wttr.in/{city}?format=3")
            return resp.text

    Declare required permissions in the ``permissions`` list.  Valid tokens:

    - ``"network"`` – outbound HTTP/socket connections
    - ``"filesystem"`` – read/write outside sandbox temp dir
    - ``"shell"`` – subprocess spawning
    - ``"secrets:<KEY>"`` – access to a specific env-var/secret

    For multi-tool skills, use the :class:`Skill` class directly.

    Args:
        name: Skill name (defaults to function name).
        description: Skill description (defaults to docstring).
        version: Skill version string.
        author: Skill author.
        dependencies: pip package dependencies (also parsed from
            ``# Requirements:`` header in the skill file).
        permissions: Required permission tokens.
        tags: Categorization tags.

    Returns:
        A :class:`Skill` instance wrapping the decorated function.
    """
    def decorator(func: Callable) -> Skill:
        skill_name = name or func.__name__
        skill_desc = description or func.__doc__ or f"Skill: {skill_name}"

        manifest = SkillManifest(
            name=skill_name,
            description=skill_desc.strip(),
            version=version,
            author=author,
            dependencies=dependencies or [],
            permissions=permissions or [],
            tags=tags or [],
        )

        tool = FunctionTool(
            func=func,
            name=skill_name,
            description=skill_desc.strip(),
            category="skill",
        )

        return Skill(manifest=manifest, tools=[tool])

    return decorator
