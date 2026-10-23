---
name: Vuelos Mérida
description: Monitor de tarifas de un solo viaje (Puebla y CDMX ⇄ Mérida, diciembre 2026), bordado como huipil yucateco.
colors:
  ground: "#f6f7f3"
  surface: "#ffffff"
  raised: "#eef0ea"
  line: "#e1e4dc"
  rule: "#edefe9"
  control: "#c9cdc3"
  ink: "#171a17"
  muted: "#545a52"
  faint: "#656b63"
  shell: "#1d4d33"
  shell-ink: "#f3f6f1"
  shell-muted: "#b9cbbd"
  glass-shell-muted: "#d6e2d9"
  verde: "#2f8a52"
  amarillo: "#d9a521"
  rosa: "#d43f7a"
  rojo: "#b3242c"
  good: "#23784a"
  bad: "#b3242c"
  seg1: "#171a17"
  seg2: "#7c857a"
  seg3: "#c3cabe"
  notice-bg: "#fff8e6"
  notice-line: "#f0d48a"
  notice-ink: "#7a4a07"
  grid: "#e3e6de"
typography:
  answer:
    fontFamily: "Hanken Grotesk, ui-sans-serif, system-ui, -apple-system, Segoe UI, sans-serif"
    fontSize: "34px"
    fontWeight: 700
    lineHeight: 1.05
    letterSpacing: "-0.02em"
    fontFeature: "tnum"
  section:
    fontFamily: "Hanken Grotesk, ui-sans-serif, system-ui, sans-serif"
    fontSize: "16px"
    fontWeight: 600
  body:
    fontFamily: "Hanken Grotesk, ui-sans-serif, system-ui, sans-serif"
    fontSize: "14px"
    fontWeight: 400
    lineHeight: 1.45
  label:
    fontFamily: "Hanken Grotesk, ui-sans-serif, system-ui, sans-serif"
    fontSize: "13px"
    fontWeight: 500
  small:
    fontFamily: "Hanken Grotesk, ui-sans-serif, system-ui, sans-serif"
    fontSize: "12px"
    fontWeight: 400
  micro:
    fontFamily: "Hanken Grotesk, ui-sans-serif, system-ui, sans-serif"
    fontSize: "11px"
    fontWeight: 600
rounded:
  stitch: "3px"
  cell: "4px"
  control: "6px"
  panel: "8px"
  capsule: "999px"
spacing:
  gap: "16px"
  pad: "20px"
  pad-sm: "16px"
  section: "32px"
components:
  panel:
    backgroundColor: "{colors.surface}"
    rounded: "{rounded.panel}"
    padding: "20px"
  button-default:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.ink}"
    typography: "{typography.body}"
    rounded: "{rounded.control}"
    padding: "0 14px"
    height: "34px"
  button-default-disabled:
    backgroundColor: "{colors.raised}"
    textColor: "{colors.faint}"
  button-primary:
    backgroundColor: "{colors.ink}"
    textColor: "{colors.surface}"
    rounded: "{rounded.control}"
    padding: "0 14px"
    height: "34px"
  button-on-shell:
    backgroundColor: "{colors.shell-ink}"
    textColor: "{colors.shell}"
    rounded: "{rounded.capsule}"
    padding: "0 16px"
    height: "34px"
  keybtn:
    textColor: "{colors.shell-ink}"
    rounded: "{rounded.capsule}"
    padding: "0 12px"
    height: "34px"
  input:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.ink}"
    typography: "{typography.body}"
    rounded: "{rounded.control}"
    padding: "0 10px"
    height: "34px"
  input-disabled:
    backgroundColor: "{colors.raised}"
    textColor: "{colors.muted}"
  matrix-cell:
    rounded: "{rounded.cell}"
    height: "62px"
  matrix-cell-chip:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.ink}"
    rounded: "{rounded.stitch}"
    padding: "3px 6px"
  tab-selected:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.ink}"
    rounded: "{rounded.cell}"
    padding: "6px 12px"
  pill-good:
    textColor: "{colors.good}"
    rounded: "{rounded.capsule}"
    padding: "2px 7px"
  notice:
    backgroundColor: "{colors.notice-bg}"
    textColor: "{colors.notice-ink}"
    rounded: "{rounded.control}"
    padding: "10px 12px"
  toast:
    textColor: "{colors.surface}"
    rounded: "{rounded.capsule}"
    padding: "10px 16px"
---

# Design System: Vuelos Mérida

## Overview

**Creative North Star: "El huipil de precios"**

