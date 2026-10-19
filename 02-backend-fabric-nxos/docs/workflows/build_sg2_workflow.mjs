// Chapter-figure generator only: no device access, automation execution, or chapter writes.
// Usage: node build_sg2_workflow.mjs --source <MOP.md> --out <directory>
//          --modules <node_modules> --chrome <Chrome executable>
import fs from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';
import { createRequire } from 'node:module';
import assert from 'node:assert/strict';
import os from 'node:os';

const args = Object.fromEntries(Array.from({length: (process.argv.length - 2) / 2}, (_, i) =>
  [process.argv[2 + i * 2], process.argv[3 + i * 2]]));
for (const key of ['--source', '--out', '--modules', '--chrome']) assert(args[key], `Missing ${key}`);
const source = path.resolve(args['--source']);
const out = path.resolve(args['--out']);
// Outputs may live only in this chapter's workflow directory or a temporary
// staging directory. Never write chapter text, Word documents, or docs/build/.
const inside = (parent, child) => child === parent || child.startsWith(parent + path.sep);
const realDestination = target => {
  if (fs.existsSync(target)) return fs.realpathSync(target);
  return path.join(realDestination(path.dirname(target)), path.basename(target));
};
const realOut = realDestination(out);
const chapterDirectory = path.dirname(fs.realpathSync(source));
const temporaryRoots = [os.tmpdir(), ...(fs.existsSync('/tmp') ? ['/tmp'] : [])].map(p => fs.realpathSync(p));
assert(!realOut.split(path.sep).some((part, i, parts) => part === 'docs' && parts[i + 1] === 'build'),
  'Workflow generator must not write docs/build/');
assert(realOut === realDestination(path.join(chapterDirectory, 'workflows')) || temporaryRoots.some(p => inside(p, realOut)),
  'Output must be the chapter workflows directory or temporary staging');
const require = createRequire(path.join(path.resolve(args['--modules']), 'package.json'));
const { chromium } = require('playwright');
const sha256 = bytes => crypto.createHash('sha256').update(bytes).digest('hex');
const sourceBytes = fs.readFileSync(source);
const sourceText = sourceBytes.toString('utf8');
const sourceLines = sourceText.split('\n');
const reference = text => {
  const index = sourceLines.findIndex(line => line.includes(text));
  assert(index >= 0, `Source evidence missing: ${text}`);
  return { path: source, line: index + 1, text: sourceLines[index] };
};
const expectedProcedures = [
  'Create the Backend Fabric Using the Nexus Dashboard AI Template',
  'Discover and Add Spine and Leaf Switches to the Backend Fabric',
  'Configure Switch Roles and Deploy Fabric',
  'Upgrade Backend Switches to target release using Nexus Dashboard',
  '(Optional) Configure Custom AI QoS Policies',
  '(Optional) Enable Bidirectional Forwarding Detection on the Underlay',
  'Verify Backend Fabric Health, Connectivity, and BGP EVPN Adjacencies',
];
const procedureEvidence = expectedProcedures.map((title, i) => reference(`### Procedure ${i + 1}. ${title}`));
assert(procedureEvidence.every((p, i) => i === 0 || p.line > procedureEvidence[i - 1].line));
const prerequisites = reference('## Assumptions and Prerequisites');
const dnsNtpAssumption = reference('DNS and NTP services are operational and reachable from the switch management interfaces.');
const breakout = reference('Configure 2×400G breakout on switches');
const upgradeDecision = reference('If an upgrade is required,');
const reload = reference('adding switches triggers a greenfield reload');
const bfdVerification = reference('If BFD was enabled in the optional BFD procedure');

// Match the existing ND/C880 figure scale: 100 units/in at 6in, 7.4pt body.
const W = 600, H = 338, BOX_W = 113, BOX_H = 60.16;
const FONT = 10.28, HEADER_FONT = 9.46, LINE_H = 12.54;
const C = { blue: '#0A60FF', ink: '#07182D', line: '#525E6C', border: '#B4B9C0',
  tint: '#EDF3FE', amber: '#E07B00', amberTint: '#FDF3E7', white: '#FFFFFF' };
