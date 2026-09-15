**free
// ============================================================
// Programa : HELLOS
// Tipo     : SQLRPGLE (*PGM) con SQL embebido
// Desc     : Hola Mundo con SQL - Demuestra SQLRPGLE
//            Obtiene datos del sistema via SQL:
//            - Usuario actual
//            - Fecha / Hora actual
//            - Nombre del sistema
// Autor    : Proyecto Hola Mundo - IBM i
// Compila  : CRTSQLRPGI OBJ(HELLOS) SRCFILE(QRPGLESRC)
//            COMMIT(*NONE) OBJTYPE(*PGM)
//
// ============================================================
ctl-opt dftactgrp(*no) actgrp(*new)
        option(*srcstmt:*nodebugio)
        datfmt(*iso)
        timfmt(*iso);

exec sql set option commit = *none,
                    datfmt = *iso,
                    timfmt = *iso,
                    closqlcsr = *endmod;

dcl-s wUsuario varchar(18) inz('');
dcl-s wSysName varchar(18) inz('');
dcl-s wFecha   date inz(d'2026-01-01');
dcl-s wHora    time inz(t'00.00.00');
dcl-s wMensaje varchar(52) inz('');
dcl-s wSchema  varchar(52) inz('');

// Obtener datos via SQL simple (compatible V7R2+)
exec sql
  select current_user,
         current_date,
         current_time,
         current_server
    into :wUsuario,
         :wFecha,
         :wHora,
         :wSysName
  from sysibm.sysdummy1;

wMensaje = '=== HOLA MUNDO SQLRPGLE ===';
dsply wMensaje;

wMensaje = 'Hola Mundo desde SQLRPGLE!';
dsply wMensaje;

wMensaje = 'Usuario....: ' + %trim(wUsuario);
dsply wMensaje;

wMensaje = 'Sistema....: ' + %trim(wSysName);
dsply wMensaje;

wMensaje = 'Fecha......: ' + %char(wFecha);
dsply wMensaje;

wMensaje = 'Hora.......: ' + %char(wHora);
dsply wMensaje;

// Cursor: listar primeras 5 bibliotecas
dsply '--- Bibliotecas (primeras 5) ---';

exec sql declare c1 cursor for
  select schema_name
    from qsys2.sysschemas
   order by schema_name
   fetch first 5 rows only;

exec sql open c1;
exec sql fetch c1 into :wSchema;
dow sqlstate = '00000';
  wMensaje = '  * ' + %trim(wSchema);
  dsply wMensaje;
  exec sql fetch c1 into :wSchema;
enddo;
exec sql close c1;

dsply 'HELLOS finalizado correctamente.';

*inlr = *on;
return;
