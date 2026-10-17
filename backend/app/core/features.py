"""Feature flags: coarse, config-driven switches for staged rollout.

Flags read from settings (env), so a deployment can enable parts of the
screening platform without a code change. Keep them coarse and few, and remove
a flag once its feature is permanent.
"""

from dataclasses import asdict, dataclass

from app.core.config import settings

FLAG_NAMES = ("screening", "magic_links", "proctoring_integrity")


@dataclass(frozen=True)
class FeatureFlags:
    screening: bool = False
    magic_links: bool = False
    proctoring_integrity: bool = False

    def is_enabled(self, name: str) -> bool:
        if name not in FLAG_NAMES:
            raise KeyError(f"Unknown feature flag {name!r}. Known: {', '.join(FLAG_NAMES)}")
        return bool(getattr(self, name))

    def as_dict(self) -> dict[str, bool]:
        return asdict(self)


def load_features() -> FeatureFlags:
    return FeatureFlags(
        screening=settings.feature_screening_enabled,
        magic_links=settings.feature_magic_links_enabled,
        proctoring_integrity=settings.feature_proctoring_integrity_enabled,
    )


features = load_features()
