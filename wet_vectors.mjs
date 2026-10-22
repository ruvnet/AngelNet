#!/usr/bin/env node
// Local RuVector retrieval. Explicit lexical embeddings; no silent semantic fallback.
import {createRequire} from 'node:module';
import {readFile, writeFile, mkdir, unlink, stat} from 'node:fs/promises';
import {resolve, dirname, join} from 'node:path';
import {createInterface} from 'node:readline';
import {createReadStream} from 'node:fs';
import {createHash} from 'node:crypto';
import {performance} from 'node:perf_hooks';
import {pathToFileURL} from 'node:url';

const require = createRequire(import.meta.url);
const {VectorDb, getImplementationType} = require('ruvector');
const {LocalNGramProvider} = require('ruvector/dist/services/embedding-service.js');
const packageVersion = require('ruvector/package.json').version;
const MODEL = 'ruvector-local-ngram-v1:384:3';
const embedder = new LocalNGramProvider(384, 3);
const vector = async text => {
  const v = Float32Array.from((await embedder.embed([text]))[0]);
  if (v.length !== 384 || !v.every(Number.isFinite) || Math.hypot(...v) < 0.01) throw Error('Invalid embedding');
  return v;
};

export async function main(argv = process.argv.slice(2)) {
  const [command, ...rest] = argv;
  const opts = {};
  for (let i = 0; i < rest.length; i += 2) {
    if (!['--input','--store','--query','--limit','--k'].includes(rest[i]) || rest[i+1] === undefined) throw Error('Invalid argument');
    opts[rest[i].slice(2)] = rest[i+1];
  }
  if (!['build','search'].includes(command) || !opts.store) throw Error('Usage: wet_vectors.mjs build --input FILE --store DIR | search --store DIR --query TEXT');
  if (getImplementationType() !== 'native') throw Error('Native RuVector required');
  if (packageVersion !== '0.2.25') throw Error('Expected pinned ruvector 0.2.25');
  const store = resolve(opts.store), model = {model:MODEL, dimensions:384, package_version:packageVersion,
    semantic_model:false, description:'Character trigram lexical similarity; no transformer semantics'};
  const start = performance.now();
  if (command === 'build') {
    if (!opts.input) throw Error('Input required');
    const limit = Number(opts.limit ?? 1000);
    if (!Number.isInteger(limit) || limit < 1 || limit > 10000) throw Error('Limit must be 1 to 10000');
    if ((await stat(opts.input)).size > 100*1024*1024) throw Error('Input exceeds 100 MiB');
    // A fresh directory makes incomplete builds distinguishable and prevents model mixing.
    await mkdir(dirname(store), {recursive:true});
    await mkdir(store);
    await writeFile(join(store,'BUILDING'), 'Incomplete until manifest.json exists\n');
    const db = new VectorDb({dimensions:384, storagePath:join(store,'vectors.db'), distanceMetric:'Cosine'});
    const seen = new Set();
    const lines = createInterface({input:createReadStream(opts.input), crlfDelay:Infinity});
    let scanned = 0, inserted = 0;
    try {
      for await (const line of lines) {
        if (++scanned > limit) break;
        if (line.length > 200000) throw Error('Oversized input line');
        const doc = JSON.parse(line);
        if (typeof doc.text !== 'string' || !doc.text.trim() || doc.text.length > 8000 || !/^[a-f0-9]{64}$/.test(doc.id)) throw Error('Invalid WET document');
        if (seen.has(doc.id)) continue;
        seen.add(doc.id);
        await db.insert({id:doc.id, vector:await vector(doc.text), metadata:doc});
        inserted++;
      }
    } finally { lines.close(); }
    if (await db.len() !== inserted) throw Error('Insertion count mismatch');
    const reopened = new VectorDb({dimensions:384, storagePath:join(store,'vectors.db'), distanceMetric:'Cosine'});
    if (await reopened.len() !== inserted) throw Error('Persistence count mismatch');
    const report = {...model, records:inserted, backend:getImplementationType(), elapsed_ms:performance.now()-start,
      input_sha256:createHash('sha256').update(await readFile(opts.input)).digest('hex'),
      input_scope:`first ${limit} lines`, persistence_verified:true};
    await writeFile(join(store,'manifest.json'), JSON.stringify(report,null,2)+'\n');
    await unlink(join(store,'BUILDING'));
    console.log(JSON.stringify(report,null,2));
    return report;
  }
  const manifest = JSON.parse(await readFile(join(store,'manifest.json'),'utf8'));
  if (manifest.model !== MODEL || manifest.package_version !== packageVersion || manifest.dimensions !== 384) throw Error('Embedding contract mismatch');
  if (!opts.query?.trim() || opts.query.length > 8000) throw Error('Query required, maximum 8000 characters');
  const k = Number(opts.k ?? 5);
  if (!Number.isInteger(k) || k < 1 || k > 100) throw Error('k must be 1 to 100');
  const db = new VectorDb({dimensions:384, storagePath:join(store,'vectors.db'), distanceMetric:'Cosine'});
  if (await db.len() !== manifest.records) throw Error('Stored count differs from manifest');
  const results = manifest.records ? await db.search({vector:await vector(opts.query), k:Math.min(k,manifest.records), efSearch:Math.max(100,k)}) : [];
  const report = {model:MODEL, semantic_model:false, elapsed_ms:performance.now()-start, results};
  console.log(JSON.stringify(report,null,2));
  return report;
}

if (import.meta.url === pathToFileURL(process.argv[1] ?? '').href) {
  main().catch(e=>{ console.error(e.message); process.exitCode=2; });
}
