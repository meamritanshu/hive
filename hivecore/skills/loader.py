"""Skill loader - auto-discovery and hot-reload of skills.

Scans the skill directory for Python files and skill.toml manifests,
loads them as Skills, and registers their tools with the agent.

Security
--------
On load the loader:
1. Parses any ``# Requirements: ...`` header and installs missing packages
   into an isolated per-skill virtual environment.
2. Validates that all declared permissions are recognised tokens.
3. Cross-checks declared permissions against the ``allowed_permissions``
   list in a co-located ``<skill_name>.toml`` allow-list file (if present).
   Only permissions listed in the allow-list are granted; any undeclared
   permission causes the skill to be rejected with an error log.
"""

from __future__ import annotations

import importlib.util
import logging
import sys
from pathlib import Path
from typing import Any, Optional

from hivecore.skills.base import (
    Skill,
    SkillManifest,
    ensure_requirements,
    parse_requirements_header,
)

logger = logging.getLogger(__name__)

# Permissions granted to all skills by default (empty = deny-by-default).
# Override globally via SkillsSettings or per-skill via <name>.toml.
DEFAULT_ALLOWED_PERMISSIONS: frozenset[str] = frozenset()


class SkillLoader:
    """Discovers and loads skills from the filesystem.

    Scans a directory for:
    1. Python files with @skill decorated functions
    2. Directories with skill.toml manifests
    3. Single-file skills (name.py)

    Supports hot-reload via watchdog file watcher integration.

    Permission enforcement
    ----------------------
    Each skill is checked against an optional ``<skill_name>.toml``
    allow-list file in the same directory::

        # ~/.hivecore/skills/my_skill.toml
        [permissions]
        allowed = ["network", "secrets:OPENAI_API_KEY"]

    If no allow-list file exists, the *allowed_permissions* argument
    passed to :class:`SkillLoader` is used as the global default.
    Skills that declare permissions not in the allow-list are skipped.
    """

    def __init__(
        self,
        skill_dirs: Optional[list[Path]] = None,
        allowed_permissions: Optional[frozenset[str]] = None,
        install_requirements: bool = True,
    ) -> None:
        self._skill_dirs = skill_dirs or []
        self._allowed_permissions = (
            allowed_permissions
            if allowed_permissions is not None
            else DEFAULT_ALLOWED_PERMISSIONS
        )
        self._install_requirements = install_requirements
        self._loaded_skills: dict[str, Skill] = {}

    def add_directory(self, path: Path) -> None:
        """Add a skill directory to scan."""
        if path not in self._skill_dirs:
            self._skill_dirs.append(path)

    async def load_all(self) -> list[Skill]:
        """Scan all skill directories and load all skills.

        Returns:
            List of loaded Skill instances.
        """
        skills = []

        for skill_dir in self._skill_dirs:
            if not skill_dir.exists():
                logger.debug("Skill directory does not exist: %s", skill_dir)
                continue

            # Load single-file skills (*.py)
            for py_file in skill_dir.glob("*.py"):
                if py_file.name.startswith("_"):
                    continue
                try:
                    loaded = await self._load_file_skill(py_file)
                    if loaded:
                        skills.append(loaded)
                        self._loaded_skills[loaded.name] = loaded
                        logger.info(
                            "Loaded skill: %s (from %s)", loaded.name, py_file.name
                        )
                except Exception as e:
                    logger.error("Failed to load skill from %s: %s", py_file, e)

            # Load directory-based skills (dir with skill.toml)
            for sub_dir in skill_dir.iterdir():
                if sub_dir.is_dir() and (sub_dir / "skill.toml").exists():
                    try:
                        loaded = await self._load_dir_skill(sub_dir)
                        if loaded:
                            skills.append(loaded)
                            self._loaded_skills[loaded.name] = loaded
                            logger.info(
                                "Loaded skill: %s (from %s/)", loaded.name, sub_dir.name
                            )
                    except Exception as e:
                        logger.error("Failed to load skill from %s: %s", sub_dir, e)

        logger.info(
            "Loaded %d skills from %d directories", len(skills), len(self._skill_dirs)
        )
        return skills

    async def _load_file_skill(self, path: Path) -> Optional[Skill]:
        """Load a skill from a single Python file.

        Steps:
        1. Read source; parse ``# Requirements:`` header.
        2. Install missing requirements into the skill's venv.
        3. Import the module and find the Skill instance.
        4. Enforce permission allow-list.
        """
        # --- Step 1: read source and parse requirements header ---
        try:
            source = path.read_text(encoding="utf-8")
        except OSError as e:
            logger.error("Cannot read skill file %s: %s", path, e)
            return None

        requirements = parse_requirements_header(source)

        # --- Step 2: install requirements ---
        if requirements and self._install_requirements:
            try:
                ensure_requirements(requirements, skill_name=path.stem)
            except RuntimeError as e:
                logger.error(
                    "Skipping skill '%s' — requirement installation failed: %s",
                    path.stem,
                    e,
                )
                return None

        # --- Step 3: import the module ---
        module_name = f"hivecore_skill_{path.stem}"
        spec = importlib.util.spec_from_file_location(module_name, path)
        if spec is None or spec.loader is None:
            return None

        module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = module

        try:
            spec.loader.exec_module(module)
        except Exception as e:
            logger.error("Error executing skill module %s: %s", path, e)
            del sys.modules[module_name]
            return None

        # Find Skill instances or factories
        found: Optional[Skill] = None
        for attr_name in dir(module):
            attr = getattr(module, attr_name)
            if isinstance(attr, Skill):
                found = attr
                break
            if (
                isinstance(attr, type)
                and issubclass(attr, Skill)
                and attr is not Skill
            ):
                found = attr()
                break

        if found is None and hasattr(module, "create_skill"):
            result = module.create_skill()
            if isinstance(result, Skill):
                found = result

        if found is None:
            logger.debug("No skill found in %s", path)
            return None

        # Merge requirements from header into manifest dependencies
        for req in requirements:
            if req not in found.manifest.dependencies:
                found.manifest.dependencies.append(req)

        # --- Step 4: permission enforcement ---
        allow_list = self._load_allowlist(path.parent, found.name)
        if not self._check_permissions(found, allow_list):
            return None

        return found

    async def _load_dir_skill(self, path: Path) -> Optional[Skill]:
        """Load a skill from a directory with a skill.toml manifest."""
        manifest_path = path / "skill.toml"
        manifest = self._load_manifest(manifest_path)
        if manifest is None:
            return None

        # Look for the main module
        main_file = path / "__init__.py"
        if not main_file.exists():
            main_file = path / "main.py"
        if not main_file.exists():
            logger.warning(
                "No __init__.py or main.py in skill directory: %s", path
            )
            return None

        # Parse requirements from the main file
        try:
            source = main_file.read_text(encoding="utf-8")
            requirements = parse_requirements_header(source)
            if requirements and self._install_requirements:
                ensure_requirements(requirements, skill_name=path.name)
        except (OSError, RuntimeError) as e:
            logger.error(
                "Skipping dir skill '%s' — requirements failed: %s", path.name, e
            )
            return None

        # Load the module
        module_name = f"hivecore_skill_{path.name}"
        spec = importlib.util.spec_from_file_location(module_name, main_file)
        if spec is None or spec.loader is None:
            return None

        module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = module

        try:
            spec.loader.exec_module(module)
        except Exception as e:
            logger.error("Error executing skill module %s: %s", main_file, e)
            del sys.modules[module_name]
            return None

        # Find the Skill or create one from the manifest
        found: Optional[Skill] = None
        for attr_name in dir(module):
            attr = getattr(module, attr_name)
            if isinstance(attr, Skill):
                attr.manifest = manifest  # Override with file manifest
                found = attr
                break

        if found is None:
            return None

        # Permission check (allow-list lives one level up from the skill dir)
        allow_list = self._load_allowlist(path.parent, found.name)
        if not self._check_permissions(found, allow_list):
            return None

        return found

    def _load_allowlist(self, directory: Path, skill_name: str) -> Optional[frozenset[str]]:
        """Load per-skill permission allow-list from ``<skill_name>.toml``.

        Returns None if no allow-list file exists (falls back to global default).
        """
        toml_path = directory / f"{skill_name}.toml"
        if not toml_path.exists():
            return None

        try:
            if sys.version_info >= (3, 11):
                import tomllib
            else:
                import tomli as tomllib

            with open(toml_path, "rb") as f:
                data = tomllib.load(f)

            perms = data.get("permissions", {}).get("allowed", [])
            return frozenset(perms)
        except Exception as e:
            logger.warning("Failed to parse allow-list %s: %s", toml_path, e)
            return None

    def _check_permissions(
        self, skill: Skill, allow_list: Optional[frozenset[str]]
    ) -> bool:
        """Return True if all of the skill's declared permissions are allowed.

        Args:
            skill: The skill to check.
            allow_list: Per-skill allow-list, or None to use the global default.

        Returns:
            True if all permissions are granted; False (with error log) otherwise.
        """
        effective_allowed = (
            allow_list if allow_list is not None else self._allowed_permissions
        )

        denied = [
            p for p in skill.permissions if p not in effective_allowed
        ]

        if denied:
            logger.error(
                "Skill '%s' requests permissions not in its allow-list: %s — "
                "create ~/.hivecore/skills/%s.toml with "
                "[permissions] allowed = %r to grant them.",
                skill.name,
                denied,
                skill.name,
                list(skill.permissions),
            )
            return False

        return True

    def _load_manifest(self, path: Path) -> Optional[SkillManifest]:
        """Load a skill.toml manifest file."""
        if not path.exists():
            return None

        try:
            if sys.version_info >= (3, 11):
                import tomllib
            else:
                import tomli as tomllib

            with open(path, "rb") as f:
                data = tomllib.load(f)

            return SkillManifest(
                name=data.get("name", path.parent.name),
                description=data.get("description", ""),
                version=data.get("version", "0.1.0"),
                author=data.get("author", "unknown"),
                dependencies=data.get("dependencies", []),
                permissions=data.get("permissions", []),
                tags=data.get("tags", []),
            )
        except Exception as e:
            logger.error("Failed to parse skill manifest %s: %s", path, e)
            return None

    async def reload_skill(self, name: str) -> Optional[Skill]:
        """Reload a specific skill by name.

        Args:
            name: The skill name to reload.

        Returns:
            The reloaded Skill, or None if not found.
        """
        if name in self._loaded_skills:
            old_skill = self._loaded_skills[name]
            await old_skill.on_unload()

        # Re-scan and find the skill
        for skill_dir in self._skill_dirs:
            for py_file in skill_dir.glob("*.py"):
                loaded = await self._load_file_skill(py_file)
                if loaded and loaded.name == name:
                    self._loaded_skills[name] = loaded
                    await loaded.on_load()
                    return loaded

        return None

    def get_loaded_skills(self) -> dict[str, Skill]:
        """Get all currently loaded skills."""
        return self._loaded_skills.copy()

    async def unload_all(self) -> None:
        """Unload all skills."""
        for s in self._loaded_skills.values():
            try:
                await s.on_unload()
            except Exception as e:
                logger.warning("Error unloading skill %s: %s", s.name, e)
        self._loaded_skills.clear()
