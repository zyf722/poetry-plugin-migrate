from poetry.console.application import Application
from poetry.plugins.application_plugin import ApplicationPlugin

from poetry_plugin_migrate.command import MigrateCommand


def factory() -> MigrateCommand:
    return MigrateCommand()


class MigrateApplicationPlugin(ApplicationPlugin):
    def activate(self, application: Application) -> None:
        application.command_loader.register_factory("migrate", factory)
