**free
// ============================================================
// Programa : HELLO
// Tipo     : RPGLE (*PGM)
// Desc     : Hola Mundo simple - Ejemplo basico RPGLE ILE
// Autor    : Proyecto Hola Mundo - IBM i
// Usa      : DSPLY (salida en pantalla / joblog)
// Compila  : CRTBNDRPG PGM(HELLO) SRCFILE(QRPGLESRC)
// ============================================================
ctl-opt dftactgrp(*no) actgrp(*new)
        option(*srcstmt:*nodebugio)
        datfmt(*iso)
        timfmt(*iso);

dcl-s mensaje varchar(52);

mensaje = 'Hola Mundo desde IBM i con RPGLE!';

dsply mensaje;

dsply 'Programa HELLO ejecutado correctamente.';

*inlr = *on;
return;
