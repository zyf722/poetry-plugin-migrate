from __future__ import annotations

from packaging.requirements import InvalidRequirement, Requirement
from poetry.core.packages.dependency import Dependency
from poetry.core.version.requirements import parse_requirement


class UnrepresentableRequirementError(ValueError):
    """Raised when a Poetry dependency cannot be migrated without semantic loss."""


def render_pep508_requirement(
    dependency: Dependency, *, keep_version_brackets: bool
) -> str:
    """Render and validate a Poetry dependency as a PEP 508 requirement.

    Poetry emits legacy parentheses around version specifiers. For registry
    dependencies, Poetry's requirement parser exposes the parsed specifier in
    its original order, which lets us omit those parentheses without editing
    arbitrary requirement text. Direct references and unconstrained
    dependencies are already unaffected by the legacy syntax and are retained
    byte-for-byte.
    """
    raw = dependency.to_pep_508()
    try:
        original = Requirement(raw)
    except InvalidRequirement as error:
        raise UnrepresentableRequirementError(
            f"Poetry generated a requirement that is not valid PEP 508: {raw}"
        ) from error

    candidate = raw
    if not keep_version_brackets and original.url is None and original.specifier:
        try:
            parsed = parse_requirement(raw)
        except ValueError as error:
            raise UnrepresentableRequirementError(
                f"Poetry could not parse its generated requirement: {raw}"
            ) from error

        extras = f"[{','.join(sorted(parsed.extras))}]" if parsed.extras else ""
        marker = f" ; {parsed.marker}" if parsed.marker else ""
        candidate = f"{parsed.name}{extras}{parsed.pretty_constraint}{marker}"

    try:
        rendered = Requirement(candidate)
        round_tripped = Dependency.create_from_pep_508(candidate)
    except (InvalidRequirement, ValueError) as error:
        raise UnrepresentableRequirementError(
            f"Rendered requirement cannot be consumed safely: {candidate}"
        ) from error

    if rendered != original or not _same_pep508_semantics(dependency, round_tripped):
        raise UnrepresentableRequirementError(
            f"Rendered requirement changes dependency semantics: {candidate}"
        )

    return candidate


def _same_pep508_semantics(source: Dependency, target: Dependency) -> bool:
    """Compare every dependency field representable in a PEP 508 string."""
    return (
        source.name == target.name
        and source.constraint == target.constraint
        and source.extras == target.extras
        and source.marker == target.marker
        and source.source_type == target.source_type
        and source.source_url == target.source_url
        and source.source_reference == target.source_reference
        and source.source_resolved_reference == target.source_resolved_reference
        and source.source_subdirectory == target.source_subdirectory
    )
