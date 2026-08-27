# Studio Pro — Odoo 18

Constructor de Apps / Modelos / Automatizaciones / Reportes — una alternativa más potente a Odoo Studio.

Crea Apps, Modelos, Campos, Vistas, Automatizaciones multi-paso, Reportes PDF/QWeb y Permisos de Acceso personalizados enteramente desde el backend de Odoo, sin tocar una línea de código.

Ficha completa con capturas: [`static/description/index.html`](./studio_pro/static/description/index.html)

## Lo más destacado

- **Editor de vistas con grupos y pestañas de verdad** (no solo una lista plana de campos): crea nuevos grupos/pestañas y decide en qué grupo va cada campo. Crea vistas nuevas (formulario, lista, kanban, búsqueda, calendario) para cualquier modelo.
- **Funciones**: acciones de servidor reutilizables (actualizar campo, crear registro, enviar correo, webhook o código Python) expuestas en el menú de Acciones de un modelo, o ejecutadas por horario.
- **Flujos de automatización multi-paso** con ramificación condicional real.
- **Historial de cambios** de todo lo creado con Studio Pro, con reversión de mejor esfuerzo y exportación a un módulo de Odoo real e instalable.
- **Asistente de IA** que convierte una solicitud en lenguaje simple en un plan revisable (campos o automatizaciones nuevas) que apruebas antes de aplicar nada.
- **Valores por defecto inteligentes**: cada App personalizada obtiene automáticamente sus propios grupos Administrador y Usuario y sus permisos de acceso.
- **Tableros** (gráfico, tabla dinámica, kanban, lista) sobre cualquier modelo, usando siempre el ORM seguro de Odoo.
- **Acceso técnico directo** a todos los Reportes, Vistas y Módulos/Addons instalados del sistema.

## Compatible con Odoo de verdad

Todo lo creado con Studio Pro vive como datos normales de Odoo (`ir.model`, `ir.model.fields`, `ir.ui.view`, `ir.actions.server`, etc.), así que sigue funcionando incluso sin este módulo instalado.

## Deliberadamente sin SQL libre

Studio Pro deliberadamente **NO incluye un ejecutor de SQL arbitrario**. Permitir SQL libre saltaría todos los permisos y reglas de negocio de la base de datos — ni siquiera Odoo Studio ofrece eso. Para "consultas de base de datos" se usan Tableros (gráfico/tabla dinámica) sobre el ORM.

## Requisitos

- Odoo **18.0** (Community o Enterprise).
- El Asistente de IA es opcional: si quieres usarlo, necesitas tu propia clave de API de un proveedor de LLM compatible, configurada en Ajustes.

## Instalación

1. Copia la carpeta `studio_pro` a tu carpeta de `addons` personalizada.
2. Reinicia el servidor de Odoo y actualiza la lista de aplicaciones.
3. Instala **Studio Pro** desde Aplicaciones.
4. Ve al menú **Studio Pro** para crear tu primera App.

## Licencia

[Odoo Proprietary License v1.0 (OPL-1)](./LICENSE). Requiere una licencia válida para su uso (ver [Odoo Apps](https://apps.odoo.com)).

## Soporte

luissalvador1987@gmail.com
