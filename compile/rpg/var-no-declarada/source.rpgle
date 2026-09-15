**FREE
ctl-opt DFTACTGRP(*NO) ACTGRP(*NEW) OPTION(*NODEBUGIO);

dcl-s saludo char(10);

// varNombre NO se declara → debe producir RNF7030 (identificador no definido).
saludo = 'hola ' + varNombre;
dsply saludo;