La matriz ida×vuelta es el producto, y está bordada: cada casilla es una puntada en cruz teñida con un hilo de bordado yucateco que funciona como dato, no como adorno. Sobre fondo de manta, con tinta de hilo negro, un solo sans de trabajo con cifras tabulares. La banda verde oscuro del encabezado es el único bloque de color sólido de la pantalla.

Densidad de herramienta (modo Operate): paneles blancos con borde fino de 1px, separadores de regla en lugar de tarjetas anidadas, cifras primero. La capa de navegación flota en vidrio (el lenguaje Liquid Glass de Apple, pedido explícitamente por el usuario y traducido a CSS), confinada a lo que flota sobre el contenido; el contenido nunca lleva vidrio.

El movimiento solo comunica estado (presión, selección, progreso), corto y con salida suave.

**Key Characteristics:**
- Puntada en cruz (máscara SVG en X de 9px) como textura de dato en casillas y leyenda.
- Hilos de color = cuartiles de precio; tinta negra = la respuesta.
- Un solo tipo, Hanken Grotesk, con `tabular-nums` en toda cifra.
- Vidrio solo en la capa flotante (banda, token, pasos, toast), con caídas sólidas.
- Tema claro y oscuro completos por tokens en `:root`.

## Colors

Manta y tinta de hilo negro, con cuatro hilos de bordado reservados a los datos y un verde oscuro de banda.

### Primary
- **Verde de banda** (shell): fondo de la banda superior, `accent-color` del cuerpo y color del favicon y `theme-color`. Texto sobre ella en **Blanco de banda** (shell-ink) y **Verde niebla** (shell-muted; `glass-shell-muted` sobre vidrio).
- **Tinta de hilo negro** (ink): texto, botón primario, relleno de la barra de meta, línea del historial, borde de casilla seleccionada.

### Secondary: hilos de dato
- **Hilo verde** (verde): cuartil más barato; también anillo de foco y tinte de fila elegida (7%).
- **Hilo amarillo** (amarillo): segundo cuartil; también paso "ahora" y punto de salud viejo/ocupado.
- **Hilo rosa** (rosa): tercer cuartil.
- **Hilo rojo** (rojo): cuartil más caro.
- **Bueno / Malo** (good / bad): veredicto contra la meta, deltas, línea de meta del historial, píldora "en meta", errores.

### Neutral
- **Manta** (ground): fondo de página. **Blanco** (surface): paneles, chips de casilla, halo de etiquetas. **Manta alzada** (raised): pistas, pestañas, esqueletos, deshabilitado.
- **Línea** (line) borde de panel; **Regla** (rule) separadores internos; **Control** (control) borde de inputs y botones; **Retícula** (grid) líneas del historial.
- **Gris tinta** (muted) texto secundario; **Gris hilo** (faint) metadatos y ejes.
- **Segmentos** seg1/seg2/seg3: barra apilada del desglose (vuelos Puebla / camión y maletas / vuelos CDMX).
- **Aviso** notice-bg / notice-line / notice-ink: avisos ámbar.

