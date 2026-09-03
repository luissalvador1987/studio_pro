{
    'name': "Studio Pro",
    'summary': "Constructor de Apps / Modelos / Automatizaciones / Reportes — una alternativa más potente a Odoo Studio",
    'description': """
Crea Apps, Modelos, Campos, Vistas, Automatizaciones multi-paso, Reportes
PDF/QWeb y Permisos de Acceso personalizados enteramente desde el backend de
Odoo, sin tocar una línea de código, como Odoo Studio, con algunos trucos
adicionales.

Lo más destacado:

* **Ícono de Studio Pro en la barra superior, en cualquier App instalada**:
  un clic abre el editor guiado de Studio Pro para lo que estés mirando en
  ese momento (modelo y tipo de vista actuales, resueltos igual que lo hace
  el propio Odoo: ``ir.ui.view.default_view``) — si esa vista todavía no
  existe para el modelo, abre el asistente de Nueva Vista ya precompletado
  en vez de fallar. Así no hace falta entrar primero a la App de Studio Pro
  para editar la pantalla que ya tenés abierta, en ninguna App del sistema.
* Editor de vistas con grupos y pestañas de verdad (no solo una lista plana
  de campos): crea nuevos grupos/pestañas y decide en qué grupo va cada
  campo. Y crea vistas nuevas —formulario, lista, kanban, búsqueda,
  calendario, **tabla dinámica, gráfico y actividades**— para cualquier
  modelo, no solo edita las existentes.
* **Personalizar Búsqueda sin código**: agregá filtros con condición
  ("Solo vencidas", "Monto > 1000") y opciones de "Agrupar por" a la
  búsqueda de cualquier modelo desde un formulario guiado, sin tocar XML.
* **Chatter y Actividades con un clic**: activá el historial de mensajes,
  seguidores y actividades (recordatorios con fecha límite) sobre
  cualquier modelo de Studio Pro —al crearlo o después— con el mecanismo
  100% nativo de Odoo (``ir.model.is_mail_thread``/``is_mail_activity``,
  del propio módulo mail), sin escribir una clase Python.
* **Campos traducibles**: marcá cualquier campo de texto para que se pueda
  escribir distinto en cada idioma instalado.
* **Más control por campo**: solo lectura, registrar cambios en el Chatter
  (``tracking``, mecanismo nativo del propio módulo mail) y un valor por
  defecto para registros nuevos (mecanismo nativo ``ir.default`` — el mismo
  que usa el propio Odoo Studio), todo desde el asistente de Nuevo Campo.
* **Actividades y Seguidores desde Automatizaciones y Funciones**: además de
  actualizar un campo, crear un registro, enviar un correo o llamar a un
  webhook, un paso puede crear una Actividad (recordatorio con fecha límite
  y responsable) o agregar Seguidores a un registro — mecanismo 100% nativo
  de ``ir.actions.server`` (del propio módulo mail), sobre modelos con
  Chatter/Actividades habilitadas.
* **Dos niveles de acceso**: "Constructor de Studio Pro" (crea y edita todo)
  y "Studio Pro — Solo lectura" (ve Apps, Tableros e Historial de cambios,
  sin poder tocar la estructura de la base de datos) — para dar visibilidad
  a un gerente o auditor sin darle permisos de builder.
* **Campos calculados de verdad**: consola de código Python integrada
  (mismo motor sandboxeado que las Funciones) con su propio "Depende de"
  —el equivalente exacto a ``@api.depends``— para que el campo se
  recalcule solo cuando corresponde, y no en cada lectura.
* **Relaciones con restricciones reales**: al crear un Many2one, elige qué
  pasa si se borra el registro relacionado (dejar en blanco, impedir el
  borrado, o borrar en cascada) e indexa cualquier campo desde el mismo
  asistente. Además, un editor de **Restricciones (Constraints)** para
  reglas Únicas o de Condición sobre tus propios modelos, aplicadas
  directamente en PostgreSQL.
* **Herencia de vistas y reportes por xpath**: un asistente guiado para
  extender cualquier vista o reporte PDF —nativo, de cualquier addon, o
  propio— insertando contenido antes, después, dentro o en reemplazo de
  cualquier elemento, sin tocar la vista original (así una actualización
  de Odoo nunca te borra el cambio).
* **Código JS/CSS personalizado**: agrega tu propio JavaScript o CSS al
  panel de control o al sitio web con el mecanismo nativo de Odoo
  (``ir.asset``), sin escribir un solo archivo ni reiniciar el servidor.
* **Seguridad de verdad**: asistente de Reglas de Registro (Record Rules)
  con presets ("solo mis propios registros", "solo de mi compañía") o
  dominio libre, acceso directo a Permisos de Acceso (ACL), y restricción
  de campos por grupo directamente desde el asistente de campos —la forma
  real en que Odoo hace seguridad de campo (a nivel de vista, como
  cualquier módulo escrito a mano).
* Funciones: acciones de servidor reutilizables (actualizar campo, crear
  registro, enviar correo, webhook o código Python) que se exponen solas en
  el menú de Acciones (⚙) de un modelo, o se ejecutan por horario — a
  diferencia de una Automatización, que solo se dispara por un evento.
* Flujos de automatización multi-paso con ramificación condicional real, no
  solo un disparador y una acción.
* Un historial de cambios de todo lo creado con Studio Pro, con reversión
  de mejor esfuerzo y exportación a un módulo de Odoo real e instalable.
* Un Asistente de IA que convierte una solicitud en lenguaje simple en un
  plan revisable (campos o automatizaciones nuevas) que apruebas antes de
  aplicar nada.
* Valores por defecto inteligentes: cada App personalizada obtiene
  automáticamente sus propios grupos Administrador y Usuario y sus permisos
  de acceso.
* Tableros (gráfico, tabla dinámica, kanban, lista) sobre cualquier modelo
  —estándar, de otro addon o creado con Studio Pro— usando siempre el ORM
  seguro de Odoo.
* Acceso técnico directo a todos los Reportes, Vistas y Módulos/Addons
  instalados del sistema, no solo a los creados con Studio Pro.

**Exportación real y completa a un módulo instalable**: el botón Exportar
ahora genera la estructura de carpetas real de un módulo de Odoo
(``models/``, ``views/``, ``security/`` con su ``ir.model.access.csv`` de
verdad, ``data/`` para automatizaciones/funciones/reportes) lista para un
repositorio Git y un pipeline de CI/CD — modelos, campos (con sus
restricciones on_delete/index/calculado), vistas, acciones, menús, grupos,
Permisos de Acceso, Reglas de Registro, Automatizaciones, Funciones y
Reportes, todo en un solo .zip.

Todo lo creado con Studio Pro vive como datos normales de Odoo (ir.model,
ir.model.fields, ir.ui.view, ir.actions.server, etc.), igual que Studio, así
que sigue funcionando incluso sin este módulo instalado.

Honestidad técnica:

* Studio Pro deliberadamente NO incluye un ejecutor de SQL arbitrario.
  Permitir SQL libre saltaría todos los permisos y reglas de negocio de la
  base de datos — ni siquiera Odoo Studio ofrece eso. Para "consultas de
  base de datos" se usan Tableros (gráfico/tabla dinámica) sobre el ORM, y
  las Restricciones (Constraints) generan SQL parametrizado desde campos
  validados, nunca texto libre del usuario.
* La exportación resuelve automáticamente qué vistas/acciones/reglas
  pertenecen de verdad a tu App incluso cuando editas un modelo nativo
  (ej. res.partner) — no vuelca por error las de otros addons instalados.
  Aun así, revisa el .zip generado antes de instalarlo en otro servidor:
  algunas referencias (destinos fijos de un paso "Actualizar campo", o
  plantillas de correo externas a la App) son específicas de esta base de
  datos y pueden necesitar ajustarse a mano.
* **Diseñador visual de arrastrar y soltar** para formularios y listas:
  reordená campos arrastrándolos, movelos a otro grupo o pestaña soltándolos
  ahí, y arrastrá campos nuevos del modelo desde la barra de herramientas de
  la izquierda directamente a donde tienen que ir. "Nuevo Grupo"/"Nueva
  Pestaña" quedan como botones (crean un contenedor, no un campo). Se abre
  solo o desde el ícono de Studio Pro en cualquier App, o desde el editor de
  vistas clásico (botón "Diseño visual"). Guarda a través del mismo motor
  del editor guiado (``ir.ui.view.studio_apply_field_lines``) — sin un
  segundo camino de persistencia en paralelo — así que todo cambio sigue
  quedando en un registro auditable con reversión desde el Historial de
  cambios, algo que un editor puramente visual normalmente no te da gratis.
  El editor guiado con lista editable (sin arrastrar, más accesible por
  teclado) sigue disponible como alternativa, y también sirve para
  kanban/calendario/tabla dinámica/gráfico/búsqueda/actividades, tipos de
  vista sin una estructura real de grupos/pestañas donde arrastrar no
  aplica.
* **Qué NO incluye, a propósito**: la vista Gantt no está entre los tipos
  de vista ofrecidos — su motor de renderizado (``web_gantt``) es
  exclusivo de Odoo Enterprise y no existe en Community, así que crear una
  vista de ese tipo acá no tendría con qué dibujarse en el navegador;
  ofrecerla igual sería aparentar una función de Enterprise que en los
  hechos no funciona. Tampoco se agregó "Enviar SMS" como paso de Función:
  requiere el módulo ``sms`` instalado (con su propio proveedor
  configurado) y depender de él a la fuerza en todas las instalaciones no
  vale la pena por una opción que la mayoría no va a usar — si lo
  necesitás, la Acción de Servidor nativa de Odoo ya soporta 'Enviar SMS'
  una vez que el módulo sms está instalado. El diseñador visual, por ahora,
  solo arrastra ``<field/>`` — no botones, etiquetas ni separadores; agregar
  esos elementos todavía se hace editando el arch directamente (Herramientas
  Avanzadas > Todas las Vistas) o por herencia xpath.
    """,
    'version': '18.0.5.0.0',
    'category': 'Customizations',
    'author': "Designweblp",
    'maintainer': "Designweblp",
    'website': "https://github.com/luissalvador1987/studio_pro",
    'support': "luissalvador1987@gmail.com",
    'license': 'OPL-1',
    'price': 100.0,
    'currency': 'USD',
    'images': ['static/description/banner.png'],
    'depends': ['base', 'web', 'mail', 'base_automation'],
    'data': [
        'security/studio_pro_groups.xml',
        'security/ir.model.access.csv',
        'wizards/studio_new_model_wizard_views.xml',
        'wizards/studio_new_field_wizard_views.xml',
        'wizards/studio_view_editor_wizard_views.xml',
        'wizards/studio_new_view_wizard_views.xml',
        'wizards/studio_view_inherit_wizard_views.xml',
        'wizards/studio_record_rule_wizard_views.xml',
        'wizards/studio_mail_features_wizard_views.xml',
        'wizards/studio_search_customizer_wizard_views.xml',
        'wizards/studio_export_wizard_views.xml',
        'wizards/studio_ai_assistant_views.xml',
        'views/studio_app_views.xml',
        'views/studio_automation_views.xml',
        'views/studio_server_action_views.xml',
        'views/studio_report_builder_views.xml',
        'views/studio_dashboard_views.xml',
        'views/studio_model_constraint_views.xml',
        'views/studio_custom_code_views.xml',
        'views/studio_change_views.xml',
        'views/res_config_settings_views.xml',
        'views/studio_menus.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'studio_pro/static/src/js/**/*',
            'studio_pro/static/src/xml/**/*',
            'studio_pro/static/src/scss/**/*',
        ],
    },
    'installable': True,
    'application': True,
    'auto_install': False,
}
