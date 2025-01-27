from poetry.plugins.application_plugin import ApplicationPlugin

from poetry_plugin_migrate.command import MigrateCommand


def factory():
    return MigrateCommand()


class MigrateApplicationPlugin(ApplicationPlugin):
    def activate(self, application):
        application.command_loader.register_factory("migrate", factory)
