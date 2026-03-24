"""Mobile-specific prompt helpers."""

from __future__ import annotations

_MOBILE_DEVELOPMENT_PROMPT = """\
## Mobile Development

Apply these rules only for React Native or Expo work.

<mobile_app_development>
- Build native-feeling experiences for iOS and Android with Expo and React Native.
- Prefer `StyleSheet`, themed style objects, and normal React Native props for new UI.
- If the runtime exposes `Skill`, load `building-ui` before major Expo UI work. For game-like tasks, load `building-mobile-game` first instead.
- Use `mobile_app_init` when you need to scaffold a new app.
- Add a backend only when the feature needs authentication, persistence, payments, or other server-side logic. If so, use `ask_user_select` before `fullstack_project_init` for database or backend choices.
- Use `restart_mobile_server` for the managed preview workflow when available.
- Build real flows with loading, empty, and error states, plus safe-area and keyboard handling where relevant.
- Use `revenuecat` for in-app subscriptions or paywalls when that tool is available.
- If the task includes app branding and `generate_image` is available, create a custom app icon instead of leaving the default Expo asset in place.
</mobile_app_development>

<mobile_game_development>
- Apply this section only for mobile games or game-like interactive experiences.
- If `Skill` is available, load `building-mobile-game` before other game work.
- Start simple: input, movement, collisions, state, restart or pause, then polish.
- Prefer the lightest rendering and physics approach that satisfies the game.
- Keep game UI separate from gameplay rendering and make success, failure, and restart states fully playable.
</mobile_game_development>
"""


def get_mobile_development_prompt() -> str:
    """Return the mobile development prompt."""
    return _MOBILE_DEVELOPMENT_PROMPT.strip()
