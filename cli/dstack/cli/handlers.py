import dstack.cli.commands
import pkgutil


def cli_initialize(parser):
    package = dstack.cli.commands
    for importer, modname, ispkg in pkgutil.iter_modules(package.__path__):
        modname = f"dstack.cli.commands.{modname}"
        importer.find_module(modname).load_module(modname)

    commands = [cls(parser=parser) for cls in dstack.cli.commands.BasicCommand.__subclasses__()]  # pylint: disable=E1101
    for command in commands:
        command.register()
