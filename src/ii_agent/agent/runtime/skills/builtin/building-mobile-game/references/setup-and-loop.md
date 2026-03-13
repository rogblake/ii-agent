# Setup And Loop

## Bootstrap

Use the reanimated example for game projects:

```bash
mobile_app_init(project_name="my-game", example="with-reanimated", with_tailwind=False)
bun install react-native-worklets@0.5.1
```

Update `babel.config.js` and keep the worklets plugin last:

```js
module.exports = function (api) {
  api.cache(true);
  return {
    presets: ["babel-preset-expo"],
    plugins: [
      // other plugins
      "react-native-worklets/plugin",
    ],
  };
};
```

Rules:

- Use `react-native-worklets@0.5.1`, not `react-native-worklets-core`.
- Do not add `react-native-reanimated/plugin`.
- If the game also has regular app screens, tabs, modals, or non-game flows, load `building-ui`.

## Library Picker

| Tool | Use it for |
| --- | --- |
| `react-native-game-engine` | Most 2D arcade, runner, flappy, platformer, and puzzle loops |
| `@shopify/react-native-skia` | Custom drawing, particle systems, HUD effects, richer 2D rendering |
| `expo-gl` + `three` | 3D scenes or GL rendering |
| `matter-js` | Only when realistic physics is part of the core mechanic |
| `react-native-gesture-handler` | Touch controls, drag, swipe, pan |
| `zustand` | Score, lives, level, paused state, unlocked content |
| `expo-av` | Audio playback |
| `expo-haptics` | Haptic feedback |
| `@react-native-async-storage/async-storage` | High scores and local progress |

## Build Order

Implement mechanics in this order:

1. Input
2. Movement
3. World bounds or obstacle collision
4. Score, health, or win/lose state
5. Pause and restart
6. Juice: animation, audio, particles, transitions

Do not implement all physics at once. Make one layer correct, then add the next.

## Physics Rules

- Prefer manual physics first:
  - `position += velocity * delta`
  - `velocity += gravity * delta`
- Use a fixed update loop with delta time from the engine. Never assume a fixed frame rate.
- Use AABB rectangle overlap checks first.
- Clamp entities after collision resolution instead of hoping velocity zeroing is enough.
- Keep physics values as floats and round only render positions if visuals shimmer.
- Use explicit grounded and `canJump` flags to avoid double-jump bugs.

Common fixes:

- Falling through floor: clamp to ground after gravity and set grounded.
- Sticking in walls: push the entity out of overlap, then clear the blocking velocity.
- Different behavior across devices: multiply all movement and timers by delta time.

## UI And State

- Keep the game canvas or entity layer separate from overlay UI.
- Implement real pause, resume, restart, failure, and success states.
- Use Reanimated for menu and overlay transitions outside the main game loop.
- Keep score and game state in `zustand` or a similarly lightweight store rather than scattered component state.

## Performance Checks

- Avoid allocating new objects every frame.
- Memoize static entities if they are React components.
- Prefer mutating engine entities inside the loop when the engine model expects it.
- Test on Expo web and at least one mobile target.
- After each major mechanic, verify frame pacing, input latency, and collision behavior before adding polish.
