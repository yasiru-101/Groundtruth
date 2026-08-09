class SSOProvider:
    """Interface for single sign-on providers."""

    def verify(self, token: str) -> bool:
        raise NotImplementedError


REGISTRY: dict[str, SSOProvider] = {}


def register(name: str, provider: SSOProvider) -> None:
    REGISTRY[name] = provider
