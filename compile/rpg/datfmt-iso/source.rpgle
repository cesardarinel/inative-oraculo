**FREE
ctl-opt DFTACTGRP(*NO) ACTGRP(*NEW) OPTION(*NODEBUGIO) DATFMT(*ISO);

// DATFMT(*ISO) — formato de fecha explícito no modelado por iNative.
// IBM i real lo compila ( врождён formato ISO); iNative debe fallar
// determinista con RNF8101 antes de GCC (firewall del compilador).
// Esperado pendiente de captura en pub400 → esperado/RPGLE.invalidos.datfmt-iso.json
// (caso HELLOS.SQLRPGLE original de iNative).
dcl-s fecha char(10);

fecha = '2026-09-08';
dsply fecha;
