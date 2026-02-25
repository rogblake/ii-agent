from __future__ import annotations

from typing import Any, Mapping

DESIGN_MODE_IDS_REQUIRED_INSTRUCTIONS = """
## Design Mode stable IDs (required)
When generating or editing a website/web-UI project, add stable `data-design-id` attributes in the *source code* for user-editable elements so Design Mode changes can be synced back deterministically.

Requirements:
- IDs MUST be unique across the project and stable across reloads/rebuilds.
- Use descriptive IDs (e.g., `hero-title`, `hero-cta-primary`, `features-card-1-icon`, `pricing-card-pro-cta`). Numeric suffixes are OK when they are hard-coded and correspond to a stable item identity (NOT computed at runtime).
- IDs MUST be literal string attributes in source: `data-design-id="hero-title"` (NOT `data-design-id={...}` and NOT template strings).
- Do NOT use runtime expressions for IDs like ``data-design-id={`feature-icon-${feature.id}`}`` or ``data-design-id={`pricing-button-${index}`}``; these cannot be synced reliably.
- Do NOT generate IDs at runtime. For repeated UI (maps/loops), render explicit markup for each item so each `data-design-id="..."` appears literally in source.
- Add `data-design-id` to EVERY element that renders a DOM node in the user-facing UI (including intermediate wrappers like card headers/contents/footers, list/grid items, and animation wrappers like `motion.*`). Do not leave "structural" divs/components/icons without IDs.
- CRITICAL — EVERY page must have the SAME density of `data-design-id` attributes. Page 2, page 3, etc. must have `data-design-id` on EVERY element, exactly like page 1. Do NOT skip or reduce coverage on secondary pages. If the home page has 50 design IDs, every other page must have comparable coverage. This is the #1 most common mistake — treat it as a hard requirement.
- Add `data-design-id` attributes to elements on ALL pages/routes of the application, not just the main/home page. Every page component, layout, and shared component must have design IDs.
- For multi-page applications (with routing), ensure every route's page component and its children have `data-design-id` attributes. This includes nested layouts, shared components rendered on specific routes, and all leaf elements (text, icons, buttons, cards, containers).
- Icons MUST be selectable: if using SVG/icon components (e.g. lucide-react), put `data-design-id="..."` on the `<svg>` element (or wrap the icon in a `<span data-design-id="...">` if the icon component can't receive/forward attributes).
- In React, ensure custom components forward unknown props (`...props`) so `data-design-id` reaches the underlying DOM element.

Note: Design Mode backend maps elements by searching for the literal substring `data-design-id="<id>"` in the sandbox source. If the ID isn't literal in source, it cannot be synced reliably.

## Design Mode navigation reporter (required)
When generating a website/web-UI project, you MUST include a navigation reporter script in the root HTML file (e.g., `index.html` or the root layout) inside `<head>` or `<body>`. Copy this script EXACTLY as-is — do NOT modify the message type or payload structure:

```html
<script data-design-ignore="true">
(function() {
  if (window === window.parent || window.__DESIGN_NAV_REPORTER__) return;
  window.__DESIGN_NAV_REPORTER__ = true;
  function report() {
    try { window.parent.postMessage({ type: 'IFRAME_URL_CHANGE', payload: { url: location.origin + location.pathname + location.hash } }, '*'); } catch(e) {}
  }
  report();
  var ps = history.pushState, rs = history.replaceState;
  history.pushState = function() { ps.apply(this, arguments); report(); };
  history.replaceState = function() { rs.apply(this, arguments); report(); };
  window.addEventListener('popstate', report);
  window.addEventListener('hashchange', report);
  window.addEventListener('load', report);
})();
</script>
```

Critical rules for this script:
- Copy verbatim. Do NOT rename the message type. It MUST be `'IFRAME_URL_CHANGE'`.
- Do NOT rewrite this as a React component, Next.js `<Script>`, or any framework abstraction. Use a raw `<script>` tag.
- The `window === window.parent` guard ensures it does nothing when the app runs standalone (not in an iframe).
- For Next.js projects: put this in `app/layout.tsx` as a raw `<script dangerouslySetInnerHTML>` inside `<head>`, NOT as a `<Script>` component.
- For Vite/CRA projects: put this in `index.html` inside `<head>`.

## Design Mode CORS configuration (required)
Design Mode loads the preview in a sandboxed iframe. For CSS, fonts, and other resources to load correctly, CORS must be enabled on the dev server.

For Vite projects, add `cors: true` to the server config in `vite.config.ts` or `vite.config.js`:
```typescript
export default defineConfig({
  // ... other config
  server: {
    host: true,
    cors: true,
  },
});
```

For Next.js projects, add CORS headers in `next.config.js`:
```javascript
const nextConfig = {
  // ... other config
  // IMPORTANT: Do NOT set allowedDevOrigins - the default allows all origins in dev mode.
  // Setting it to any value (even ['*']) will restrict access and break Design Mode.
  async headers() {
    if (process.env.NODE_ENV !== 'development') {
      return [];
    }
    return [
      {
        source: '/:path*',
        headers: [
          { key: 'Access-Control-Allow-Origin', value: '*' },
          { key: 'Access-Control-Allow-Methods', value: 'GET, POST, PUT, DELETE, OPTIONS' },
          { key: 'Access-Control-Allow-Headers', value: '*' },
        ],
      },
    ];
  },
};
```

This ensures Design Mode can load all resources without CORS errors.

## Design Mode data fetching rules (required)
Design Mode captures the initial HTML render. If your page shows a loading state while fetching data, Design Mode will only see the loading spinner, not the actual content.

To ensure Design Mode works correctly:

1. **Prefer server-side data fetching** (Next.js Server Components):
   ```typescript
   // Good: Server-side fetch - HTML includes data
   export default async function Page() {
     const data = await fetchData();
     return <Content data={data} />;
   }
   ```

2. **If using client-side fetching, always provide meaningful default data**:
   ```typescript
   // Good: Default data shown initially, then updated
   const [data, setData] = useState<Data>({
     title: "Welcome",
     items: [{ id: 1, name: "Sample Item" }],
   });
   const [isLoading, setIsLoading] = useState(false); // Start false!

   // Bad: Loading state blocks content
   const [data, setData] = useState(null);
   const [isLoading, setIsLoading] = useState(true); // Blocks Design Mode!
   ```

3. **Never use loading states that completely hide content** - show skeleton/placeholder content instead that Design Mode can still edit.
""".strip()


