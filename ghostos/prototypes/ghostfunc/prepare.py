from typing import Optional
from ghostos.container import Container
from ghostos.core.moss import moss_container, MossCompiler

from ghostos.core.llms import LLMs
from ghostos.framework.configs import ConfigsByStorageProvider
from ghostos.framework.storage import FileStorageProvider
from ghostos.framework.llms import ConfigBasedLLMsProvider
from ghostos.prototypes.ghostfunc.decorator import GhostFunc
from ghostos.container import Contracts

__all__ = ["init_ghost_func_container", "init_ghost_func", 'ghost_func_contracts']

ghost_func_contracts = Contracts([
    LLMs,
    MossCompiler,
])


def init_ghost_func_container(
        workspace_dir: str,
        configs_dir: str = "configs",
        llm_conf_path: str = "llms_conf.yml",
        container: Optional[Container] = None,
) -> Container:
    """
    init ghost_func's container
    :param workspace_dir:
    :param configs_dir: relative directory from workspace
    :param llm_conf_path: llms conf path
    :param container: parent container.
    """
    if container is None:
        container = moss_container()
    container.register(FileStorageProvider(workspace_dir))
    container.register(ConfigsByStorageProvider(configs_dir))
    container.register(ConfigBasedLLMsProvider(llm_conf_path))
    return container


def init_ghost_func(
        container: Container,
) -> GhostFunc:
    """
    return ghost func instance
    :param container: application container.
    """
    ghost_func_contracts.validate(container)
    self_container = Container(parent=container)
    self_container.bootstrap()
    return GhostFunc(self_container)