const FONT_FAMILY = 'system-ui, -apple-system, Segoe UI, sans-serif';
const esc = value => String(value).replaceAll('&', '&amp;').replaceAll('<', '&lt;').replaceAll('>', '&gt;').replaceAll('"', '&quot;');
const nodes = [
  { id: 'start', x: 56, y: 41.5, w: 93, h: 29, kind: 'terminal', lines: ['Start'] },
  { id: 'prerequisites', x: 177, y: 16, header: 'Prerequisites', lines: ['ND cluster,', 'OOB management,', 'cabling, DNS/NTP'], evidence: prerequisites },
  { id: 'breakout', x: 308, y: 16, header: 'Deploy prerequisite', lines: ['Configure & verify', '2×400G breakout', 'before discovery'], evidence: breakout },
  { id: 'p1', x: 439, y: 16, header: 'Procedure 1', lines: ['Create AI BE fabric', 'using ND', 'AI template'], evidence: procedureEvidence[0] },
  { id: 'p2', x: 46, y: 130, header: 'Procedure 2', lines: ['Discover & add', 'switches with reload'], evidence: procedureEvidence[1] },
  { id: 'p3', x: 177, y: 130, header: 'Procedure 3', lines: ['Assign spine and', 'leaf role;', 'deploy fabric'], evidence: procedureEvidence[2] },
  { id: 'upgrade', x: 308, y: 130, h: 80, kind: 'diamond', lines: ['NX-OS', 'upgrade', 'required?'], evidence: upgradeDecision },
  { id: 'p4', x: 439, y: 130, header: 'Procedure 4', lines: ['Upgrade NXOS', 'using ND', 'Update Groups'], evidence: procedureEvidence[3] },
  { id: 'p5', x: 46, y: 260, header: 'Procedure 5', lines: ['(Optional)', 'Customize AI QoS:', 'Queueing'], evidence: procedureEvidence[4] },
  { id: 'p6', x: 177, y: 260, header: 'Procedure 6', lines: ['(Optional)', 'Enable BFD for BGP'], evidence: procedureEvidence[5] },
  { id: 'p7', x: 308, y: 260, header: 'Procedure 7', font: 9.46, lineHeight: 10.75, lines: ['Verify BE fabric', 'health, connectivity,', 'BGP EVPN, QoS', 'and BFD'], evidence: procedureEvidence[6] },
  { id: 'end', x: 442.5, y: 282.5, w: 106, h: 35, kind: 'terminal', lines: ['Healthy Backend', 'Fabric Deployed'] },
];
function text(cx, y, lines, header = false, font = FONT, lineHeight = LINE_H) {
  // y is the first line's visual center, already positioned within its block.
  // Use an explicit alphabetic baseline so previews need no baseline CSS support.
  const size = header ? HEADER_FONT : font;
  // 0.37 is the approximately 0.35-em optical correction for this font stack.
  const baseline = Number((y + 0.37 * size).toFixed(4));
  return `<text x="${cx}" y="${baseline}" text-anchor="middle" fill="${header ? C.blue : C.ink}" font-size="${size}"${header ? ' font-weight="700"' : ''} font-family="${FONT_FAMILY}">${lines.map((line, i) => `<tspan x="${cx}" dy="${i ? lineHeight : 0}">${esc(line)}</tspan>`).join('')}</text>`;
}
function node(n) {
  if (!n.kind) n = { ...n, y: n.y + (80 - BOX_H) / 2 };
  const w = n.w ?? BOX_W, h = n.h ?? BOX_H, cx = n.x + w / 2, cy = n.y + h / 2;
  let shape;
  if (n.kind === 'diamond') {
    shape = `<polygon data-shape="diamond" points="${cx},${n.y} ${n.x + w},${cy} ${cx},${n.y + h} ${n.x},${cy}" fill="${C.amberTint}" stroke="${C.amber}" stroke-width="0.8"/>`;
  } else {
    shape = `<rect data-shape="box" x="${n.x}" y="${n.y}" width="${w}" height="${h}" rx="${n.kind === 'terminal' ? h / 2 : 2}" fill="${n.kind === 'terminal' ? C.tint : C.white}" stroke="${n.kind === 'terminal' ? C.blue : C.border}" stroke-width="0.8"/>`;
  }
  const count = n.lines.length + (n.header ? 1 : 0);
  const lineHeight = n.lineHeight ?? LINE_H;
  const top = cy - (count - 1) * lineHeight / 2;
  return `<g data-node="${n.id}"${n.evidence ? ` data-source-line="${n.evidence.line}"` : ''}>${shape}${n.header ? text(cx, top, [n.header], true) : ''}${text(cx, top + (n.header ? lineHeight : 0), n.lines, false, n.font ?? FONT, lineHeight)}</g>`;
}
const edges = [];
const arrow = (id, d) => { edges.push(id); return `<path data-edge="${id}" d="${d}" fill="none" stroke="${C.line}" stroke-width="0.8" marker-end="url(#arrow)"/>`; };
const line = d => `<path d="${d}" fill="none" stroke="${C.line}" stroke-width="0.8"/>`;
const connector = (x, y, tag) => `<g><circle cx="${x}" cy="${y}" r="9" fill="${C.white}" stroke="${C.blue}" stroke-width="0.96"/>${text(x, y, [tag], true)}</g>`;
const branchLabel = (x, y, label) => `<text x="${x}" y="${y}" text-anchor="middle" fill="${C.line}" font-size="${HEADER_FONT}" font-weight="600" font-family="${FONT_FAMILY}">${label}</text>`;
const drawing = [
  arrow('start-prerequisites', 'M149 56 H175'), arrow('prerequisites-breakout', 'M290 56 H306'),
  arrow('breakout-p1', 'M421 56 H437'), arrow('p1-A', 'M552 56 H569'), connector(579, 56, 'A'),
  connector(19, 170, 'A'), arrow('A-p2', 'M28 170 H44'), arrow('p2-p3', 'M159 170 H175'),
  arrow('p3-upgrade', 'M290 170 H306'), arrow('upgrade-yes-p4', 'M421 170 H437'), branchLabel(429, 161, 'Yes'),
  line('M364.5 210 V234 H495.5'), branchLabel(380, 226, 'No'),
  line('M495.5 200.08 V234'), '<circle cx="495.5" cy="234" r="1.6" fill="#525E6C"/>',
  arrow('upgrade-join-B', 'M495.5 234 H569'), connector(579, 234, 'B'),
  connector(19, 300, 'B'), arrow('B-p5', 'M28 300 H44'), arrow('p5-p6', 'M159 300 H175'),
  arrow('p6-p7', 'M290 300 H306'), arrow('p7-end', 'M421 300 H440.5'),
];
const svg = `<svg xmlns="http://www.w3.org/2000/svg" width="${W}" height="${H}" viewBox="0 0 ${W} ${H}" role="img" aria-labelledby="title description">
<title id="title">SG2 Backend Fabric Deployment Workflow</title>
<desc id="description">Manual chapter sequence. Check prerequisites, configure breakout, create the fabric, discover and add switches, assign roles and deploy. Upgrade NX-OS with Procedure 4 only if required. Optionally customize AI QoS and enable BFD. Verify the fabric with Procedure 7. Matching A and B circles continue to the next row. This diagram describes a procedure, not evidence of a completed live deployment.</desc>
<rect width="${W}" height="${H}" fill="${C.white}"/>
<defs><marker id="arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="5" markerHeight="5" orient="auto-start-reverse"><path d="M0 0 L10 5 L0 10z" fill="${C.line}"/></marker></defs>
${nodes.map(node).join('\n')}
${drawing.join('\n')}
</svg>\n`;
assert(!svg.includes('preflight'), 'Manual chapter figure must not include automation-preflight commentary');
const basename = 'backend-sg2-deployment-workflow';
const svgPath = path.join(out, 'backend-sg2-deployment-workflow.svg');
const pngPath = path.join(out, `${basename}.png`);
const proofPath = path.join(out, `${basename}.verification.json`);
const replaceStaged = args['--replace-staged-in-this-turn'] === 'true';
for (const file of [svgPath, pngPath, proofPath]) {
  assert(!fs.lstatSync(file, { throwIfNoEntry: false })?.isSymbolicLink(), 'Output-file symlinks are forbidden');
  assert(replaceStaged || !fs.existsSync(file), `Refusing to replace existing file: ${file}`);
}
fs.mkdirSync(out, { recursive: true });
const browser = await chromium.launch({ executablePath: args['--chrome'], headless: true,
  args: ['--disable-background-networking', '--no-first-run'] });
