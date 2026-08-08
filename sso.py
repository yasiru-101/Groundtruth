class SSOProvider:
    """Interface for single sign-on providers."""

    def verify(self, token: str) -> bool:
        raise NotImplementedError