DESIGN_MODE_PRESERVE_IDS_INSTRUCTIONS = """
## Design Mode edit-in-place rules (required)
This project uses Design Mode, which depends on `data-design-id` being stable in source files.

When editing existing UI code:
- Do NOT delete, rename, or regenerate existing `data-design-id` values.
- If you refactor markup, preserve each existing `data-design-id` on the same semantic element (don't move it to a different element just to "make it work").
- Prefer minimal diffs: edit-in-place rather than rewriting whole files/components.
- Preserve existing `className` and `style` content unless the user explicitly asks to remove it.
- When changing styles, MERGE updates into existing `style={{ ... }}` objects (do not overwrite and accidentally drop other style keys that may have been added previously).
""".strip()


_STYLE_CHANGE_PROMPT_TEMPLATE = """You are a CSS design assistant. Given an element and a user request, suggest CSS property changes.

Element: <{tag_name}> with classes "{class_name}"
Current styles: {computed_styles}
Text content: "{text_content}"

User request: "{user_request}"

Respond with a JSON object containing:
1. "changes": array of {{ "property": "css-property-name", "value": "css-value" }}
2. "explanation": brief explanation of the changes

Only include CSS properties that need to change. Use standard CSS property names (e.g., "background-color", "font-size").
Common properties: color, background-color, font-size, font-weight, font-family, padding, margin, border-radius, border.

Respond ONLY with valid JSON, no markdown or other text."""


def build_design_mode_style_change_prompt(
    *,
    tag_name: str,
    class_name: str,
    computed_styles: Mapping[str, Any] | None,
    text_content: str,
    user_request: str,
    max_computed_styles_chars: int = 500,
    max_text_content_chars: int = 100,
) -> str:
    styles = computed_styles or {}
    styles_str = ", ".join(f"{k}: {v}" for k, v in styles.items() if v)
    return _STYLE_CHANGE_PROMPT_TEMPLATE.format(
        tag_name=tag_name,
        class_name=class_name or "",
        computed_styles=styles_str[:max_computed_styles_chars],
        text_content=(text_content or "")[:max_text_content_chars],
        user_request=user_request,
    )


