"""How a symbolic actor ("victim", "attacker") becomes real request headers.

Kept separate from the replay engine: the engine knows how to fire a proven
witness, this knows how a particular target authenticates. Phase 8 ships the
header strategy, which is all the seeded-race target needs. crAPI's signup +
email-OTP + JWT flow is a real piece of work and is deliberately not automated
here — supply tokens via StaticTokenAuth once you have them.
"""

from pydantic import BaseModel


class ActorAuth(BaseModel):
    """Header strategy: one templated header carrying the actor's identity.

    `template` is formatted with the actor name, so {"X-User": "{actor}"}
    sends `X-User: attacker` for the attacker's requests.
    """

    headers: dict[str, str] = {}
    tokens: dict[str, str] = {}
    """actor -> full header value for `token_header` (e.g. a bearer token)."""
    token_header: str = "Authorization"

    def headers_for(self, actor: str) -> dict[str, str]:
        out = {name: value.format(actor=actor) for name, value in self.headers.items()}
        if actor in self.tokens:
            out[self.token_header] = self.tokens[actor]
        return out


class ReplayTarget(BaseModel):
    base_url: str
    auth: ActorAuth
    timeout_s: float = 10.0


# Per-target defaults, by the same target_name the pipeline already uses.
TARGETS: dict[str, ReplayTarget] = {
    "seeded-race": ReplayTarget(
        base_url="http://localhost:8090",
        auth=ActorAuth(headers={"X-User": "{actor}"}),
    ),
    "crapi": ReplayTarget(
        base_url="http://localhost:8888",
        # crAPI needs real JWTs; without them replay reports its 401s honestly
        # rather than pretending the app is vulnerable.
        auth=ActorAuth(headers={}),
    ),
}


def target_for(target_name: str, base_url: str | None = None) -> ReplayTarget | None:
    target = TARGETS.get(target_name)
    if target is None:
        return None
    return target.model_copy(update={"base_url": base_url}) if base_url else target
