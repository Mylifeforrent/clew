// Frontend/backend API integration script: mirrors every request in src/lib/api.ts
// (paths / field names / error semantics) and runs end-to-end checks against a live backend.
// Usage:
//
//   node scripts/api-e2e.mjs                 # defaults to http://127.0.0.1:8000
//   E2E_BASE_URL=http://127.0.0.1:8001 node scripts/api-e2e.mjs
//
// Writes e2e-prefixed data to the backend (users / batches / tags / annotations / edges), then
// rolls back to the e2e baseline tag to revert rollbackable changes; annotations are append-only
// and stay. Apart from change_log the script leaves no global state and can be run repeatedly.

const BASE = (process.env.E2E_BASE_URL ?? 'http://127.0.0.1:8000').replace(/\/$/, '');

let pass = 0;
const failures = [];

function check(name, ok, detail = '') {
  if (ok) {
    pass += 1;
    console.log(`  PASS  ${name}`);
  } else {
    failures.push(`${name}${detail ? ` — ${detail}` : ''}`);
    console.log(`  FAIL  ${name}${detail ? ` — ${detail}` : ''}`);
  }
}

/** Same error-body parsing as api.ts::request (detail string / 422 array). */
function readErrorDetail(payload, status) {
  if (payload && typeof payload === 'object' && 'detail' in payload) {
    const d = payload.detail;
    if (typeof d === 'string' && d.trim()) return d;
    if (Array.isArray(d)) {
      const msgs = d
        .map((item) => (item && typeof item === 'object' && 'msg' in item ? String(item.msg) : ''))
        .filter(Boolean);
      if (msgs.length) return msgs.join('；');
    }
  }
  return `HTTP ${status}`;
}

async function req(path, { method = 'GET', token, body, form } = {}) {
  const headers = {};
  if (body !== undefined) headers['Content-Type'] = 'application/json';
  if (token) headers.Authorization = `Bearer ${token}`;
  const res = await fetch(`${BASE}${path}`, {
    method,
    headers,
    body: form ?? (body !== undefined ? JSON.stringify(body) : undefined),
  });
  let payload = null;
  if (res.status !== 204) {
    try {
      payload = await res.json();
    } catch {
      payload = null;
    }
  }
  return { status: res.status, payload, res };
}

function isObject(v) {
  return v !== null && typeof v === 'object' && !Array.isArray(v);
}

/** Assert object fields are present and types match; returns null or a missing-field description. */
function hasShape(obj, shape) {
  const missing = Object.entries(shape).filter(([key, type]) => {
    const v = obj?.[key];
    if (type === 'array') return !Array.isArray(v);
    if (type === 'object') return !isObject(v);
    if (type === 'string|null') return v !== null && typeof v !== 'string';
    if (type === 'number|null') return v !== null && typeof v !== 'number';
    if (type === 'string') return typeof v !== 'string';
    if (type === 'number') return typeof v !== 'number';
    if (type === 'boolean') return typeof v !== 'boolean';
    return true;
  }).map(([key]) => key);
  return missing.length === 0 ? null : `Missing field or type mismatch: ${missing.join(', ')}`;
}

async function expectStatus(name, promiseOrRes, wantStatus, wantDetailIncludes) {
  const r = await promiseOrRes;
  const okStatus = r.status === wantStatus;
  let ok = okStatus;
  let detail = `actual ${r.status}`;
  if (okStatus && wantDetailIncludes) {
    const msg = readErrorDetail(r.payload, r.status);
    ok = msg.includes(wantDetailIncludes);
    detail = `detail="${msg}"`;
  }
  check(name, ok, ok ? '' : detail);
  return r;
}

const ts = Date.now();
const TAG_BASE = `e2e-baseline-${ts}`;
const TAG_MID = `e2e-mid-${ts}`;
const DS_E2E = `e2e_ds_${ts}`;
const EDITOR_NAME = `e2e_ed_${ts}`;
const VIEWER_NAME = `e2e_vw_${ts}`;

