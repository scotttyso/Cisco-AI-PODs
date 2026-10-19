// Build the vendored editor bundle into ../static/yaml-editor/.
import { build } from 'esbuild'
import { rmSync } from 'node:fs'

const outdir = new URL('../static/yaml-editor/', import.meta.url).pathname
rmSync(outdir, { recursive: true, force: true })

const common = { bundle: true, minify: true, legalComments: 'linked', target: 'es2020', logLevel: 'info' }

await build({
  ...common,
  entryPoints: { 'yaml-editor': 'src/index.js' },
  format: 'iife',
  outdir,
  loader: { '.ttf': 'file' }
})

await build({
  ...common,
  entryPoints: {
    'editor.worker': 'monaco-editor/esm/vs/editor/editor.worker.js',
    'yaml.worker': 'monaco-yaml/yaml.worker.js'
  },
  format: 'iife',
  outdir
})
