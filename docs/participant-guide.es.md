# Cómo rellenar un FIP — Guía para los participantes

**Gestor de FIP** ayuda a una comunidad de investigación a registrar, con precisión y de manera comparable, qué tecnologías utiliza realmente para hacer que sus datos y metadatos sean **L**ocalizables, **A**ccesibles, **I**nteroperables y **R**eutilizables. El resultado es un **Perfil de Implementación FAIR (FIP)**: 21 preguntas cortas, una elección tecnológica por pregunta, exportable como JSON, CSV y RDF.

Esta guía es para la persona que **rellena** un FIP: en un taller o por su cuenta. No asume conocimientos técnicos ni conocimientos previos sobre FAIR más allá de las cuatro letras.

> **No hay que instalar nada.** Gestor de FIP funciona en el navegador de su teléfono o portátil. No necesita una cuenta para rellenar un FIP, ni tiene que terminarlo de una vez.

> **Su trabajo se guarda automáticamente.** No hay ningún botón "enviar". Cada cambio se guarda un momento después de realizarlo: fíjese en el indicador *Guardado*. Cerrar la pestaña no hace que se pierda el trabajo, siempre que conserve el enlace (vea [§6](#6-volver-más-tarde-y-en-otro-dispositivo)).

Si está en el taller CONFOA y quiere una sola página imprimeible en lugar de esta guía, utilice [`workshop/participant-handout.md`](workshop/participant-handout.md), que cubre el mismo contenido en inglés y pt-PT en una hoja.

---

## Tabla de contenidos

1. [Qué está describiendo (conceptos clave)](#1-qué-está-describiendo-conceptos-clave)
2. [Tres formas de empezar](#2-tres-formas-de-empezar)
3. [El editor de un vistazo](#3-el-editor-de-un-vistazo)
4. [Recorrido guiado: rellene su primer FIP](#4-recorrido-guiado-rellene-su-primer-fip)
   - [Paso 1 — Elija su área](#paso-1--elija-su-área)
   - [Paso 2 — Asigne un nombre a su comunidad](#paso-2--asigne-un-nombre-a-su-comunidad)
   - [Paso 3 — Lea la pregunta](#paso-3--lea-la-pregunta)
   - [Paso 4 — Marque una opción sugerida](#paso-4--marque-una-opción-sugerida)
   - [Paso 5 — Responda con sus propias palabras](#paso-5--responda-con-sus-propias-palabras)
   - [Paso 6 — Cuando la pregunta no aplica](#paso-6--cuando-la-pregunta-no-aplica)
   - [Paso 7 — Cuando está planificado en lugar de en uso](#paso-7--cuando-está-planificado-en-lugar-de-en-uso)
   - [Paso 8 — Añada más de una respuesta](#paso-8--añada-más-de-una-respuesta)
   - [Paso 9 — Siga su progreso](#paso-9--siga-su-progreso)
   - [Paso 10 — Comparta su FIP](#paso-10--comparta-su-fip)
5. [Los cinco tipos de respuesta](#5-los-cinco-tipos-de-respuesta)
6. [Volver más tarde, y en otro dispositivo](#6-volver-más-tarde-y-en-otro-dispositivo)
7. [Crear una cuenta (opcional)](#7-crear-una-cuenta-opcional)
8. [Elegir su idioma](#8-elegir-su-idioma)
9. [Descargar y compartir su FIP](#9-descargar-y-compartir-su-fip)
10. [Solución de problemas](#10-solución-de-problemas)
11. [Atribución](#11-atribución)

---

## 1. Qué está describiendo (conceptos clave)

No se le pide lo que **debería** hacer, ni lo que dice la política de su institución. Se le pide qué es lo que su comunidad **utiliza realmente hoy** — y, cuando corresponda, qué planea utilizar. Una respuesta honesta de "aún no lo hemos decidido" es mejor que una respuesta aspiracional.

| Término | Qué significa para usted |
|---|---|
| **FIP** | El perfil completo que está rellenando: las respuestas de su comunidad a las 21 preguntas. |
| **FER** (FAIR Enabling Resource) | La tecnología, servicio o estándar específico que nombra como respuesta: la cosa que realiza el trabajo de habilitación FAIR. **DOI** es un FER; también lo son **Dublin Core**, **OWL** o **CC BY 4.0**. |
| **Comunidad** | A qué comunidad describe: un grupo de investigación, un proyecto, un consorcio, un instituto. Le da nombre al principio. |
| **Pregunta** | Una de las 21, agrupadas por las cuatro letras de FAIR. Cada una pregunta por un tipo de recurso: "¿qué esquemas de identificadores para sus datos?", "¿qué licencia para sus metadatos?" |
| **Declaración** | Una respuesta individual a una pregunta: *este* recurso, con un estado, opcionalmente con una nota. Una pregunta puede tener varias declaraciones. |
| **Estado** | Si el recurso está en uso actualmente, planificado, en desarrollo o a punto de ser sustituido. |
| **Área** | Un enfoque de dominio de investigación del cuestionario (ómica, biodiversidad, agricultura, salud pública, enfermería…). Cada área sugiere una breve lista de opciones adaptadas a ese campo. |

> **Por qué "un recurso por pregunta" es importante.** Un FIP es útil porque es comparable. Cuando cincuenta comunidades nombran cada una su esquema de identificadores real, puede ver la convergencia y la divergencia de un vistazo: algo imposible con la prosa de políticas de libre formato.

---

## 2. Tres formas de empezar

| Usted está… | Haga esto | ¿Necesita cuenta? |
|---|---|---|
| En un taller, con un código o código QR en pantalla | Escanee el código QR o abra el sitio y escriba el **código de acceso** en la página de inicio | No |
| Trabajando por su cuenta, ahora mismo | Abra el sitio y elija **Empezar un FIP** (o vaya a `/fips/new`), luego seleccione un cuestionario | No |
| Volviendo al trabajo que empezó | Use su **Enlace de edición**, o la lista **FIPs en este dispositivo** en la página de inicio | No |

![La página de inicio de Gestor de FIP en un teléfono, con el cuadro del código de acceso](images/home-join-code.png)

Las tres opciones le llevan al mismo editor. Nunca es necesario tener una cuenta para rellenar un FIP: solo se vuelve útil más tarde, si quiere que todos sus FIPs estén reunidos en un mismo espacio de trabajo ([§7](#7-crear-una-cuenta-opcional)).

> **Unirse a una sesión vs. empezar solo.** Una *sesión* es un ejercicio grupal facilitado: el facilitador ve los FIPs a medida que se rellenan y puede exportarlos todos juntos. Un FIP *independiente* pertenece solo a usted. Las preguntas y el editor son idénticos.

---

## 3. El editor de un vistazo

El editor de FIP tiene cuatro partes, de arriba abajo:

![El editor de FIP: encabezado de la comunidad, barra de progreso y las cuatro secciones FAIR](images/editor-overview.png)

- **El encabezado de la comunidad**: el nombre de la comunidad que está describiendo, más detalles opcionales. Puede editar esto en cualquier momento; no se bloquea después de la creación.
- **Una barra de progreso**: cuántas de las preguntas tienen al menos una respuesta. Es una guía, no un requisito: una pregunta sin respuesta es un estado legítimo.
- **Cuatro secciones plegables**: **L**ocalizable, **A**ccesible, **I**nteroperable y **R**eutilizable. La sección **L**ocalizable está abierta cuando llega; toque un encabezado para abrir o cerrar una sección. Trabaje en el orden que prefiera.
- **La fila de acciones**: compartir, descargar y, si ha iniciado sesión, controles de visibilidad.

Cada pregunta dentro de una sección es una tarjeta que muestra el texto de la pregunta, un texto de **ayuda** corto que puede expandir, un interruptor de **No aplica**, y el área de respuesta.

![Una tarjeta de pregunta individual](images/question-card.png)

> **En un teléfono**, las secciones y las tarjetas de preguntas se apilan verticalmente y todo es accesible desplazándose: no hay una versión móvil separada que buscar.

---

## 4. Recorrido guiado: rellene su primer FIP

### Paso 1 — Elija su área

Si el facilitador ofreció varios cuestionarios de área, elige uno al unirse. Escoja el área más cercana al trabajo de su grupo. Si ninguna se ajusta, elija **"Otra área"**: obtendrá la lista genérica de 21 preguntas con texto libre disponible en todas partes.

El área determina **qué opciones se sugieren**, no qué preguntas se hacen. Todas las áreas preguntan las mismas 21 preguntas.

![Elegir un área de investigación al unirse a una sesión](images/join-area-choice.png)

> **Esta elección se hace una vez, al unirse.** Si eligió el área equivocada, la solución más rápida en un taller es empezar un nuevo FIP y elegir de nuevo: pídale al facilitador, quien también puede eliminar el que abandonó.

### Paso 2 — Asigne un nombre a su comunidad

Dé a la comunidad un nombre que la gente reconocerá: "Laboratorio de Genómica, Fiocruz" en lugar de "nuestro grupo". Este nombre aparece en la matriz de comparación que la sala mira en conjunto, y en cada exportación.

![Asignar nombre a la comunidad antes de empezar el FIP](images/join-community-name.png)

### Paso 3 — Lea la pregunta

Cada pregunta nomina un tipo de recurso de habilitación FAIR. Si la redacción no le es familiar, expanda el texto de **ayuda**: explica qué tipo de cosa se está preguntando, y normalmente da un ejemplo.

![Una tarjeta de pregunta con su texto de ayuda expandido](images/question-help.png)

> **Si realmente no lo sabe**, deje la pregunta vacía y continúe. Volver a ella después de ver las otras preguntas suele ser más fácil, y una pregunta vacía es una respuesta honesta.

### Paso 4 — Marque una opción sugerida

La mayoría de las preguntas muestran una lista corta de opciones sugeridas. **Marcar una registra que su comunidad la utiliza hoy**: esa es toda la acción, sin ningún paso adicional.

Las opciones sugeridas vienen en dos tipos, y ambos son respuestas igual de válidas:

- **Recursos de catálogo**: FERs reconocidos y nombrados (DOI, ORCID, Dublin Core…). Estos son los que se comparan limpiamente entre comunidades.
- **Frases sugeridas**: redactados descriptivos para prácticas que no son un producto nombrado ("solo texto no estructurado", "cuenta del repositorio"). Estos registran la realidad donde no existe un recurso estándar.

Si la lista no muestra lo que necesita, utilice la búsqueda del catálogo para buscar un recurso por nombre, o escriba su propia respuesta: ese es el siguiente paso.

![La lista de opciones sugeridas para una pregunta](images/options-list.png)

### Paso 5 — Responda con sus propias palabras

Al final de la lista de opciones está **"Otro (especificar)"**: márquelo para abrir un cuadro de texto, escriba su propia redacción, luego pulse Intro o toque el botón de añadir. El cuadro de la declaración también tiene un botón **"Usar mis propias palabras"** que cambia el selector de recursos de la búsqueda del catálogo a texto libre para esa respuesta.

Una respuesta de texto libre es **igualmente válida** que una de la lista. Úsela para herramientas locales, sistemas internos y prácticas informales: son precisamente las cosas que una lista fija no puede anticipar, y omitirlas falsearía la representación de su comunidad.

![Responder con sus propias palabras mediante Otro (especificar)](images/other-specify.png)

### Paso 6 — Cuando la pregunta no aplica

Algunas preguntas realmente no aplican a una comunidad dada. Active el interruptor **"No aplica"** en la propia pregunta. La herramienta le pide que confirme, porque marcar una pregunta como no aplicable elimina cualquier recurso ya registrado en ella. Luego, el cuadro de comentarios pregunta *por qué* no aplica: una línea corta es suficiente, y vale la pena escribirla, porque "no aplica" y "sin responder" significan cosas muy diferentes para cualquiera que lea su FIP más tarde.

> **"No aplica" no es un salto.** Úselo cuando la pregunta sea realmente irrelevante para su comunidad: no cuando no esté seguro, y no cuando la respuesta sea simplemente "ninguna todavía". Para "no hemos decidido", deje la pregunta vacía.

### Paso 7 — Cuando está planificado en lugar de en uso

Marcar una opción registra **En uso actualmente**. Cuando esa no sea la descripción correcta, toque **"Más"** en la respuesta para abrir el control de estado completo:

| Estado | Úselo cuando |
|---|---|
| **En uso actualmente** | En uso hoy. Esto es lo que marca una opción registra. |
| **Planificado** | Decidido, pero aún no en uso. |
| **Por desarrollar** | Se está construyendo o adoptando ahora mismo. |
| **Por sustituir** | Lo usa hoy, pero está en proceso de ser reemplazado. Nombre también el recurso sustituto. |
| **Sin elección todavía** | Quiere registrar explícitamente que no se ha decidido nada, en lugar de dejar la pregunta en blanco. |

El mismo panel de "Más" contiene una **nota** opcional — una frase de contexto — y, cuando su instancia está vinculada a una herramienta de planes de gestión de datos, una forma de apuntar a la sección de un DMP que respalda esta respuesta.

![El control de estado expandido que muestra los cinco estados de declaración](images/status-control.png)

### Paso 8 — Añada más de una respuesta

Muchas preguntas aceptan varias respuestas: dos esquemas de identificadores, un vocabulario actual y su sustituto planificado. Utilice **"Añadir un recurso"** para registrar cada uno por separado, con su propio estado y nota, en lugar de agruparlos todos en un solo cuadro de texto libre. Las declaraciones separadas permanecen comparables; una oración que enumera tres cosas no.

### Paso 9 — Siga su progreso

La barra de progreso cuenta las preguntas con al menos una respuesta. No hay un mínimo ni una puerta de validación: un FIP con doce respuestas honestas es más útil que uno con 21 suposiciones.

El guardado ocurre automáticamente, un momento después de que deje de escribir. El indicador dice **"Guardado {time}"** y **"Cambios sin guardar"** mientras un cambio aún está pendiente. Si va a cerrar el portátil, mire ese indicador primero.

![El encabezado de la comunidad y el indicador de guardado](images/save-indicator.png)

### Paso 10 — Comparta su FIP

Abra el panel **Compartir**. Este le ofrece dos cosas diferentes:

- **El enlace del FIP**: una URL permanente, **solo lectura** para su FIP, más un código QR. Seguro de enviar a cualquier persona: pueden leerlo pero no cambiarlo.
- **El enlace de edición**: una URL que **concede permisos de edición**. Cualquier persona que lo tenga puede cambiar su FIP, así que compártalo solo dentro de su grupo.

Conserve el enlace del FIP. Sigue funcionando después del taller.

![El panel Compartir con el enlace del FIP, código QR y enlace de edición](images/share-panel.png)

---

## 5. Los cinco tipos de respuesta

| Respuesta | Cómo | Qué registra |
|---|---|---|
| **Marcar una opción** | Toque una opción sugerida | Su comunidad la utiliza hoy |
| **Buscar en el catálogo** | Busque por nombre en el selector | Lo mismo, para un recurso que no está en las sugerencias |
| **"Otro (especificar)"** | Márcalo, escriba, pulse Intro | Su propia redacción: igual de válida |
| **"No aplica"** | Active el interruptor en la pregunta, confirme | La pregunta es irrelevante para su comunidad |
| **Dejarla vacía** | Continúe | No decidido todavía: una respuesta honesta, no un fallo |

---

## 6. Volver más tarde, y en otro dispositivo

Su FIP **no** está vinculado al dispositivo que lo creó.

- **Mismo dispositivo**: la página de inicio lista los **FIPs en este dispositivo**. Toque el suyo para reabrirlo.
- **Otro teléfono o portátil**: abra el panel **Compartir**, copie el **Enlace de edición** y abra ese enlace en el otro dispositivo. Esa es la forma admitida para moverse entre un teléfono y un portátil, o para pasar el FIP a un compañero que lo continuará.
- **Perdió el enlace por completo**: si lo rellenó durante una sesión facilitada, el facilitador aún puede ver el FIP y recuperar su enlace. Si era independiente y la lista del dispositivo se ha perdido, no se puede recuperar: esa es la razón más fuerte para crear una cuenta ([§7](#7-crear-una-cuenta-opcional)) o para guardar el enlace en algún lugar.

![La lista FIPs en este dispositivo en la página de inicio](images/home-device-fips.png)

> **Trate el enlace de edición como una contraseña.** Cualquier persona que lo tenga puede editar el FIP. El enlace del FIP normal es el que se comparte ampliamente.

> **Los FIPs independientes no se conservan para siempre.** Una instancia puede eliminar FIPs independientes que no se hayan editado durante mucho tiempo (doce meses en el despliegue de CONFOA). Los FIPs reclamados en una cuenta no están sujetos a eso.

---

## 7. Crear una cuenta (opcional)

Nunca es necesario tener una cuenta para rellenar un FIP. Una cuenta le ofrece:

- **Un espacio de trabajo** que lista todos sus FIPs, sesiones y modelos de conocimiento en un solo lugar.
- **Reclamar**: abra un FIP que creó anónimamente y elija **Reclamar** para moverlo a su espacio de trabajo permanentemente, de modo que ya no dependa de un enlace guardado en un navegador.
- **Control de visibilidad**: establezca cada FIP como **Privado**, **Enlace** (cualquiera con el enlace puede leerlo) o **Público**.
- **Ejecutar sus propias sesiones**, si más adelante facilita un ejercicio usted mismo.

Puede reclamar un FIP en cualquier momento después de crear la cuenta, incluido uno que empezó en un taller meses antes, siempre que aún tenga su enlace de edición.

---

## 8. Elegir su idioma

La interfaz está disponible en **inglés**, **portugués europeo (pt-PT)**, **portugués brasileño (pt-BR)** y **español (es)**. Utilice el selector de idioma en el encabezado; si su navegador ya está configurado con uno de estos, el sitio se abre en él automáticamente. Las variantes del portugués retroceden entre sí antes de retroceder al inglés, así que siempre obtendrá texto en portugués donde exista alguna traducción al portugués.

Cambiar el idioma cambia **la interfaz y los textos de las preguntas**. Nunca cambia ni traduce **sus respuestas**: lo que escribió permanece exactamente como lo escribió.

---

## 9. Descargar y compartir su FIP

Desde el editor o la vista de solo lectura, puede descargar su FIP como:

| Formato | Para qué sirve |
|---|---|
| **JSON** | Legible por máquina, para volver a cargar o procesar |
| **CSV** | Una hoja de cálculo: una fila por declaración |
| **Turtle** / **JSON-LD** | RDF siguiendo la ontología FIP, para herramientas y publicación de la web semántica |

![Botones de exportación: JSON, CSV, Turtle y JSON-LD](images/export-buttons.png)

Las exportaciones RDF son las que hacen que su FIP forme parte del ecosistema FAIR más amplio en lugar de ser una hoja de cálculo privada. No necesita entenderlas para beneficiarse de ellas.

---

## 10. Solución de problemas

| Síntoma | Qué hacer |
|---|---|
| **El código de acceso no se acepta** | Verifique los caracteres confusos, y que la sesión no se haya cerrado. Pídale al facilitador que vuelva a leer el código de su pantalla. |
| **El código QR no se escanea** | Escriba el código de acceso en la página de inicio: es lo mismo. |
| **No veo el indicador "Guardado"** | Aparece un momento después de que deje de escribir. Si nunca aparece, verifique su conexión: su texto permanece en la página hasta que se guarda. |
| **Mi opción no está en la lista** | Busque en el catálogo por nombre, o utilice **"Otro (especificar)"** y escríbala usted mismo. |
| **Marcó la opción equivocada** | Tóquela de nuevo para desmarcarla, o elimine la declaración de la fila de respuesta. |
| **No puedo editar: todo es de solo lectura** | Está en el enlace del FIP normal, no en el enlace de edición. Obtenga el enlace de edición de quien empezó el FIP. |
| **Elegí el área equivocada** | Pregúntele al facilitador. El área se fija al unirse: empezar de nuevo suele ser más rápido que rehacer. |
| **Perdí mi FIP** | Verifique **FIPs en este dispositivo** en la página de inicio. En una sesión, el facilitador puede encontrarlo. |

---

## 11. Atribución

Contenido del cuestionario: FIP mini-questionnaire v2.0.0 © 2023 Erik Schultes, Barbara Magagna, Jacintha Schultes / GO FAIR Foundation, CC BY-SA 4.0. Las listas de selección de áreas adaptadas de "PERFIS DE IMPLEMENTAÇÃO FAIR 2" (autor por confirmar), usadas bajo los mismos términos CC BY-SA 4.0.