Tema oscuro: los mismos nombres se redefinen bajo `@media (prefers-color-scheme: dark) { :root:not([data-theme="light"]) }` y, de forma idéntica, en `:root[data-theme="dark"]` (ground #101310, surface #171b17, raised #20251f, ink #ecefe9, shell #173d29, verde #4fb377, amarillo #e6b83f, rosa #ec6a9c, rojo #e2565d, good #5cc287, bad #ec6a70, notice-bg #2a2412, notice-ink #f0cf80; lista completa en el sidecar), con `color-scheme: dark`.

### Named Rules
**La regla del hilo como dato.** Verde, amarillo, rosa y rojo solo marcan precio. En la matriz, tal como está construida, las casillas válidas se agrupan por cuartil de sus totales (verde = cuartil más barato … rojo = más caro) y la leyenda muestra el rango en pesos de cada banda. Pendiente de decisión del usuario: bandear contra la meta en lugar de por cuartil.

**La regla de la tinta.** La respuesta (total, barra de meta, línea del historial, selección) va en tinta negra, nunca en un hilo de color.

## Typography

**Fuente única:** Hanken Grotesk (400/500/600/700, Google Fonts) con caída a `ui-sans-serif, system-ui, -apple-system, "Segoe UI", sans-serif`.

**Character:** grotesca de trabajo, cálida y legible al sol en un teléfono; las cifras son tabulares para que los totales se alineen en columna.

### Hierarchy
- **Respuesta** (700, 34px, 1.05, -0.02em; 30px bajo 640px): el mejor total del grupo. Su unidad acompañante va a 15px/400.
- **Sección** (600, 16px): títulos de panel y marca de la banda.
- **Cuerpo** (400, 14px, 1.45): texto, tablas, inputs, botones (500).
- **Etiqueta** (500, 13px): etiquetas de campo, pestañas, avisos, cifras de casilla (600), títulos de la respuesta.
- **Pequeño** (12px): metadatos, ejes del historial, encabezados de tabla, leyenda.
- **Micro** (600, 11px): píldoras, "viajan juntos", subtítulo de casilla, casilla vacía (400).

Ramp de uso real: 34 / 16 / 14 / 13 / 12 / 11, más 18px en las cifras del pie del historial y 15px en la unidad de la respuesta. `--fs-title` (24px) está declarado pero ningún elemento lo usa.

### Named Rules
**La regla tabular.** Toda cifra lleva `font-variant-numeric: tabular-nums` (clase `num` o texto del gráfico).

## Layout

Contenedor centrado de 1200px con 16px laterales (o el safe-area si es mayor). `main` apila bloques con 32px; la fila superior es una rejilla 5fr / 6fr (respuesta a la izquierda, matriz a la derecha) con 16px de separación. Relleno de panel 20px (16px bajo 640px).

Matriz: columna de fechas de 74px + `repeat(var(--cols), minmax(0,1fr))`, 6px de separación, casillas de 62px.

- **≤900px:** la fila superior pasa a una columna; las filas de reglas (300px + campos) se apilan.
- **≤640px:** columna de fechas de 44px y separación de 4px; casillas de 50px sin subtítulo; gráfico de 190px; la tabla de opciones deja de ser tabla y cada fila es una rejilla de dos líneas (`1fr auto`), con columnas `hide-sm` ocultas; todo control táctil (botones, inputs, selects, pestañas, chips, casillas de verificación, enlaces del desglose, botones de enlace) llega a 44px de alto.

## Elevation & Depth

Plano por defecto: profundidad por tono (manta → blanco → manta alzada) y bordes de 1px. Las sombras existen solo en lo que flota y son suaves y difusas.

### Shadow Vocabulary
- **Capa de navegación** (`box-shadow: 0 8px 24px -18px rgba(0,0,0,.4)`) más un hilo inferior de 2px (1px de luz blanca al 12% sobre 1px de sombra negra al 30%).
- **Toast** (`box-shadow: 0 10px 28px -14px rgba(0,0,0,.45)`).
- **Chip de casilla** (`box-shadow: 0 1px 2px rgba(0,0,0,.08)`): despega la cifra de la puntada.

### Named Rules
**La regla del vidrio flotante.** Solo `.navlayer` (banda verde, barra del token, pasos de la búsqueda; pegajosa arriba) y el toast llevan vidrio: `backdrop-filter: blur(18px) saturate(170%)`, banda al 90% de shell, planos al 90% de blanco teñido 7% hacia shell, toast al 84% de tinta, borde de luz blanca al 18%. La opacidad es alta a propósito para pasar AA aunque pase una casilla rosa por detrás. Caída a sólido sin `backdrop-filter`, con `prefers-reduced-transparency: reduce` o con `prefers-contrast: more`. Respuesta, matriz, historial, tablas y reglas nunca llevan vidrio.

## Shapes

Esquinas suaves y pequeñas que crecen con el tamaño del objeto: 3px en chips de puntada y leyenda, 4px en casillas y pestañas internas, 6px en controles y avisos, 8px en paneles. La cápsula (999px) es el lenguaje de la capa de vidrio y de los marcadores: botones de la banda, toast, píldoras, barra de meta. Bordes de 1px; la selección engrosa a 2px en tinta; lo vacío es discontinuo.

## Components

### Botones
- **Normal:** blanco, borde control, 34px, radio 6px, 500/14px. **Primario:** tinta con texto blanco. **Deshabilitado:** manta alzada y texto faint.
- **En la banda:** "Buscar ahora" en cápsula blanco de banda con texto verde (600); "Editar" (keybtn) en cápsula translúcida (shell-ink al 10%, 18% en hover) con borde de luz.
- **Botón de enlace:** texto muted 12px subrayado ("Volver a la mejor", "Reintentar", "Ver más").
- **Presión:** `scale(0.97)` en 140ms.

### Respuesta y barra de meta
Título 13px muted, total en Respuesta, hechos 13px. Barra de 8px en cápsula sobre manta alzada con relleno en tinta (ancho animado 250ms); la marca de meta es un trazo de tinta de 2px colocado en su posición real de la escala, con su etiqueta centrada debajo. Veredicto en good u bad. Barra apilada de 10px con segmentos seg1–3 separados 2px.

### Desglose (tramos)
Filas de muestra de 10px + texto + precio a la derecha, separadas por regla; enlace a Google Flights bajo el precio; la fila total va en 700. "Viajan juntos" en micro good.

### Matriz de punto de cruz
- **Casilla:** fondo del hilo de su banda al 12% sobre blanco, puntada en X del hilo al 90% de opacidad, chip blanco centrado con el total (600/13px) y subtítulo micro ("mejor", "en meta" o noches).
- **Estados:** hover borde control; seleccionada `aria-pressed` borde de 2px en tinta; mejor subtítulo en tinta 600; vacía (fuera del rango de noches) transparente, borde discontinuo, sin puntada, texto faint 11px.
- **Leyenda:** muestra de puntada de 14px por banda con su rango, más notas de punteado y fechas excluidas.

### Historial
SVG de 230px (190px en móvil): retícula grid, línea de meta discontinua en good, línea de precio de 2px en tinta, punto final de 4px. Las etiquetas se pintan después de la línea con halo de 4px del color de superficie (`paint-order: stroke`), así nunca quedan bajo el trazo. Tooltip en tinta. Pestañas segmentadas sobre manta alzada; la elegida en blanco con borde. Pie de cuatro cifras de 18px con delta en good/bad/faint.

### Tabla de opciones
Encabezados de 12px muted ordenables, celdas de 14px (detalle de 12px muted) con regla superior, fila elegida teñida de verde al 7%, píldoras good/neutras. Bajo 640px se vuelve filas de dos líneas.

### Formulario de reglas y barra de guardado
Filas de sección (descripción de 300px máx. 40ch + rejilla de campos `minmax(150px,1fr)`). Inputs de 34px, radio 6px, borde control; deshabilitados en manta alzada. Chips de aeropuerto con borde que pasa a tinta y fondo alzado al marcarse. En modo lectura los campos no reciben puntero y lo editable se oculta. La barra de guardado alinea a la derecha Deshacer, Guardar y el primario "Guardar y buscar", con el metadato a la izquierda.

### Pasos de la búsqueda
Franja de vidrio con En cola → Buscando → Publicando → Listo, puntos de 7px unidos por trazos de 14px: pendiente faint/control, hecho muted/verde, ahora tinta 600/amarillo, fallo bad 600/bad. El punto cambia de color en 200ms.

### Barra del token
Plano de vidrio con etiqueta, input de contraseña flexible (260–420px), "Usar token" primario, Cancelar y error en bad.

### Avisos y salud
Punto de salud de 8px en la banda (ok, viejo, ocupado con pulso, caído). Avisos ámbar de radio 6px: precios viejos (stale, arriba de la página), "necesita búsqueda" y presupuesto de SerpApi (en reglas).

### Carga y error
Carga con el mismo layout: barras planas de manta alzada del tamaño real del contenido final, casillas planas, gráfico plano; leyenda y pies ocultos. El error vive dentro del bloque que falló: mensaje en bad 600, explicación muted y "Reintentar".

### Toast
Cápsula de vidrio en tinta al 84%, abajo al centro (respeta safe-area), texto blanco 13px; entra subiendo 12px (opacidad 180ms, posición 220ms).

### Movimiento
140–250ms, solo para estado, con `cubic-bezier(0.23, 1, 0.32, 1)`; los cambios de color usan `ease` a 150ms. `prefers-reduced-motion: reduce` anula transiciones y animaciones.

## Do's and Don'ts

### Do:
- **Do** reservar verde, amarillo, rosa y rojo para bandas de precio y estado; la respuesta va en tinta.
- **Do** poner `tabular-nums` en cada cifra.
- **Do** confinar el vidrio a la capa flotante, con opacidad ≥84% y caída sólida en los tres casos (sin soporte, menos transparencia, más contraste).
- **Do** marcar la meta en su posición real de la escala, no al final de la barra.
- **Do** dar 44px de alto a todo control táctil bajo 640px.
- **Do** cargar con barras planas del tamaño final y mostrar el error dentro del bloque que falló, con "Reintentar".
- **Do** definir todo color nuevo como token en `:root` con su par oscuro en ambos bloques de tema.

### Don't:
- **Don't** poner vidrio en paneles, matriz, historial, tablas o reglas.
- **Don't** usar un segundo tipo de letra.
- **Don't** animar fuera de un cambio de estado ni pasar de 250ms.
- **Don't** dejar una etiqueta del gráfico bajo la línea; píntala después y con halo de superficie.
