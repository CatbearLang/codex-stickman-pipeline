# Cómo se construyó

🇬🇧 [English](HOW_IT_WAS_BUILT.md)

Este documento explica **por qué** existe Codex Stickman Pipeline, **cómo** funciona cada etapa y las decisiones de ingeniería detrás. El mapa de módulos está en [ARCHITECTURE.md](ARCHITECTURE.md).

## El problema

Hacer videos explicativos (estilo stickman / pizarra) a mano es lento: escribir el guion, grabar la voz, dibujar o generar una imagen cada pocos segundos, sincronizar y editar. Casi todo es repetible. El objetivo fue **un solo comando** —`stickman run`— que convierta un tema en un MP4 1080p terminado, con miniatura y descripción, con costo predecible y corridas reproducibles.

## Etapa por etapa

| Etapa | Entrada → Salida | Idea clave |
|---|---|---|
| **Banco de temas** | archivo de temas → siguiente tema | Lock exclusivo del sistema + diario del trabajo: si una corrida se cae, se retoma el mismo tema sin gastar otro |
| **Guion** | tema → guion JSON (escenas → conceptos visuales) | La salida del LLM se valida contra `script-schema.json`; los quality gates revisan ritmo, palabras y densidad de imágenes **antes** de cualquier llamada paga |
| **Voz** | guion → audio por escena | Edge TTS por defecto (sin clave); ElevenLabs o cualquier TTS HTTP con la misma interfaz; verificación de duración |
| **Alineación** | audio → tiempos por palabra | Límites de palabra de Edge o faster-whisper local; `timeline.py` asigna cada concepto a un rango (~1 imagen cada 12 s) |
| **Imágenes** | conceptos → imágenes | Una sola llamada por lote; registro de presupuesto persistente; caché por trabajo + prompt + referencias + proveedor + tamaño + calidad, más hash del PNG |
| **Composición** | imágenes + audio → MP4 | Grafo de filtros FFmpeg: movimiento de cámara, transiciones, overlays, efectos procedurales, música con ducking y normalización de volumen |
| **Verificación** | MP4 → reporte | Chequeos con ffprobe en `technical-check.json`; copia 480p y miniatura |

## Decisiones de diseño

1. **Costo con falla cerrada.** Nada pago se ejecuta sin `--live`. El proveedor se elige explícitamente, sin cambiar en silencio a una API paga. Las imágenes se estiman y se descuentan de un registro *antes* de generarse, así dos corridas no se pasan del límite juntas.
2. **Interfaces chicas de proveedores.** Guion, voz e imágenes detrás de `provider_base.py` y factories: sumar un servicio es una clase y los tests usan dobles.
3. **Etapas idempotentes y reanudables.** Hashes de contenido y un manifiesto permiten reutilizar trabajo después de un corte o un ajuste.
4. **Sin manejo de credenciales.** La autenticación de Codex queda dentro del CLI oficial; las API keys solo vienen de variables de entorno. Un escáner de secretos forma parte de los tests.
5. **Demo sin cuentas.** Un render con imágenes procedurales y tonos de prueba funciona sin ninguna cuenta.
6. **Recursos propios.** Los efectos de sonido son procedurales; la música y las fuentes incluidas llevan su licencia en `THIRD_PARTY_NOTICES.md`.

## Tests

`pytest -q` corre sin conexión con dobles para cada proveedor: **94 pasan, 2 omitidos**. Cubre locks del banco de temas, validación de config, contratos de proveedores, esquema del guion, gates de ritmo y presupuesto (incluida una carrera entre dos corridas), caché de imágenes, render con FFmpeg, verificación de salida y el escáner de secretos.

## Forma de trabajo

Hecho en Python como herramienta de línea de comandos, iterando con asistentes de programación con IA: cada cambio se especificó, se implementó y se comprobó con los tests y renderizando videos reales. Los fallos de corridas reales (riesgo de sobrecosto, cortes a mitad de trabajo, ritmo lento) se convirtieron en gates y tests en lugar de reglas manuales.

## Próximos pasos

Formato vertical 9:16, más proveedores de voz e imagen y un pequeño panel web (ver Roadmap en el README).