// ---------- Session ----------
let T = null; // admin token
let editor = null;
let viewer = null;

async function main() {
  console.log(`\n== 0. Login and session (POST /auth/login, GET /auth/me) ==`);
  const login = await req('/auth/login', { method: 'POST', body: { username: 'admin', password: 'admin123' } });
  check('Login returns 200 with access_token/username/role', login.status === 200 &&
    hasShape(login.payload, { access_token: 'string', token_type: 'string', username: 'string', role: 'string' }) === null,
    `actual ${login.status}`);
  T = login.payload?.access_token;
  await expectStatus('Wrong password 401', req('/auth/login', { method: 'POST', body: { username: 'admin', password: 'wrong' } }), 401);
  const me = await req('/auth/me', { token: T });
  check('GET /auth/me 200 returns username/role', me.status === 200 && hasShape(me.payload, { username: 'string', role: 'string' }) === null, `actual ${me.status}`);
  await expectStatus('No credentials 401 (frontend returns to sign-in)', req('/datasets'), 401);

  console.log(`\n== 1. Browsing: datasets / subgraph / source preview (viewer read paths) ==`);
  const ds = await req('/datasets', { token: T });
  check('GET /datasets 200 and elements contain id/name/field_count/field_names',
    ds.status === 200 && Array.isArray(ds.payload) && ds.payload.length > 0 &&
    hasShape(ds.payload[0], { id: 'string', name: 'string|null', field_count: 'number', field_names: 'array' }) === null,
    `actual ${ds.status}`);
  const seedDs = ds.payload.find((d) => !d.id.startsWith('e2e'));
  const seedId = seedDs?.id ?? 'd0';

  const detail = await req(`/datasets/${encodeURIComponent(seedId)}`, { token: T });
  const seedDesc = detail.payload?.fields?.find((f) => f.name === 'order_id')?.description ?? null;
  check('GET /datasets/{id} 200 fields contain locator envelope and source file name',
    detail.status === 200 && isObject(detail.payload) &&
    detail.payload.fields?.[0]?.src_locator != null && 'input' in detail.payload.fields[0].src_locator &&
    typeof detail.payload.fields[0].source_file_name === 'string',
    `actual ${detail.status}`);

  const sub = await req(`/lineage/subgraph?dataset=${seedId}&hops=3&direction=both`, { token: T });
  const subOk = sub.status === 200 && isObject(sub.payload) && Array.isArray(sub.payload.datasets) && Array.isArray(sub.payload.edges);
  check('GET /lineage/subgraph 200 returns datasets[]/edges[]', subOk, `actual ${sub.status}`);
  if (subOk) {
    const f = sub.payload.datasets.flatMap((d) => d.fields ?? [])[0];
    check('Subgraph fields contain name/field_type/description/src_locator envelope/source_file',
      f && hasShape(f, { name: 'string', field_type: 'string|null', description: 'string|null' }) === null &&
      isObject(f.src_locator) && 'input' in f.src_locator && 'resolved' in f.src_locator &&
      isObject(f.source_file) && typeof f.source_file.original_name === 'string');
    const e = sub.payload.edges[0];
    check('Subgraph edges contain id and 8 business fields (appendix A2)',
      e && hasShape(e, { id: 'number', from_dataset: 'string', from_field: 'string|null', to_dataset: 'string', to_field: 'string|null', transform: 'string|null', confidence: 'number|null', source: 'string', note: 'string|null' }) === null);
  }
  const fieldSub = await req(`/lineage/subgraph?dataset=${seedId}&field=order_id&hops=2&direction=up`, { token: T });
  check('Field-level subgraph 200', fieldSub.status === 200, `actual ${fieldSub.status}`);
  await expectStatus('Subgraph unknown dataset 404', req(`/lineage/subgraph?dataset=nope_${ts}&hops=3`, { token: T }), 404);
  await expectStatus('Subgraph hops=9 out of range 422', req(`/lineage/subgraph?dataset=${seedId}&hops=9`, { token: T }), 422);

  // Pick one field per locator kind for source preview
  for (const [dsId, field, kind] of [[seedId, 'order_id', 'csv'], ['d1', 'order_id', 'xlsx'], ['d2', 'order_id', 'json']]) {
    const p = await req(`/fields/${encodeURIComponent(dsId)}/${encodeURIComponent(field)}/preview`, { token: T });
    const shapeOk = p.status === 200 && isObject(p.payload) &&
      hasShape(p.payload, { file: 'object', locator: 'object', preview: 'object' }) === null &&
      (p.payload.verification === null || hasShape(p.payload.verification, { status: 'string', version_no: 'number', checked_by: 'string', checked_at: 'string' }) === null);
    check(`GET /fields/${dsId}/${field}/preview (${kind}) 200 with correct shape`, shapeOk, `actual ${p.status}`);
    if (p.status === 200) {
      const pv = p.payload.preview;
      const want = {
        csv: ['header', 'column_index', 'rows'],
        xlsx: ['sheet', 'header_rows', 'merged_ranges', 'column_index', 'row_start', 'row_end', 'rows'],
        json: ['json_path', 'hits', 'samples'],
      }[kind];
      check(`  ${kind} preview shape fields ${want.join('/')}`, want.every((k) => k in pv));
    }
  }
  await expectStatus('Unknown field preview 404', req(`/fields/${seedId}/nope_${ts}/preview`, { token: T }), 404);

  console.log(`\n== 2. User management (admin) ==`);
  const users0 = await req('/users', { token: T });
  check('GET /users 200 elements contain username/display_name/role',
    users0.status === 200 && Array.isArray(users0.payload) &&
    hasShape(users0.payload[0], { username: 'string', display_name: 'string|null', role: 'string' }) === null,
    `actual ${users0.status}`);
  const mkUser = await req('/users', { method: 'POST', token: T, body: { username: EDITOR_NAME, password: 'e2e-pass-123', display_name: 'E2E Editor', role: 'editor' } });
  check('POST /users editor 201', mkUser.status === 201 && hasShape(mkUser.payload, { username: 'string', display_name: 'string|null', role: 'string' }) === null, `actual ${mkUser.status}`);
  const mkViewer = await req('/users', { method: 'POST', token: T, body: { username: VIEWER_NAME, password: 'e2e-pass-123', role: 'viewer' } });
  check('POST /users viewer 201', mkViewer.status === 201, `actual ${mkViewer.status}`);
  await expectStatus('Duplicate username 409', req('/users', { method: 'POST', token: T, body: { username: EDITOR_NAME, password: 'e2e-pass-123', role: 'editor' } }), 409);
  await expectStatus('Invalid role 422', req('/users', { method: 'POST', token: T, body: { username: `e2e_x_${ts}`, password: 'e2e-pass-123', role: 'root' } }), 422);
  editor = (await req('/auth/login', { method: 'POST', body: { username: EDITOR_NAME, password: 'e2e-pass-123' } })).payload?.access_token;
  viewer = (await req('/auth/login', { method: 'POST', body: { username: VIEWER_NAME, password: 'e2e-pass-123' } })).payload?.access_token;
  check('New users can log in and obtain tokens', Boolean(editor) && Boolean(viewer));

  console.log(`\n== 3. RBAC: viewer read-only (write operations 403) ==`);
  await expectStatus('viewer GET /datasets 200', req('/datasets', { token: viewer }), 200);
  await expectStatus('viewer POST /files 403', req('/files', { method: 'POST', token: viewer, form: new FormData() }), 403);
  await expectStatus('viewer POST /edges 403', req('/edges', { method: 'POST', token: viewer, body: { from_dataset: seedId, to_dataset: seedId } }), 403);
  await expectStatus('viewer POST /annotations 403', req('/annotations', { method: 'POST', token: viewer, body: { target_kind: 'dataset', target_id: seedId, body: 'x' } }), 403);
  await expectStatus('viewer GET /users 403', req('/users', { token: viewer }), 403);
  await expectStatus('viewer POST /ai/suggest 403', req('/ai/suggest', { method: 'POST', token: viewer, body: { dataset: seedId } }), 403);

  console.log(`\n== 4. Import wizard in three steps: upload → import → batches (POST /files, POST /import, GET /import/batches) ==`);
  const csv1 = 'order_id,amount,region\nSO-1,19.9,East\nSO-2,42.0,North\n';
  const csv2 = 'product_id,region,qty\nP-1,East,3\nP-2,North,7\n';
  const form1 = new FormData();
  form1.append('files', new File([csv1], 'e2e_orders.csv', { type: 'text/csv' }));
  form1.append('files', new File([csv2], 'e2e_products.csv', { type: 'text/csv' }));
  const up = await req('/files', { method: 'POST', token: editor, form: form1 });
  const upOk = up.status === 201 && Array.isArray(up.payload) && up.payload.length === 2 &&
    hasShape(up.payload[0], { id: 'number', original_name: 'string', storage_path: 'string', sha256: 'string', size_bytes: 'number', src_type: 'string', uploaded_by: 'string', created_at: 'string', deduped: 'boolean' }) === null;
  check('POST /files 201 returns registration records (with storage_path/deduped)', upOk, `actual ${up.status}`);
  const [fileA, fileB] = up.payload ?? [];
  const formDup = new FormData();
  formDup.append('files', new File([csv1], 'e2e_orders_again.csv', { type: 'text/csv' }));
  const upDup = await req('/files', { method: 'POST', token: editor, form: formDup });
  check('Re-uploading identical content dedupes by sha256, deduped=true', upDup.status === 201 && upDup.payload?.[0]?.deduped === true, `actual ${upDup.status}`);

  const dsManifest = [
    'dataset_id,dataset_name,field_name,field_type,src_file,src_type,src_locator,description',
    `${DS_E2E},E2E Test Set,order_id,STRING,${fileA.id},csv,"{""header"":""order_id""}",Order ID`,
    `${DS_E2E},E2E Test Set,amount,DECIMAL,${fileA.id},csv,"{""header"":""amount""}",Order Amount`,
    `${DS_E2E},E2E Test Set,bad_field,STRING,${fileA.id},csv,"{""header"":""no_such_header""}",Should be rejected at row level`,
    `${DS_E2E},E2E Test Set,region,STRING,${fileB.id},csv,"{""column"":2}",Sales Region`,
  ].join('\n');
  const edgeManifest = [
    'from_dataset,from_field,to_dataset,to_field,transform,confidence,note',
    `${DS_E2E},order_id,${seedId},order_id,trim,0.9,e2e imported edge`,
    `${DS_E2E},amount,${seedId},amount,cast,not-a-number,Invalid confidence should be rejected`,
  ].join('\n');
  const importForm = new FormData();
  importForm.append('format', 'csv');
  importForm.append('source_file_ids', `${fileA.id},${fileB.id}`);
  importForm.append('manifest_datasets', new File([dsManifest], 'datasets.csv', { type: 'text/csv' }));
  importForm.append('manifest_lineage', new File([edgeManifest], 'lineage.csv', { type: 'text/csv' }));
  const imp = await req('/import', { method: 'POST', token: editor, form: importForm });
  const impOk = imp.status === 201 && isObject(imp.payload) &&
    hasShape(imp.payload, { batch_id: 'number', version_no: 'number', report: 'object' }) === null &&
    hasShape(imp.payload.report, { summary: 'object', items: 'array' }) === null;
  check('POST /import 201 returns batch_id/version_no/report', impOk, `actual ${imp.status} ${JSON.stringify(imp.payload ?? '')?.slice(0, 200)}`);
  if (impOk) {
    const { summary, items } = imp.payload.report;
    check(`Import report row-level rejection works (rejected>=2, actual ${JSON.stringify(summary)})`, summary.rejected >= 2 && items.some((i) => i.status === 'rejected'));
  }
  const batchId = imp.payload?.batch_id;
  const batches = await req('/import/batches', { token: T });
  const batchRow = batches.payload?.find((b) => b.id === batchId);
  check('GET /import/batches includes the new batch (file_names array, rolled_back_at null)',
    batches.status === 200 && batchRow &&
    hasShape(batchRow, { id: 'number', version_no: 'number', file_names: 'array', format: 'string', created_by: 'string', created_at: 'string', rolled_back_at: 'string|null' }) === null,
    `actual ${batches.status}`);
  const subNew = await req(`/lineage/subgraph?dataset=${DS_E2E}&hops=1&direction=both`, { token: T });
  check('The new dataset subgraph is queryable after import', subNew.status === 200 && subNew.payload?.datasets?.some((d) => d.id === DS_E2E), `actual ${subNew.status}`);
  const pvNew = await req(`/fields/${DS_E2E}/order_id/preview`, { token: T });
  check('Imported field source preview 200 with verification.passed', pvNew.status === 200 && pvNew.payload?.verification?.status === 'passed', `actual ${pvNew.status}`);
  await expectStatus('Missing manifest file 400', req('/import', {
    method: 'POST', token: editor,
    form: (() => { const f = new FormData(); f.append('format', 'csv'); f.append('source_file_ids', String(fileA.id)); return f; })(),
  }), 400);

  console.log(`\n== 5. Batch rollback (admin) + create a rollbackable baseline tag ==`);
  await expectStatus('editor batch rollback 403', req(`/import/batches/${batchId}/rollback`, { method: 'POST', token: editor }), 403);
  const rb = await req(`/import/batches/${batchId}/rollback`, { method: 'POST', token: T });
  check('admin batch rollback 200 {batch_id,reverted}', rb.status === 200 && rb.payload?.batch_id === batchId && rb.payload?.reverted > 0, `actual ${rb.status}`);
  await expectStatus('Repeated batch rollback 409', req(`/import/batches/${batchId}/rollback`, { method: 'POST', token: T }), 409);
  const subGone = await req(`/lineage/subgraph?dataset=${DS_E2E}&hops=1`, { token: T });
  check('e2e_ds subgraph 404 after rollback (data reverted)', subGone.status === 404, `actual ${subGone.status}`);
  const batches2 = await req('/import/batches', { token: T });
  check('Batch list has rolled_back_at written', batches2.payload?.find((b) => b.id === batchId)?.rolled_back_at != null);

  const tag0 = await req('/version-tags', { method: 'POST', token: T, body: { name: TAG_BASE, note: 'e2e baseline (before subsequent writes in this run)' } });
  check('POST /version-tags 201 {name,change_seq,…}', tag0.status === 201 && hasShape(tag0.payload, { name: 'string', note: 'string|null', change_seq: 'number', created_by: 'string', created_at: 'string' }) === null, `actual ${tag0.status}`);
  await expectStatus('Duplicate tag name 409', req('/version-tags', { method: 'POST', token: T, body: { name: TAG_BASE } }), 409);

  console.log(`\n== 6. Field editing (PATCH /fields/{ds}/{f}) ==`);
  const pf = await req(`/fields/${seedId}/order_id`, { method: 'PATCH', token: editor, body: { description: `E2E description ${ts}` } });
  check('editor update description 200 returns the field object (with src_locator)', pf.status === 200 && isObject(pf.payload) && pf.payload.description === `E2E description ${ts}` && 'src_locator' in pf.payload, `actual ${pf.status}`);
  await expectStatus('Locator type mismatches source file 409', req(`/fields/${seedId}/order_id`, { method: 'PATCH', token: editor, body: { src_locator: { type: 'json', input: { json_path: '$.x' } } } }), 409);
  await expectStatus('Explicit src_locator:null 400', req(`/fields/${seedId}/order_id`, { method: 'PATCH', token: editor, body: { src_locator: null } }), 400);
  await expectStatus('Empty patch body 400', req(`/fields/${seedId}/order_id`, { method: 'PATCH', token: editor, body: {} }), 400);
  await expectStatus('viewer editing a field 403', req(`/fields/${seedId}/order_id`, { method: 'PATCH', token: viewer, body: { description: 'x' } }), 403);

  console.log(`\n== 7. Annotations (append-only, survive rollbacks) ==`);
  const ano = await req('/annotations', { method: 'POST', token: editor, body: { target_kind: 'field', target_id: `${seedId}.order_id`, body: `E2E annotation ${ts}` } });
  check('POST /annotations 201 returns id/author', ano.status === 201 && hasShape(ano.payload, { id: 'number', target_kind: 'string', target_id: 'string', body: 'string', author: 'string', created_at: 'string' }) === null, `actual ${ano.status}`);
  const anoList = await req(`/annotations?target_kind=field&target_id=${encodeURIComponent(`${seedId}.order_id`)}`, { token: viewer });
  check('GET /annotations filtered by target includes the new annotation', anoList.status === 200 && Array.isArray(anoList.payload) && anoList.payload.some((a) => a.body === `E2E annotation ${ts}`), `actual ${anoList.status}`);
  await expectStatus('Blank body 400', req('/annotations', { method: 'POST', token: editor, body: { target_kind: 'field', target_id: `${seedId}.order_id`, body: '   ' } }), 400);
  await expectStatus('Target does not exist 404', req('/annotations', { method: 'POST', token: editor, body: { target_kind: 'dataset', target_id: `nope_${ts}`, body: 'x' } }), 404);

  console.log(`\n== 8. Lineage edge CRUD (POST/PATCH/DELETE /edges) ==`);
  // Seed edges run one-way d0→d1→…→d4; the reverse d3.order_id→d2.order_id is a new natural key
  const ek = { from_dataset: 'd3', from_field: 'order_id', to_dataset: 'd2', to_field: 'order_id' };
  const eNew = await req('/edges', { method: 'POST', token: editor, body: { ...ek, transform: 'e2e reverse edge', confidence: 0.9, note: 'e2e' } });
  const eNewOk = eNew.status === 201 && hasShape(eNew.payload, { id: 'number', from_dataset: 'string', from_field: 'string|null', to_dataset: 'string', to_field: 'string|null', transform: 'string|null', confidence: 'number|null', source: 'string', note: 'string|null' }) === null;
  check('POST /edges 201 source=manual', eNewOk && eNew.payload.source === 'manual', `actual ${eNew.status}`);
  const edgeId = eNew.payload?.id;
  await expectStatus('Duplicate edge for the same natural key 409', req('/edges', { method: 'POST', token: editor, body: { ...ek } }), 409);
  await expectStatus('Field-level/table-level with one side null 400', req('/edges', { method: 'POST', token: editor, body: { from_dataset: 'd3', from_field: 'order_id', to_dataset: 'd2', to_field: null } }), 400);
  await expectStatus('confidence out of range 422', req('/edges', { method: 'POST', token: editor, body: { ...ek, confidence: 1.5 } }), 422);
  await expectStatus('Nonexistent dataset 404', req('/edges', { method: 'POST', token: editor, body: { from_dataset: `nope_${ts}`, to_dataset: 'd2' } }), 404);
  const ep = await req(`/edges/${edgeId}`, { method: 'PATCH', token: editor, body: { transform: 'e2e reverse edge v2', note: 'e2e check', confidence: 0.8 } });
  check('PATCH /edges 200 update applied', ep.status === 200 && ep.payload?.transform === 'e2e reverse edge v2' && ep.payload?.confidence === 0.8, `actual ${ep.status}`);
  const ch = await req(`/changes?entity_kind=edge&entity_key=${encodeURIComponent('d3.order_id-->d2.order_id')}&limit=10`, { token: viewer });
  check('GET /changes edge history contains added/updated with before/after objects',
    ch.status === 200 && Array.isArray(ch.payload) && ch.payload.length >= 2 &&
    ch.payload.every((c) => hasShape(c, { id: 'number', op: 'string', actor: 'string', created_at: 'string' }) === null && (c.before === null || isObject(c.before)) && (c.after === null || isObject(c.after))),
    `actual ${ch.status}`);
  await expectStatus('viewer deleting an edge 403', req(`/edges/${edgeId}`, { method: 'DELETE', token: viewer }), 403);
  const del = await req(`/edges/${edgeId}`, { method: 'DELETE', token: editor });
  check('DELETE /edges 204 with no response body', del.status === 204, `actual ${del.status}`);
  await expectStatus('Repeated edge deletion 404', req(`/edges/${edgeId}`, { method: 'DELETE', token: editor }), 404);

  console.log(`\n== 9. AI: status / chat / heuristic suggestions ==`);
  const st = await req('/ai/status', { token: viewer });
  check('GET /ai/status 200 {configured,model}', st.status === 200 && hasShape(st.payload, { configured: 'boolean' }) === null && 'model' in st.payload, `actual ${st.status}`);
  const chat = await req('/ai/chat', { method: 'POST', token: viewer, body: { messages: [{ role: 'user', content: `Where does order_id of d0 come from?` }], focus: { dataset: seedId } } });
  if (st.payload?.configured === false) {
    check('/ai/chat 503 when LLM is not configured', chat.status === 503, `actual ${chat.status}`);
  } else {
    check('/ai/chat 200 {answer,tool_trace} when LLM is configured', chat.status === 200 && typeof chat.payload?.answer === 'string' && Array.isArray(chat.payload?.tool_trace), `actual ${chat.status}`);
  }
  await expectStatus('Message role=system 422', req('/ai/chat', { method: 'POST', token: viewer, body: { messages: [{ role: 'system', content: 'x' }] } }), 422);
  const sug = await req('/ai/suggest', { method: 'POST', token: editor, body: { dataset: seedId, field: null } });
  const sugOk = sug.status === 200 && Array.isArray(sug.payload?.candidates);
  check('POST /ai/suggest 200 candidates (confidence/reason)', sugOk && (sug.payload.candidates.length === 0 ||
    hasShape(sug.payload.candidates[0], { from_dataset: 'string', from_field: 'string|null', to_dataset: 'string', to_field: 'string|null', confidence: 'number', reason: 'string' }) === null), `actual ${sug.status}`);
  const candidates = sug.payload?.candidates ?? [];
  if (candidates.length > 0) {
    const key = (({ from_dataset, from_field, to_dataset, to_field }) => ({ from_dataset, from_field, to_dataset, to_field }))(candidates[0]);
    const cf = await req('/ai/suggest/confirm', { method: 'POST', token: editor, body: key });
    check('confirm candidate edge to manual 200 {edge}', cf.status === 200 && cf.payload?.edge?.source === 'manual' && typeof cf.payload.edge.id === 'number', `actual ${cf.status}`);
    const cfAgain = await req('/ai/suggest/confirm', { method: 'POST', token: editor, body: key });
    check('Repeated confirm 404 (already processed)', cfAgain.status === 404, `actual ${cfAgain.status}`);
    if (candidates.length > 1) {
      const key2 = (({ from_dataset, from_field, to_dataset, to_field }) => ({ from_dataset, from_field, to_dataset, to_field }))(candidates[1]);
      const rj = await req('/ai/suggest/reject', { method: 'POST', token: editor, body: key2 });
      check('reject candidate edge 204', rj.status === 204, `actual ${rj.status}`);
      const rjAgain = await req('/ai/suggest/reject', { method: 'POST', token: editor, body: key2 });
      check('Repeated reject 404', rjAgain.status === 404, `actual ${rjAgain.status}`);
    }
  } else {
    check('Usable heuristic candidates exist (seed data same-name fields should match)', false, 'candidates is empty');
  }

  console.log(`\n== 10. Version tags: diff / roll back to baseline (reverts writes from steps 6, 8, 9) ==`);
  const tag1 = await req('/version-tags', { method: 'POST', token: editor, body: { name: TAG_MID } });
  check('Second tag 201', tag1.status === 201, `actual ${tag1.status}`);
  const tags = await req('/version-tags', { token: viewer });
  check('GET /version-tags list elements contain id/batch_id/change_seq',
    tags.status === 200 && tags.payload.some((t) => t.name === TAG_MID) &&
    hasShape(tags.payload[0], { id: 'number', name: 'string', note: 'string|null', batch_id: 'number|null', change_seq: 'number', created_by: 'string', created_at: 'string' }) === null,
    `actual ${tags.status}`);
  const diff = await req(`/version-tags/diff?from=${encodeURIComponent(TAG_BASE)}&to=${encodeURIComponent(TAG_MID)}`, { token: viewer });
  const diffOk = diff.status === 200 && hasShape(diff.payload, { summary: 'object', items: 'array' }) === null;
  check('GET /version-tags/diff 200 summary/items with net changes in the range', diffOk && (diff.payload?.items?.length ?? 0) >= 1, `actual ${diff.status}`);
  if (diffOk) {
    check('diff summary contains added/updated/deleted counts', ['added', 'updated', 'deleted'].every((k) => typeof diff.payload.summary[k] === 'number'));
  }
  await expectStatus('diff with reversed direction 400', req(`/version-tags/diff?from=${encodeURIComponent(TAG_MID)}&to=${encodeURIComponent(TAG_BASE)}`, { token: viewer }), 400);
  await expectStatus('diff with unknown tag 404', req(`/version-tags/diff?from=nope_${ts}&to=${encodeURIComponent(TAG_MID)}`, { token: viewer }), 404);
  await expectStatus('editor tag rollback 403', req(`/version-tags/${encodeURIComponent(TAG_MID)}/rollback`, { method: 'POST', token: editor }), 403);
  const trb = await req(`/version-tags/${encodeURIComponent(TAG_BASE)}/rollback`, { method: 'POST', token: T });
  check('admin rollback to baseline 200 {reverted>0}', trb.status === 200 && trb.payload?.reverted > 0, `actual ${trb.status} ${JSON.stringify(trb.payload ?? '')}`);
  const trb2 = await req(`/version-tags/${encodeURIComponent(TAG_BASE)}/rollback`, { method: 'POST', token: T });
  check('Repeated tag rollback is idempotent (reverted=0)', trb2.status === 200 && trb2.payload?.reverted === 0, `actual ${trb2.status}`);
  const detailBack = await req(`/datasets/${encodeURIComponent(seedId)}`, { token: T });
  check('Field description restored to the baseline value after rollback', detailBack.status === 200 &&
    detailBack.payload?.fields?.find((f) => f.name === 'order_id')?.description === seedDesc,
    `actual ${detailBack.status}`);

  console.log(`\n== 11. Source file list and controlled download ==`);
  const fl = await req('/files', { token: viewer });
  check('GET /files 200 without storage_path (business rule #8)',
    fl.status === 200 && Array.isArray(fl.payload) && fl.payload.length > 0 &&
    hasShape(fl.payload[0], { id: 'number', original_name: 'string', sha256: 'string', size_bytes: 'number', src_type: 'string', uploaded_by: 'string', created_at: 'string' }) === null &&
    !('storage_path' in fl.payload[0]),
    `actual ${fl.status}`);
  const dl = await fetch(`${BASE}/files/${fl.payload[0].id}/download`, { headers: { Authorization: `Bearer ${viewer}` } });
  check('GET /files/{id}/download 200 binary stream (Content-Disposition)', dl.status === 200 && (dl.headers.get('content-disposition') ?? '').length > 0, `actual ${dl.status}`);
  await dl.body?.cancel();
  await expectStatus('Download nonexistent file 404', req('/files/999999999/download', { token: viewer }), 404);

  console.log(`\n=========================================`);
  console.log(`Passed ${pass}, failed ${failures.length}`);
  if (failures.length) {
    console.log('\nFailure details:');
    failures.forEach((f) => console.log(`  - ${f}`));
    process.exit(1);
  }
}

main().catch((err) => {
  console.error('E2E script aborted unexpectedly:', err);
  process.exit(2);
});
