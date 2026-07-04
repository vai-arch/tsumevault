# TsumeVault v2
# Plan Maestro de Refactorización

Versión: 1.0
Fecha: Julio 2026

---

# Objetivo

Este documento define el proceso oficial para ejecutar la refactorización de TsumeVault.

El objetivo NO es reescribir la aplicación.

El objetivo es:

- eliminar bugs críticos
- mejorar la arquitectura
- aumentar la seguridad
- facilitar el mantenimiento futuro
- mantener compatibilidad completa
- no introducir regresiones

Todo cambio debe cumplir estos principios.

---

# Filosofía del proyecto

TsumeVault es un sistema estable en producción.

Funciona.

Los cambios deben ser:

- pequeños
- aislados
- verificables
- reversibles

Nunca se harán cambios masivos.

Nunca se modificarán varias áreas importantes al mismo tiempo.

Siempre existirá una versión estable.

---

# Principios

## 1. Cambios mínimos

Cada línea modificada aumenta el riesgo.

La mejor solución es la que modifica menos código.

---

## 2. Una fase = un objetivo

Nunca mezclar:

- seguridad
- sync
- arquitectura
- optimización

Cada fase debe tener un único objetivo.

---

## 3. Compatibilidad

Todo comportamiento existente debe mantenerse salvo que la auditoría indique lo contrario.

---

## 4. Nada de refactors estéticos

No cambiar:

- nombres
- orden de funciones
- formato
- estilo

si no es necesario.

---

## 5. Nunca avanzar con errores

Si una prueba falla:

la siguiente fase queda bloqueada.

---

# Flujo de trabajo

Cada fase sigue exactamente este proceso.

PLAN

↓

Implementación

↓

Autorevisión

↓

Pruebas

↓

Git Commit

↓

Nueva fase

Nunca alterar este orden.

---

# Organización de Claude

Proyecto:

TsumeVault v2 Refactor

Archivos permanentes:

- AUDITORIA_TSUMEVAULT_v2.md
- tsumevault.html
- tsumevault_server.py
- db_schema.sql
- PLAN_MAESTRO.md
- PROGRESO.md

Cada fase se desarrolla en un chat independiente.

Nunca utilizar un único chat para todo el proyecto.

---

# Orden de ejecución

## Fase 0

Planificación

Objetivo:

analizar dependencias

No escribir código.

Resultado esperado:

plan definitivo.

---

## Fase 1

Seguridad

Incluye:

- autenticación
- CORS
- validación
- límites
- ThreadingHTTPServer

Debe terminar con:

servidor seguro.

---

## Fase 2

Bugs críticos

Incluye:

3.5

3.6

3.7

3.8

3.9

3.10

3.11

3.12

NO tocar todavía el Sync.

---

## Fase 3

Persistencia

Incluye:

saveDB

debounce

IndexedDB

seguridad de escritura

---

## Fase 4

Sync v2

La fase más importante.

Incluye:

R1

R2

Todo el protocolo nuevo.

No mezclar con modularización.

---

## Fase 5

Base de datos

Tipos

Índices

Migraciones

CHECK

UUID

FK

---

## Fase 6

Limpieza

Eliminar:

endpoints muertos

prints

duplicaciones pequeñas

variables inútiles

---

## Fase 7

Optimización

N+1

queries

snapshot

saveDB

push

window functions

---

## Fase 8

Modularización

Extraer uno a uno:

sm2.js

repo.js

sync.js

board.js

panels.js

modals.js

state.js

Nunca extraer varios módulos simultáneamente.

---

## Fase 9

Pulido

Documentación

comentarios

nombres

tests

limpieza final

---

# Regla de implementación

Antes de escribir código el modelo debe explicar:

- qué va a cambiar
- por qué
- riesgos
- archivos afectados

Después implementará el cambio.

Nunca al revés.

---

# Regla de alcance

Si durante una fase aparecen mejoras adicionales:

NO implementarlas.

Anotarlas para fases futuras.

---

# Revisión obligatoria

Después de implementar:

el modelo hará una revisión crítica del código.

Debe buscar:

- bugs
- edge cases
- regresiones
- duplicaciones
- código muerto

No debe asumir que su código es correcto.

---

# Pruebas

Ninguna fase termina sin pruebas.

Cada fase debe generar una checklist.

Ejemplo:

Servidor inicia.

Frontend carga.

Sync funciona.

Review funciona.

Free Practice funciona.

Runs funcionan.

Stats funcionan.

Offline funciona.

Móvil funciona.

---

# Git

Siempre:

una fase

↓

un commit

Nunca:

varias fases

↓

un commit

---

# Commits

Ejemplos:

Phase 1 Security

Phase 2 Critical Bugs

Phase 3 Persistence

Phase 4 Sync V2

Phase 5 Database

Phase 6 Cleanup

Phase 7 Performance

Phase 8 Modularization

Phase 9 Final Polish

---

# Cambio de chat

Cada fase comienza un chat nuevo.

El nuevo chat debe asumir únicamente:

- el código actual
- los archivos del proyecto
- el progreso indicado en PROGRESO.md

Nunca depender de conversaciones antiguas.

---

# Criterios para cerrar una fase

Una fase solo puede cerrarse cuando:

✓ Compila

✓ Arranca

✓ Todas las pruebas pasan

✓ Claude revisa su propio código

✓ Se corrigen los problemas encontrados

✓ Git Commit realizado

Solo entonces puede iniciarse la siguiente fase.

---

# Regla más importante

La prioridad es:

Fiabilidad

↓

Corrección

↓

Mantenibilidad

↓

Rendimiento

↓

Elegancia

Nunca sacrificar estabilidad por código más bonito.

---

FIN DEL DOCUMENTO