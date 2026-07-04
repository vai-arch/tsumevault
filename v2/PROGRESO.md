# TsumeVault v2
# PROGRESO.md

Versión del documento: 1.0

Este documento representa el estado oficial del proyecto.

Toda conversación nueva con Claude debe comenzar leyendo este documento.

Nunca confiar en el contexto de conversaciones anteriores.

---

# Estado actual

Versión estable:

v1.x (pre-refactor)

Último commit estable:

<rellenar>

Estado:

🟢 ESTABLE

---

# FASE -1
# BASELINE Y PRUEBAS DE REGRESIÓN

Estado:

⬜ Pendiente

Objetivo:

Construir una batería de pruebas manuales para poder detectar inmediatamente cualquier regresión durante la refactorización.

Esta fase NO modifica código.

---

# Checklist general

## Inicio

□ El servidor arranca correctamente.

□ No aparecen errores en consola.

□ El frontend carga correctamente.

□ La PWA funciona.

□ El Service Worker se registra.

---

## Base de datos

□ La base local se abre.

□ IndexedDB contiene la base.

□ Se guarda correctamente.

□ Reiniciar navegador mantiene todos los datos.

---

## Sincronización

□ El botón Sync funciona.

□ Pull funciona.

□ Push funciona.

□ Snapshot funciona.

□ Dos sincronizaciones consecutivas no generan errores.

□ No aparecen duplicados.

---

## Colecciones

□ Se muestran correctamente.

□ Expandir colección funciona.

□ Contraer funciona.

□ Filtros funcionan.

□ Estadísticas aparecen correctamente.

---

## Capítulos

□ Se muestran correctamente.

□ Cambiar visibilidad funciona.

□ Persistencia correcta tras reinicio.

---

## Problemas

□ Carga correcta.

□ SGF correcto.

□ Navegación correcta.

□ Restart funciona.

□ Back funciona.

□ Ghost stone correcto.

□ Tap confirm correcto.

---

## Free Practice

□ Se puede iniciar.

□ Cambiar filtros funciona.

□ Todos los problemas cargan.

□ Correctos registrados.

□ Incorrectos registrados.

□ Finaliza correctamente.

---

## Review

□ Se puede iniciar.

□ Sólo aparecen problemas pendientes.

□ El algoritmo SM2 funciona.

□ Las fechas cambian correctamente.

□ Finaliza correctamente.

---

## Runs

□ Crear run.

□ Reanudar run.

□ Finalizar run.

□ Borrar run.

□ Estadísticas correctas.

---

## Estadísticas

□ Último run.

□ Global.

□ Maturity.

□ Difficulty.

□ Struggling.

□ By Level.

---

## Juegos

□ Lista correcta.

□ Carga correcta.

□ Navegación correcta.

---

## Configuración

□ Tema.

□ Sonido.

□ Sync.

□ Presets.

---

## Offline

□ Funciona sin conexión.

□ Se pueden hacer intentos.

□ Se guarda la información.

□ Al volver la conexión sincroniza correctamente.

---

## Multidispositivo

□ PC → móvil.

□ Móvil → PC.

□ No aparecen duplicados.

□ No desaparecen datos.

---

# FASE 0

Estado:

✅ COMPLETADA

Resultado:

- Plan maestro aprobado.
- Metodología de trabajo definida.
- CLAUDE.md creado.
- PLAN_MAESTRO.md creado.
- PROGRESO.md creado.
- Orden de ejecución aprobado.

---

# FASE 1

Estado:

⬜ Pendiente

Objetivo:

Seguridad.

Commit esperado:

phase-1-security

---

# FASE 2

Estado:

⬜ Pendiente

Objetivo:

Corrección de bugs críticos.

Commit esperado:

phase-2-critical-bugs

---

# FASE 3

Estado:

⬜ Pendiente

Objetivo:

Persistencia.

Commit esperado:

phase-3-persistence

---

# FASE 4

Estado:

⬜ Pendiente

Objetivo:

Sync V2.

Commit esperado:

phase-4-sync-v2

---

# FASE 5

Estado:

⬜ Pendiente

Objetivo:

Base de datos.

Commit esperado:

phase-5-database

---

# FASE 6

Estado:

⬜ Pendiente

Objetivo:

Limpieza.

Commit esperado:

phase-6-cleanup

---

# FASE 7

Estado:

⬜ Pendiente

Objetivo:

Optimización.

Commit esperado:

phase-7-performance

---

# FASE 8

Estado:

⬜ Pendiente

Objetivo:

Modularización.

Commit esperado:

phase-8-modularization

---

# FASE 9

Estado:

⬜ Pendiente

Objetivo:

Pulido final.

Commit esperado:

phase-9-final-polish

---

# Reglas

Nunca comenzar una fase si la anterior no está:

✅ Implementada

✅ Revisada

✅ Probada

✅ Commit realizado

---

# Historial

## Cambios realizados

(Ninguno todavía)

---

# Problemas conocidos

Se utilizará este apartado para anotar incidencias encontradas durante la refactorización.

---

# Notas para Claude

Antes de comenzar cualquier fase:

1. Leer PLAN_MAESTRO.md

2. Leer PROGRESO.md

3. Leer la auditoría

4. Confirmar la fase actual

5. Explicar el plan

6. Esperar aprobación antes de modificar el código

Nunca asumir el estado del proyecto a partir de conversaciones anteriores.