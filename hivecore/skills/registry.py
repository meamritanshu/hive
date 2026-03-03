"""Skill registry - manages installed and available skills."""

from __future__ import annotations

import logging
from typing import Optional

from hivecore.skills.base import Skill, SkillManifest

logger = logging.getLogger(__name__)


class SkillRegistry:
    """Registry for managing installed skills.

    Provides lookup, listing, and management of skills.
    Works with the SkillLoader for filesystem-based skills
    and supports programmatic registration.
    """

    def __init__(self) -> None:
        self._skills: dict[str, Skill] = {}

    def register(self, skill: Skill) -> None:
        """Register a skill.

        Args:
            skill: The skill to register.
        """
        self._skills[skill.name] = skill
        logger.debug("Registered skill: %s v%s", skill.name, skill.version)

    def get(self, name: str) -> Optional[Skill]:
        """Get a skill by name."""
        return self._skills.get(name)

    def list_all(self) -> list[Skill]:
        """List all registered skills."""
        return list(self._skills.values())

    def unregister(self, name: str) -> bool:
        """Remove a skill from the registry."""
        if name in self._skills:
            del self._skills[name]
            return True
        return False

    def install(self, source: str) -> None:
        """Install a skill from a source (path, URL, or registry name).

        This is a placeholder for the full marketplace integration.

        Args:
            source: Skill source identifier.
        """
        # TODO: Implement full skill installation from marketplace
        logger.info("Skill installation requested: %s (not yet implemented)", source)
        raise NotImplementedError(
            "Skill marketplace installation is not yet implemented. "
            "For now, place skill files in ~/.hivecore/skills/"
        )

    def list_names(self) -> list[str]:
        """List all registered skill names."""
        return sorted(self._skills.keys())

    def __len__(self) -> int:
        return len(self._skills)

    def __contains__(self, name: str) -> bool:
        return name in self._skills
