# inative-mock-data — IBM i behavior corpus (§18)

> **iNative debe reproducir el comportamiento observable de IBM i a partir de contratos
> capturados y verificados contra un IBM i real** — no inventamos mensajes del simulador.

Árbol generado por `probe/joblog_recorder.py` (Record) + `internal/mock` (Replay):

```
inative-mock-data/
  metadata/{recorder-version.json,ibmi-environment.json}
  commands/{success,invalid-command,object-not-found,library-not-found,authority-error}
  rpgle/{compile/{success,syntax-error},runtime/{success,divide-by-zero,file-not-found,...}}
  cl/{success,monmsg,message-handling}
  fileio/{chain,read,reade,setll,setgt,write,update,delete,eof}
  messages/{sndpgmmsg,diagnostic,escape,completion}
  evfevent/
  raw/*.json            exact capture (timestamps/job numbers reales)
  normalized/*.json     deterministic contract (placeholders ${JOB_*})
```

Cada fixture: `fixture_version`, `experiment{id,name,language,category}`, `job` (placeholders),
`operation{command}`, `result{success}`, `joblog{messages[ordered],raw_messages}`, `raw{initial,final,delta}`,
`manifest{fixture_status: CAPTURED|REVIEWED|VERIFIED}`.

Ver `fixtures/joblog/README.md` y `tools/joblog-recorder/README.md`.