let layout;
try {
  const context = await browser.newContext({ viewport: { width: W, height: H }, deviceScaleFactor: 4 });
  await context.route('**/*', route => route.abort());
  const page = await context.newPage();
  await page.setContent(`<html><head><meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'"></head><body style="margin:0">${svg}</body></html>`);
  await page.evaluate(() => document.fonts.ready);
  layout = await page.evaluate(() => {
    const errors = [], labels = [], centering = [];
    const checkCenter = (id, shape, texts) => {
      const s = shape.getBBox(), bounds = [...texts].map(t => t.getBBox());
      const top = Math.min(...bounds.map(b => b.y));
      const bottom = Math.max(...bounds.map(b => b.y + b.height));
      const dy = (top + bottom) / 2 - (s.y + s.height / 2);
      const dx = Math.max(...bounds.map(b => Math.abs(b.x + b.width / 2 - (s.x + s.width / 2))));
      centering.push({ id, horizontalError: dx, verticalError: dy });
      if (dx > 0.1 || Math.abs(dy) > 0.5) errors.push(`Text not centered: ${id}`);
    };
    for (const group of document.querySelectorAll('[data-node]')) {
      const shape = group.querySelector('[data-shape]'), bounds = shape.getBBox();
      checkCenter(group.dataset.node, shape, group.querySelectorAll('text'));
      for (const label of group.querySelectorAll('text')) {
        const b = label.getBBox();
        const corners = [[b.x,b.y],[b.x+b.width,b.y],[b.x,b.y+b.height],[b.x+b.width,b.y+b.height]];
        const inside = corners.every(([x,y]) => shape.dataset.shape === 'diamond'
          ? Math.abs(x-(bounds.x+bounds.width/2))/(bounds.width/2) + Math.abs(y-(bounds.y+bounds.height/2))/(bounds.height/2) < 0.96
          : x >= bounds.x+3 && x <= bounds.x+bounds.width-3 && y >= bounds.y+3 && y <= bounds.y+bounds.height-3);
        labels.push({ node: group.dataset.node, text: label.textContent, width: b.width, fits: inside,
          textBounds: { x: b.x, y: b.y, width: b.width, height: b.height },
          shapeBounds: { x: bounds.x, y: bounds.y, width: bounds.width, height: bounds.height } });
        if (!inside) errors.push(`${group.dataset.node}: ${label.textContent}`);
      }
    }
    for (const group of document.querySelectorAll('g')) {
      const circle = group.querySelector(':scope > circle');
      const label = group.querySelector(':scope > text');
      if (circle && label) checkCenter(`continuation-${label.textContent}`, circle, [label]);
    }
    if (document.querySelector('[dominant-baseline]')) errors.push('Unexpected dominant-baseline dependency');
    const svg = document.querySelector('svg');
    const canvasWidth = svg.viewBox.baseVal.width, canvasHeight = svg.viewBox.baseVal.height;
    for (const note of document.querySelectorAll('[data-note] text')) {
      const b = note.getBBox();
      if (b.x < 3 || b.y < 3 || b.x+b.width > canvasWidth-3 || b.y+b.height > canvasHeight-3) errors.push('Note outside viewBox');
    }
    const b = svg.getBBox();
    if (b.x < 0 || b.y < 0 || b.x+b.width > canvasWidth || b.y+b.height > canvasHeight) errors.push('Drawing outside viewBox');
    return { errors, labels, centering, nodeCount: document.querySelectorAll('[data-node]').length };
  });
  if (layout.errors.length) console.log(JSON.stringify(layout.labels.filter(l => l.node === 'p7'), null, 2));
  assert.deepEqual(layout.errors, [], 'Label or canvas overflow');
  assert.equal(layout.nodeCount, 12);
  assert.equal(sha256(fs.readFileSync(source)), sha256(sourceBytes), 'Chapter changed during generation; review again');
  fs.writeFileSync(svgPath, svg, { flag: replaceStaged ? 'w' : 'wx' });
  await page.screenshot({ path: pngPath, type: 'png' });
  await context.close();
} finally { await browser.close(); }
const pngBytes = fs.readFileSync(pngPath);
assert.equal(pngBytes.readUInt32BE(16), W*4);
assert.equal(pngBytes.readUInt32BE(20), H*4);
const proof = {
  source: { path: source, sha256: sha256(sourceBytes), unchangedAfterGeneration: true },
  outputs: [svgPath, pngPath].map(file => ({ path: file, bytes: fs.statSync(file).size, sha256: sha256(fs.readFileSync(file)) })),
  canvas: { svg: [W,H], png: [W*4,H*4], intendedEmbedWidthInches: 6, bodyPointSize: 7.4,
    procedureBox: [BOX_W, BOX_H], procedure7BodyPointSize: 9.46 * 72 / 100,
    procedure7LineHeight: 10.75, endBox: [106,35], decisionDiamond: [113,80] },
  textPositioning: { horizontal: 'text-anchor="middle"', vertical: 'Explicit alphabetic baseline; no dominant-baseline attribute',
    firstBaseline: 'centerY - ((lineCount - 1) / 2) * lineHeight + 0.37 * fontSize; header/body centers share the existing block layout',
    singleLineBaseline: 'centerY + 0.37 * fontSize', fontSizesAndLineHeightsUnchanged: true,
    legacyProcedure7OneUnitDownwardNudgeRemoved: true },
  procedureEvidence, supportingEvidence: { prerequisites, dnsNtpAssumption, breakout, upgradeDecision, reload, bfdVerification },
  approvedLabelChanges: {
    authority: 'Archana, 2026-10-16: SVG and SG2 generator editing authorized; no chapter/Word/build writes or SVG import.',
    breakoutHeader: 'Deploy prerequisite', procedure1Template: 'ND AI template',
    dnsNtp: 'DNS/NTP remain chapter prerequisite assumptions, represented in the Prerequisites box; no chapter prerequisite change.',
    manualFigureCleanup: 'Removed the automation-preflight footnote and matching description sentence; trimmed the bottom band from 356 to 338 units without moving any workflow content.',
    conditionalGrammar: 'Unchanged: upgrade required? decision before P4; P5/P6 are operator-optional.',
  },
  styleExceptionsUnchanged: ['Existing smaller P7 body font remains pending the separately scoped shared-engine style regression; no font was shrunk for these label changes.'],
  layout, edges,
  scope: 'Chapter workflow draft only; no chapter integration, Word build, automation changes, device contact, or deployment.',
};
fs.writeFileSync(proofPath, JSON.stringify(proof, null, 2)+'\n', { flag: replaceStaged ? 'w' : 'wx' });
console.log(JSON.stringify({ result: 'PASS', svgPath, pngPath, proofPath, nodes: 12,
  procedures: procedureEvidence.length, labelFitErrors: layout.errors.length, pngDimensions: [W*4,H*4],
  sourceSHA256: proof.source.sha256 }, null, 2));
