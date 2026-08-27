{
    'name': "Studio Pro",
    'summary': "Constructor de Apps / Modelos / Automatizaciones / Reportes — una alternativa más potente a Odoo Studio",
    'description': """
Crea Apps, Modelos, Campos, Vistas, Automatizaciones multi-paso, Reportes
PDF/QWeb y Permisos de Acceso personalizados enteramente desde el backend de
Odoo, sin tocar una línea de código, como Odoo Studio, con algunos trucos
adicionales.

Lo más destacado:

* Editor de vistas con grupos y pestañas de verdad (no solo una lista plana
  de campos): crea nuevos grupos/pestañas y decide en qué grupo va cada
  campo. Y crea vistas nuevas (formulario, lista, kanban, búsqueda,
  calendario) para cualquier modelo, no solo edita las existentes.
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

Todo lo creado con Studio Pro vive como datos normales de Odoo (ir.model,
ir.model.fields, ir.ui.view, ir.actions.server, etc.), igual que Studio, así
que sigue funcionando incluso sin este módulo instalado.

Nota: Studio Pro deliberadamente NO incluye un ejecutor de SQL arbitrario.
Permitir SQL libre saltaría todos los permisos y reglas de negocio de la
base de datos — ni siquiera Odoo Studio ofrece eso. Para "consultas de base
de datos" se usan Tableros (gráfico/tabla dinámica) sobre el ORM, que es la
forma segura de lograr el mismo resultado.
    """,
    'version': '18.0.1.0.0',
    'category': 'Customizations',
    'author': "Designweblp",
    'maintainer': "Designweblp",
    'website': "https://github.com/luissalvador1987/studio_pro",
    'support': "luissalvador1987@gmail.com",
    'license': 'OPL-1',
    'price': 100.0,
    'currency': 'EUR',
    'images': ['static/description/banner.png'],
    'depends': ['base', 'web', 'mail', 'base_automation'],
    'data': [
        'security/studio_pro_groups.xml',
        'security/ir.model.access.csv',
        'wizards/studio_new_model_wizard_views.xml',
        'wizards/studio_new_field_wizard_views.xml',
        'wizards/studio_view_editor_wizard_views.xml',
        'wizards/studio_new_view_wizard_views.xml',
        'wizards/studio_export_wizard_views.xml',
        'wizards/studio_ai_assistant_views.xml',
        'views/studio_app_views.xml',
        'views/studio_automation_views.xml',
        'views/studio_server_action_views.xml',
        'views/studio_report_builder_views.xml',
        'views/studio_dashboard_views.xml',
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