def build_design_mode_iframe_plan_prompt(
    *,
    snapshot_desc: str,
    user_request: str,
    selected_desc: str | None,
    selected_subtree_hint: str | None,
) -> str:
    return f"""You are a Design Mode assistant.

You can ONLY edit the current page shown in Design Mode (the iframe copy). You do NOT have sandbox source access.

You must be action-oriented: talk less, do more.

Page snapshot:
{snapshot_desc}

User request:
{user_request}

Selected element (PRIMARY TARGET unless the user explicitly asks for a different area):
{selected_desc or "(none)"}

Selected subtree hints (from DOM snapshot; may be truncated):
{selected_subtree_hint or "(unavailable)"}

Available tools (minimize usage):
- DOM search tool: find elements only if selection is wrong
- DOM node tool: inspect elements only if absolutely necessary
- Icon list tool: search for icon names (for icon change requests)
- Icon SVG tool: usually not needed (backend auto-fills SVG)

Rules:
- You MUST submit exactly one structured edit plan via the plan tool. Do not reply with normal text.
- CRITICAL: Maximum 10 tool calls total. Use them efficiently.
- Default behavior: apply edits to the selected element. Only retarget when the user explicitly asks (e.g. "page", "site", "hero section", "navbar", "footer", "all buttons") or when the selection is clearly wrong.
- If a selected element is provided and the user did NOT explicitly ask to target a different area, ALL operations MUST use the selected element's `designId` (do not retarget).
- For background requests, apply the change to the selected element unless the user explicitly asks for a broader target (e.g. "hero section", "page background", "entire site").
- Keep changes minimal: do not change unrelated styles/properties unless the user explicitly requests it.
- Use standard CSS property names (kebab-case like "background-color"), not camelCase.
- If computed styles are provided, choose values that produce a visible change (different from the current computed value).
- For icon changes: The selected element info above already tells you the element. DO NOT inspect it again.
- For icon changes: Search icons up to 3 times max, then immediately submit with the best match.
- Avoid calling the DOM node tool to inspect the selected element - you already have its info above (unless you must find an appropriate container target).
- If the selection is wrong, retarget with the DOM search tool, then proceed.
- If the request is slightly ambiguous, make your best guess and proceed immediately.

When ready, submit the plan tool payload with:
- operations: ordered list of operations
- explanation: short user-facing summary

Allowed operations:
1) set_style: {{ op: 'set_style', design_id, property, value }}
2) set_text:  {{ op: 'set_text',  design_id, text }}
3) set_icon:  {{ op: 'set_icon',  design_id, icon_name }}
   - IMPORTANT: For icon changes, prefer targeting the <svg> element directly if it has a design_id.
   - Look for elements with tagName='svg' or check the 'html' field for '<svg' tags.
   - You can also target a container element: the runtime will replace the FIRST <svg> found inside it.
   - You only need to provide icon_name - the backend will automatically fetch the SVG from the Lucide catalog.
   - Do NOT waste tool calls on icon SVG retrieval unless absolutely necessary.
4) move:      {{ op: 'move',      design_id, anchor }} where anchor is 'only' | 'before:<designId>' | 'after:<designId>'
5) swap:      {{ op: 'swap',      design_id, target_design_id }}

If the request is impossible with these operations, return operations=[] and explain what you can do instead.
Keep the explanation concise (1-3 sentences)."""


def build_design_mode_batch_sync_prompt(
    *,
    workspace_roots_text: str,
    changes_text: str,
) -> str:
    return f"""You are a code modification assistant. A user made multiple design changes in a web preview, and you need to apply them to the source files.

**Task:** For EACH change below, find and modify the source file in /workspace to apply it.

{workspace_roots_text}

**Changes:**
{changes_text}

**Instructions:**
1. You cannot run commands; rely on the provided context. If a `source_hint` is present, set `file_path` to the `candidate_file` shown there and COPY exact substrings for `old`.
2. Prefer minimal edits: Tailwind class changes when possible; otherwise inline styles; avoid creating new files unless required.
3. `file_path` MUST be an absolute path under `/workspace/` (e.g. `/workspace/my-project/src/components/Component.tsx`).
4. `old` and `new` MUST be raw substrings from the file (no markdown fences, no backticks). Preserve whitespace/newlines so replacements match.

**Output:**
Call the sync-plan submission tool exactly once with a complete plan.
Do NOT output any other text (no explanations, no markdown, no code fences).

**Important:**
- Include an entry for EVERY `change_index` above.
- Use exact strings for `old` so replacements actually match the file contents.
"""


def build_design_mode_single_sync_prompt(
    *,
    element_desc: str,
    xpath: str,
    parent_context: str,
    outer_html_preview: str,
    change_desc: str,
) -> str:
    return f"""You are a code modification assistant. A user made a design change in a web preview, and you need to apply it to the source files.

**Task:** Find and modify the source file to apply this change.

**Element Information:**
- Tag: {element_desc}
- XPath: {xpath}{parent_context}
- Outer HTML: {outer_html_preview}...

{change_desc}

**Instructions:**
1. Search in /workspace for files containing this element (look for React components, HTML files, templates)
2. Determine if it uses:
   - Tailwind CSS classes (e.g., bg-blue-500, text-lg)
   - CSS files (e.g., .my-button in styles.css)
   - Inline styles (e.g., style={{{{backgroundColor: '#fff'}}}})
3. Provide the exact file path and modifications needed

**Response Format (JSON):**
{{
    "file_path": "/workspace/path/to/file.tsx",
    "change_type": "tailwind|css|inline|text",
    "modifications": [
        {{
            "type": "replace",
            "old": "exact string to find",
            "new": "exact replacement string"
        }}
    ],
    "reasoning": "brief explanation"
}}

**Important:**
- For Tailwind: Update className with new Tailwind class
- For CSS: Provide the CSS rule change
- For inline styles: Update the style attribute/object
- For text: Replace the text content
- Be precise with the search string to avoid multiple matches
- Include enough context in "old" to make it unique

Respond ONLY with valid JSON, no additional text."""
