// Monaco YAML editor for the Cisco AI PODs Automation UI.
// monaco-yaml runs Red Hat's yaml-language-server in a web worker, giving the
// same JSON-schema validation, hover, and completion as VS Code's YAML extension.
import * as monaco from 'monaco-editor/esm/vs/editor/edcore.main.js'
import 'monaco-editor/esm/vs/basic-languages/yaml/yaml.contribution.js'
import { configureMonacoYaml } from 'monaco-yaml'

const base = new URL('.', document.currentScript ? document.currentScript.src : location.href)

globalThis.MonacoEnvironment = {
  getWorker (_moduleId, label) {
    const name = label === 'yaml' ? 'yaml.worker.js' : 'editor.worker.js'
    return new Worker(new URL(name, base))
  }
}

const schemas = new Map()
const editors = new Map()
const yaml = configureMonacoYaml(monaco, {
  enableSchemaRequest: true,
  hover: true,
  completion: true,
  validate: true,
  format: true,
  schemas: []
})

function refreshSchemas () {
  yaml.update({
    enableSchemaRequest: true,
    hover: true,
    completion: true,
    validate: true,
    format: true,
    schemas: [...schemas.values()]
  })
}

function applyTheme () {
  monaco.editor.setTheme(document.body.classList.contains('body--dark') ? 'vs-dark' : 'vs')
}

function onBody (callback) {
  if (document.body) callback()
  else document.addEventListener('DOMContentLoaded', callback, { once: true })
}

onBody(() => new MutationObserver(applyTheme).observe(document.body, { attributes: true, attributeFilter: ['class'] }))

function whenPresent (id, callback) {
  if (!document.body) return onBody(() => whenPresent(id, callback))
  const element = document.getElementById(id)
  if (element) return callback(element)
  const observer = new MutationObserver(() => {
    const found = document.getElementById(id)
    if (found) {
      observer.disconnect()
      callback(found)
    }
  })
  observer.observe(document.body, { childList: true, subtree: true })
}

const MODELINE = /^(\s*#\s*yaml-language-server:\s*\$schema=)(\S+)/m

// Example files may carry workstation-specific schema modelines, which would
// override the served schema. Show the served schema while editing and put the
// original modeline back when the value is read.
function toEditor (entry, text) {
  const match = MODELINE.exec(text || '')
  entry.modeline = match ? match[2] : null
  if (!match || !entry.schemaHref) return text
  return text.replace(MODELINE, `$1${entry.schemaHref}`)
}

function fromEditor (entry, text) {
  if (!entry.modeline || !entry.schemaHref) return text
  return text.replace(MODELINE, (line, prefix, target) => target === entry.schemaHref ? prefix + entry.modeline : line)
}

function create (id, value, options = {}) {
  const entry = { value: '', editor: null, model: null, markers: [], modeline: null, schemaHref: null }
  editors.set(id, entry)
  const uri = monaco.Uri.parse(`file:///${id}.yaml`)
  if (options.schemaUri) {
    entry.schemaHref = new URL(options.schemaUri, location.origin).href
    schemas.set(id, { uri: entry.schemaHref, fileMatch: [uri.toString()] })
    refreshSchemas()
  }
  entry.value = toEditor(entry, value)
  whenPresent(id, (element) => {
    if (entry.editor) return
    entry.model = monaco.editor.getModel(uri) || monaco.editor.createModel(entry.value, 'yaml', uri)
    entry.model.setValue(entry.value)
    applyTheme()
    entry.editor = monaco.editor.create(element, {
      model: entry.model,
      automaticLayout: true,
      readOnly: Boolean(options.readOnly),
      minimap: { enabled: false },
      tabSize: 2,
      insertSpaces: true,
      fontSize: 13,
      scrollBeyondLastLine: false,
      // Hovers and suggestions render outside the clipped editor box, so help on the first lines stays visible.
      fixedOverflowWidgets: true,
      renderWhitespace: 'boundary',
      quickSuggestions: { other: true, comments: false, strings: true }
    })
    monaco.editor.onDidChangeMarkers((uris) => {
      if (uris.some((changed) => changed.toString() === uri.toString())) {
        entry.markers = monaco.editor.getModelMarkers({ resource: uri })
      }
    })
  })
}

function getValue (id) {
  const entry = editors.get(id)
  if (!entry) return null
  return fromEditor(entry, entry.model ? entry.model.getValue() : entry.value)
}

function setValue (id, value) {
  const entry = editors.get(id)
  if (!entry) return
  entry.value = toEditor(entry, value)
  if (entry.model) entry.model.setValue(entry.value)
}

function problems (id) {
  const entry = editors.get(id)
  if (!entry) return []
  return entry.markers
    .filter((marker) => marker.severity >= monaco.MarkerSeverity.Warning)
    .map((marker) => ({ line: marker.startLineNumber, column: marker.startColumn, message: marker.message, severity: marker.severity }))
}

function dispose (id) {
  const entry = editors.get(id)
  if (!entry) return
  if (entry.editor) entry.editor.dispose()
  if (entry.model) entry.model.dispose()
  editors.delete(id)
  if (schemas.delete(id)) refreshSchemas()
}

globalThis.aipodYamlEditor = { create, getValue, setValue, problems, dispose }
