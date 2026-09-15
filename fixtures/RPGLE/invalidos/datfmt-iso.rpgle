**FREE
ctl-opt DFTACTGRP(*NO) ACTGRP(*NEW) OPTION(*NODEBUGIO) DATFMT(*ISO);

// DATFMT(*ISO) — aceptado por iNative desde 2026-09-11 (FASE 6):
// IBM i real lo compila (formato ISO nativo) e iNative también
// (lowering a C: DATE char[11] YYYY-MM-DD, ver compile/rpg/datfmt-iso/).
// Historial: antes se rechazaba con RNF8101 (firewall); decisión superada.
// Esperado pendiente de captura en pub400 → compile/rpg/datfmt-iso/.
dcl-s fecha char(10);

fecha = '2026-09-08';
dsply fecha;
