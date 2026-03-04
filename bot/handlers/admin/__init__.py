"""Admin panel router with AdminMiddleware."""
from aiogram import Router
from bot.middlewares.admin import AdminMiddleware

from . import roles, users, finance, operations, promos, support, audit

admin_router = Router(name="admin")
admin_router.message.middleware(AdminMiddleware(min_role="support"))
admin_router.callback_query.middleware(AdminMiddleware(min_role="support"))

admin_router.include_router(operations.router)  # dashboards — all admin roles
admin_router.include_router(support.router)      # tickets — all admin roles
admin_router.include_router(finance.router)       # finances — finance+
admin_router.include_router(users.router)         # user management — admin+
admin_router.include_router(promos.router)        # promo codes — admin+
admin_router.include_router(audit.router)         # audit logs — admin+
admin_router.include_router(roles.router)         # role management — superadmin only
