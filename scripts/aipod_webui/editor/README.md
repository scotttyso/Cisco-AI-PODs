# YAML editor bundle

The WebUI serves a prebuilt Monaco editor with [monaco-yaml](https://github.com/remcohaszing/monaco-yaml),
which runs the same Red Hat `yaml-language-server` used by the VS Code YAML extension. The built files in
`../static/yaml-editor/` are committed, so running the UI does not need Node.js.

Rebuild only after changing `src/index.js` or the package versions (Node.js 20 or later):

```bash
cd scripts/aipod_webui/editor
npm ci
node build.mjs
```

`node_modules/` is ignored by git. The page adds a `?v=<mtime>` query to the bundle URL, so browsers pick up a
rebuild on the next page load.
