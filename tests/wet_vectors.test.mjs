import {test} from 'node:test';
import assert from 'node:assert/strict';
import {mkdtemp, writeFile, readFile, rm} from 'node:fs/promises';
import {tmpdir} from 'node:os';
import {join, resolve} from 'node:path';
import {execFileSync} from 'node:child_process';
import {createHash} from 'node:crypto';

const cli = resolve('wet_vectors.mjs');
test('native persistence, ranking, provenance and model contract across processes', async()=>{
  const root=await mkdtemp(join(tmpdir(),'angel-wet-'));
  try {
    const texts=['legacy PHP community forum discussion board','orchard apple pear fruit harvest','ocean whale dolphin coral reef'];
    const docs=texts.map((text,i)=>({id:createHash('sha256').update(text).digest('hex'),text,
      url:`https://fixture${i}.example.org/index.php`,source:'synthetic-test',vulnerability_status:'not_assessed'}));
    const input=join(root,'docs.jsonl'),store=join(root,'vectors');
    await writeFile(input,docs.concat(docs[0]).map(JSON.stringify).join('\n')+'\n');
    const run=(args)=>JSON.parse(execFileSync(process.execPath,[cli,...args],{encoding:'utf8'}));
    const report=run(['build','--input',input,'--store',store]);
    assert.equal(report.records,3);assert.equal(report.persistence_verified,true);assert.equal(report.backend,'native');
    const result=run(['search','--store',store,'--query',texts[0],'--k','3']);
    assert.equal(result.results[0].id,docs[0].id);assert.equal(result.semantic_model,false);
    assert.equal(result.results[0].metadata.source,'synthetic-test');
    assert.equal(result.results[0].metadata.vulnerability_status,'not_assessed');
    const manifest=JSON.parse(await readFile(join(store,'manifest.json'),'utf8'));
    manifest.model='wrong-model';await writeFile(join(store,'manifest.json'),JSON.stringify(manifest));
    assert.throws(()=>run(['search','--store',store,'--query',texts[0]]),/Embedding contract mismatch/);
  } finally {await rm(root,{recursive:true,force:true});}
});
