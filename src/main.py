# MIT License
#
# Copyright (c) 2026 Philipp Höllinger
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in
# all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
# THE SOFTWARE.

"""Composition root: loads the selected database adapter and wires FastAPI."""

from __future__ import annotations

import importlib
import inspect
import logging
import sys
from pathlib import Path
from types import ModuleType

from fastapi import APIRouter, FastAPI
from pydantic import ValidationError
from wireup import create_sync_container, injectable

import application
import application.controllers as controllers_package
import infrastructure.config
import infrastructure.observability
from core.model.access_guard import AccessGuard
from core.ports.outbound.query_executor import QueryExecutor
from core.ports.outbound.query_scrubber import QueryScrubber
from core.ports.outbound.query_validator import QueryValidator
from infrastructure.config.settings import GatewaySettings

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)

_ADAPTER_PACKAGE_ROOT = "infrastructure.persistence"


class AdapterImportFailed(RuntimeError):
    """Raised when the selected database adapter package cannot be imported."""


def _import_submodules_recursively(package: ModuleType) -> list[ModuleType]:
    """Import every ``.py`` submodule under ``package`` and return the list."""
    if not hasattr(package, "__path__"):
        return [package]
    for path_str in package.__path__:
        root = Path(path_str)
        for py_file in root.rglob("*.py"):
            if py_file.name == "__init__.py":
                continue
            relative = py_file.relative_to(root).with_suffix("")
            module_name = ".".join((package.__name__, *relative.parts))
            importlib.import_module(module_name)
    prefix = f"{package.__name__}."
    return [module for name, module in sys.modules.items() if name.startswith(prefix)]


def _load_adapter(adapter_name: str) -> ModuleType:
    module_path = f"{_ADAPTER_PACKAGE_ROOT}.{adapter_name}"
    try:
        return importlib.import_module(module_path)
    except ImportError as exception:
        raise AdapterImportFailed(
            f"Failed to import adapter {module_path!r}: {exception}. "
            f"Make sure the adapter package exists under "
            f"``src/{_ADAPTER_PACKAGE_ROOT.replace('.', '/')}/{adapter_name}/``."
        ) from exception


@injectable
def assemble_access_guard(
    validator: QueryValidator,
    scrubber: QueryScrubber,
    executor: QueryExecutor,
) -> AccessGuard:
    """Compose the port triple into the domain value object."""
    return AccessGuard(validator=validator, scrubber=scrubber, executor=executor)


def _discover_controllers(pkg: ModuleType) -> list[type]:
    """Return every ``@injectable`` class defined inside ``pkg``."""
    classes: list[type] = []
    for module in _import_submodules_recursively(pkg):
        for _, obj in inspect.getmembers(module, inspect.isclass):
            if obj.__module__ != module.__name__:
                continue
            if not hasattr(obj, "__wireup_registration__"):
                continue
            classes.append(obj)
    return sorted(classes, key=lambda cls: cls.__name__)


def _load_settings_or_exit() -> GatewaySettings:
    try:
        return GatewaySettings()
    except ValidationError as exception:
        missing = sorted(
            {
                str(location[0]).upper()
                for error in exception.errors()
                if error["type"] == "missing"
                for location in [error["loc"]]
                if location
            }
        )
        if missing:
            print(
                "\nStartup error: missing required environment variables: "
                f"{', '.join(missing)}.\n"
                "Copy .env.example to .env and fill in the values, or export "
                "the variables in the shell.\n",
                file=sys.stderr,
            )
        else:
            print(f"\nStartup error: invalid settings.\n{exception}\n", file=sys.stderr)
        raise SystemExit(1) from exception


def build_app() -> FastAPI:
    settings = _load_settings_or_exit()
    adapter_module = _load_adapter(settings.database_adapter)

    injectables: list[ModuleType] = [
        *_import_submodules_recursively(application),
        *_import_submodules_recursively(infrastructure.observability),
        *_import_submodules_recursively(infrastructure.config),
        *_import_submodules_recursively(adapter_module),
        sys.modules[__name__],
    ]

    container = create_sync_container(injectables=injectables)

    app = FastAPI(title="SQL Gateway")
    for controller_class in _discover_controllers(controllers_package):
        instance: object = container.get(controller_class)
        router = getattr(instance, "router", None)
        if isinstance(router, APIRouter):
            app.include_router(router)
    return app


app = build_app()
